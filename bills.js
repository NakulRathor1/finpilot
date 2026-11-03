'use strict';

let bills = [];
const $id = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[ch]));

function localDate() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}
function setStatus(message, kind = '') {
  const node = $id('ocrStatus');
  node.textContent = message;
  node.className = `small ${kind === 'error' ? 'status-error' : 'muted'}`;
}
function dateFromOcr(text) {
  const iso = text.match(/\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b/);
  if (iso) return `${iso[1]}-${iso[2].padStart(2, '0')}-${iso[3].padStart(2, '0')}`;
  // Indian receipts usually use DD/MM/YYYY. Two-digit years are interpreted as 20xx.
  const local = text.match(/\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})\b/);
  if (!local) return '';
  let [, day, month, year] = local;
  if (year.length === 2) year = `20${year}`;
  const d = new Date(Number(year), Number(month) - 1, Number(day));
  if (d.getFullYear() !== Number(year) || d.getMonth() !== Number(month) - 1 || d.getDate() !== Number(day)) return '';
  return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
}
function amountFromOcr(text) {
  const lines = text.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
  const totalLabels = /\b(grand\s*total|total\s*amount|amount\s*due|balance\s*due|net\s*payable|amount\s*payable|total\s*paid|total)\b/i;
  const candidates = [];
  const add = (line, priority) => {
    const matches = [...line.matchAll(/(?:₹|rs\.?\s*|inr\s*)?([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]{1,2})?|[0-9]{1,9}(?:\.[0-9]{1,2})?)/gi)];
    for (const match of matches) {
      const value = Number(match[1].replace(/,/g, ''));
      if (Number.isFinite(value) && value > 0 && value <= 1_000_000_000) candidates.push({ value, priority });
    }
  };
  lines.forEach(line => {
    if (totalLabels.test(line)) add(line, /grand\s*total|amount\s*due|net\s*payable|amount\s*payable/i.test(line) ? 5 : 4);
    else if (/\b(subtotal|tax|gst|discount|change|cash|upi|card|invoice\s*(?:no|number))\b/i.test(line)) add(line, 1);
  });
  if (!candidates.length) lines.forEach(line => add(line, 2));
  candidates.sort((a, b) => b.priority - a.priority);
  return candidates[0]?.value ?? null;
}
function guessMerchant(text) {
  const skip = /\b(invoice|receipt|bill|tax|gst|date|time|cashier|customer|phone|mobile|address|www\.|upi|thank you|original|duplicate|order|payment|total|subtotal)\b/i;
  return text.split(/\r?\n/).map(line => line.trim()).find(line =>
    line.length >= 3 && line.length <= 70 && /[a-zA-Z]/.test(line) && !skip.test(line) && !/^\d/.test(line)
  ) || 'Scanned receipt';
}
function guessCategory(text) {
  const t = text.toLowerCase();
  if (/electric|water bill|gas bill|internet|broadband|mobile recharge/.test(t)) return 'Utilities';
  if (/restaurant|cafe|food|swiggy|zomato|grocery|supermarket/.test(t)) return 'Food';
  if (/pharmacy|medical|hospital|clinic/.test(t)) return 'Health';
  if (/petrol|fuel|uber|ola|metro|bus|railway/.test(t)) return 'Transport';
  if (/salary|payroll|stipend/.test(t)) return 'Salary';
  if (/amazon|flipkart|shopping|retail/.test(t)) return 'Shopping';
  return 'Bills';
}
function preprocessImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      try {
        const scale = Math.min(2, 2400 / Math.max(img.width, img.height));
        const canvas = document.createElement('canvas');
        canvas.width = Math.max(1, Math.round(img.width * scale));
        canvas.height = Math.max(1, Math.round(img.height * scale));
        const ctx = canvas.getContext('2d', { willReadFrequently: true });
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height);
        for (let i = 0; i < pixels.data.length; i += 4) {
          const gray = 0.299 * pixels.data[i] + 0.587 * pixels.data[i + 1] + 0.114 * pixels.data[i + 2];
          const contrast = Math.max(0, Math.min(255, (gray - 128) * 1.18 + 128));
          pixels.data[i] = pixels.data[i + 1] = pixels.data[i + 2] = contrast;
        }
        ctx.putImageData(pixels, 0, 0);
        canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('Image preprocessing failed')), 'image/png');
      } catch (error) { reject(error); }
      finally { URL.revokeObjectURL(url); }
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Could not read this image. Try a JPG or PNG.')); };
    img.src = url;
  });
}
async function ensureTesseract() {
  if (window.Tesseract) return;
  const sources = [
    'https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js',
    'https://unpkg.com/tesseract.js@5/dist/tesseract.min.js'
  ];
  let lastError;
  for (const src of sources) {
    try {
      await new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = src; script.async = true;
        script.onload = resolve;
        script.onerror = () => { script.remove(); reject(new Error('OCR CDN unavailable')); };
        document.head.appendChild(script);
      });
      if (window.Tesseract) return;
    } catch (error) { lastError = error; }
  }
  throw new Error('OCR engine could not load. Check your internet connection, or enter the details manually.');
}
async function runOcr(file) {
  if (!file || !file.type.startsWith('image/')) throw new Error('Choose an image file (JPG, PNG, or WEBP).');
  if (file.size > 10 * 1024 * 1024) throw new Error('Image must be smaller than 10 MB.');
  setStatus('Preparing image for text recognition…');
  const image = await preprocessImage(file);
  await ensureTesseract();
  setStatus('Reading receipt… keep this page open.');
  const result = await window.Tesseract.recognize(image, 'eng', {
    logger: info => {
      if (info.status === 'recognizing text' && Number.isFinite(info.progress)) {
        setStatus(`Reading receipt… ${Math.round(info.progress * 100)}%`);
      }
    }
  });
  const text = (result.data?.text || '').trim();
  if (text.length < 4) throw new Error('Very little text was detected. Try a sharper, brighter image or enter the details manually.');
  return text;
}

async function loadBills() {
  const data = await api('/api/bills');
  bills = data.bills || [];
  const today = localDate();
  const end = new Date(); end.setDate(end.getDate() + 7);
  const endDate = `${end.getFullYear()}-${String(end.getMonth() + 1).padStart(2, '0')}-${String(end.getDate()).padStart(2, '0')}`;
  $id('upcoming').textContent = fmt(bills.filter(b => b.status !== 'Paid').reduce((sum, b) => sum + Number(b.amount), 0));
  $id('dueSoon').textContent = fmt(bills.filter(b => b.status !== 'Paid' && b.due_date >= today && b.due_date <= endDate).reduce((sum, b) => sum + Number(b.amount), 0));
  $id('paid').textContent = fmt(bills.filter(b => b.status === 'Paid' && b.due_date.slice(0, 7) === monthNow()).reduce((sum, b) => sum + Number(b.amount), 0));
  $id('recurring').textContent = bills.filter(b => b.frequency !== 'Once').length;
  renderBills();
}
function renderBills() {
  const status = $id('billFilter').value;
  const filtered = bills.filter(b => !status || b.status === status);
  $id('billRows').innerHTML = filtered.length ? filtered.map(b => `<tr>
    <td><b>${escapeHtml(b.title)}</b><div class="small muted">${escapeHtml(b.provider || b.category)}</div></td>
    <td>${escapeHtml(b.due_date)}</td><td>${escapeHtml(b.frequency)}</td><td>${fmt(b.amount)}</td>
    <td><span class="pill ${b.status === 'Paid' ? 'paid' : ''}">${escapeHtml(b.status)}</span></td>
    <td class="table-actions">${b.status !== 'Paid' ? `<button data-paid="${b.id}">Mark paid</button>` : ''} <button class="secondary" data-del="${b.id}">Delete</button></td>
  </tr>`).join('') : '<tr><td colspan="6" class="empty">No bills match this filter.</td></tr>';
}

$id('newBill').addEventListener('click', () => { const form = $id('billForm'); form.reset(); form.elements.due_date.value = localDate(); modal('billModal'); });
$id('scanBill').addEventListener('click', () => { $id('scanForm').reset(); $id('scanForm').elements.due_date.value = localDate(); $id('ocrStatus').textContent = 'Choose a clear receipt image. You can always enter the details manually.'; modal('scanModal'); });
$$('[data-close]').forEach(button => button.addEventListener('click', () => modal(button.dataset.close, false)));
$id('billForm').addEventListener('submit', async event => {
  event.preventDefault();
  try {
    await api('/api/bills', { method: 'POST', body: JSON.stringify(Object.fromEntries(new FormData(event.currentTarget))) });
    modal('billModal', false); toast('Bill saved'); await loadBills();
  } catch (error) { toast(error.message); }
});
$id('billRows').addEventListener('click', async event => {
  const button = event.target.closest('button'); if (!button) return;
  try {
    if (button.dataset.paid && confirm('Mark this bill paid and record it in transactions?')) {
      await api(`/api/bills/${button.dataset.paid}`, { method: 'PATCH', body: JSON.stringify({ status: 'Paid' }) });
      toast('Payment recorded'); await loadBills();
    } else if (button.dataset.del && confirm('Delete this bill? Its existing transaction remains in your history.')) {
      await api(`/api/bills/${button.dataset.del}`, { method: 'DELETE' }); await loadBills();
    }
  } catch (error) { toast(error.message); }
});
$id('billFilter').addEventListener('change', renderBills);
$id('billImage').addEventListener('change', async event => {
  const file = event.target.files?.[0]; if (!file) return;
  try {
    const text = await runOcr(file);
    const form = $id('scanForm');
    form.elements.ocr_text.value = text;
    form.elements.title.value = guessMerchant(text);
    form.elements.amount.value = amountFromOcr(text) ?? '';
    form.elements.due_date.value = dateFromOcr(text) || localDate();
    form.elements.category.value = guessCategory(text);
    setStatus('Text extracted. Verify the description, amount, date, and category before saving.');
  } catch (error) {
    setStatus(error.message, 'error');
    toast('Could not scan automatically. Manual entry remains available.');
  }
});
$id('scanForm').addEventListener('submit', async event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget));
  const payload = {
    name: data.title, amount: data.amount, date: data.due_date, type: data.type,
    category: data.category, notes: data.ocr_text,
    save_as_bill: data.save_as_bill === 'on', frequency: data.frequency || 'Once', provider: data.provider || data.title
  };
  const submit = event.currentTarget.querySelector('button[type="submit"]');
  submit.disabled = true; submit.textContent = 'Saving…';
  try {
    await api('/api/receipts', { method: 'POST', body: JSON.stringify(payload) });
    modal('scanModal', false); toast('Receipt saved to transactions'); await loadBills();
  } catch (error) { toast(error.message); }
  finally { submit.disabled = false; submit.textContent = 'Save transaction'; }
});
loadBills().catch(error => toast(error.message));
