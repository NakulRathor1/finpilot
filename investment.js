'use strict';

let investments = [];
let activeInvestmentId = null;
let searchTimer = null;

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('addInvestmentBtn')?.addEventListener('click', () => openInvestmentModal());
  document.getElementById('investmentForm')?.addEventListener('submit', submitInvestmentForm);
  document.getElementById('assetName')?.addEventListener('input', onAssetSearchInput);
  document.getElementById('fetchQuoteBtn')?.addEventListener('click', fetchQuoteForForm);
  document.getElementById('refreshPricesBtn')?.addEventListener('click', refreshAllPrices);
  document.getElementById('tradeForm')?.addEventListener('submit', submitTradeForm);
  document.querySelectorAll('[data-close-modal]').forEach(btn => {
    btn.addEventListener('click', () => closeModal(btn.dataset.closeModal));
  });
  document.querySelectorAll('.modal').forEach(node => {
    node.addEventListener('click', e => { if (e.target === node) closeModal(node.id); });
  });
  setDefaultInvestmentDate();
  loadInvestments();
});

function setDefaultInvestmentDate() {
  const input = document.getElementById('purchaseDate');
  if (input) input.value = todayLocal();
}

function todayLocal() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

function openModal(id) {
  const modal = document.getElementById(id);
  if (!modal) return;
  modal.classList.add('show', 'open');
  modal.style.display = 'flex';
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (!modal) return;
  modal.classList.remove('show', 'open');
  modal.style.display = '';
  document.getElementById('marketSearchResults')?.classList.remove('open');
}

function openInvestmentModal(editItem = null) {
  const form = document.getElementById('investmentForm');
  form.reset();
  setDefaultInvestmentDate();
  document.getElementById('investmentId').value = '';
  document.getElementById('quoteSource').value = 'manual';
  document.getElementById('modalTitle').textContent = 'Add Investment';
  document.getElementById('submitInvestmentBtn').textContent = 'Add Investment';
  document.getElementById('quantityField').style.display = '';
  document.getElementById('buyPriceField').style.display = '';
  document.getElementById('purchaseDateField').style.display = '';
  document.getElementById('assetQuantity').required = true;
  document.getElementById('buyPrice').required = true;
  document.getElementById('purchaseDate').required = true;

  if (editItem) {
    document.getElementById('modalTitle').textContent = 'Edit Investment';
    document.getElementById('submitInvestmentBtn').textContent = 'Save changes';
    document.getElementById('investmentId').value = editItem.id;
    document.getElementById('assetType').value = editItem.asset_type;
    document.getElementById('assetName').value = editItem.asset_name;
    document.getElementById('assetSymbol').value = editItem.symbol || '';
    document.getElementById('currentPrice').value = editItem.current_price;
    document.getElementById('quoteSource').value = editItem.quote_source || 'manual';
    document.getElementById('quantityField').style.display = 'none';
    document.getElementById('buyPriceField').style.display = 'none';
    document.getElementById('purchaseDateField').style.display = 'none';
    document.getElementById('assetQuantity').required = false;
    document.getElementById('buyPrice').required = false;
    document.getElementById('purchaseDate').required = false;
  }

  openModal('investmentModal');
  setTimeout(() => document.getElementById('assetName')?.focus(), 80);
}

function closeInvestmentModal() {
  closeModal('investmentModal');
}

async function onAssetSearchInput(e) {
  const q = e.target.value.trim();
  const box = document.getElementById('marketSearchResults');
  if (!box) return;
  clearTimeout(searchTimer);
  if (q.length < 1) {
    box.classList.remove('open');
    box.innerHTML = '';
    return;
  }
  searchTimer = setTimeout(async () => {
    try {
      const data = await api(`/api/investments/catalog?q=${encodeURIComponent(q)}`);
      const results = data.results || [];
      if (!results.length) {
        box.innerHTML = '<div class="search-item muted">No catalog match — enter details manually.</div>';
        box.classList.add('open');
        return;
      }
      box.innerHTML = results.map(r => `
        <button type="button" class="search-item" data-name="${escapeAttr(r.asset_name)}" data-type="${escapeAttr(r.asset_type)}" data-symbol="${escapeAttr(r.symbol || '')}" data-source="${escapeAttr(r.quote_source || 'manual')}">
          <strong>${escapeInvestment(r.asset_name)}</strong>
          <span class="muted">${escapeInvestment(r.asset_type)}${r.symbol ? ' · ' + escapeInvestment(r.symbol) : ''}</span>
        </button>
      `).join('');
      box.classList.add('open');
      box.querySelectorAll('.search-item[data-name]').forEach(btn => {
        btn.addEventListener('click', () => {
          document.getElementById('assetName').value = btn.dataset.name;
          document.getElementById('assetType').value = btn.dataset.type;
          document.getElementById('assetSymbol').value = btn.dataset.symbol || '';
          document.getElementById('quoteSource').value = btn.dataset.source || 'manual';
          box.classList.remove('open');
          if (btn.dataset.symbol) fetchQuoteForForm();
        });
      });
    } catch (err) {
      box.innerHTML = '<div class="search-item muted">Search unavailable — enter manually.</div>';
      box.classList.add('open');
    }
  }, 220);
}

async function fetchQuoteForForm() {
  const symbol = document.getElementById('assetSymbol').value.trim();
  const status = document.getElementById('quoteStatus');
  if (!symbol) {
    if (status) status.textContent = 'Enter a symbol to fetch a quote, or set the price manually.';
    return;
  }
  if (status) status.textContent = 'Fetching quote…';
  try {
    const data = await api(`/api/investments/quote?symbol=${encodeURIComponent(symbol)}`);
    if (data.success && data.price != null) {
      document.getElementById('currentPrice').value = data.price;
      const buy = document.getElementById('buyPrice');
      if (buy && !buy.value) buy.value = data.price;
      document.getElementById('quoteSource').value = data.source || 'yahoo';
      if (status) status.textContent = `Quote: ${data.price} · ${data.source} · ${data.fetched_at || ''}`;
    } else {
      if (status) status.textContent = data.message || 'Quote unavailable. Enter price manually.';
    }
  } catch (err) {
    if (status) status.textContent = err.message || 'Quote fetch failed. Enter price manually.';
  }
}

async function submitInvestmentForm(event) {
  event.preventDefault();
  const id = document.getElementById('investmentId').value;
  const submitBtn = document.getElementById('submitInvestmentBtn');
  submitBtn.disabled = true;

  try {
    if (id) {
      const payload = {
        asset_type: document.getElementById('assetType').value,
        asset_name: document.getElementById('assetName').value.trim(),
        symbol: document.getElementById('assetSymbol').value.trim(),
        current_price: Number(document.getElementById('currentPrice').value),
        quote_source: document.getElementById('quoteSource').value || 'manual'
      };
      await api(`/api/investments/${id}`, { method: 'PATCH', body: JSON.stringify(payload) });
      showInvestmentToast('Investment updated.');
    } else {
      const payload = {
        asset_type: document.getElementById('assetType').value,
        asset_name: document.getElementById('assetName').value.trim(),
        symbol: document.getElementById('assetSymbol').value.trim(),
        quantity: Number(document.getElementById('assetQuantity').value),
        buy_price: Number(document.getElementById('buyPrice').value),
        current_price: Number(document.getElementById('currentPrice').value),
        purchase_date: document.getElementById('purchaseDate').value,
        quote_source: document.getElementById('quoteSource').value || 'manual'
      };
      await api('/api/investments', { method: 'POST', body: JSON.stringify(payload) });
      showInvestmentToast('Investment added.');
    }
    closeInvestmentModal();
    await loadInvestments();
  } catch (error) {
    showInvestmentToast(error.message || 'Could not save investment.', true);
  } finally {
    submitBtn.disabled = false;
  }
}

async function loadInvestments() {
  try {
    const data = await api('/api/investments');
    investments = data.investments || [];
    renderSummary();
    renderInvestments();
    renderCategoryPerformance();
    renderDistribution();
  } catch (error) {
    showInvestmentToast(error.message || 'Unable to load investments.', true);
  }
}

function renderSummary() {
  let invested = 0, current = 0;
  investments.forEach(item => {
    invested += Number(item.invested_value);
    current += Number(item.current_value);
  });
  const profit = current - invested;
  const returnPercent = invested > 0 ? (profit / invested) * 100 : 0;
  document.getElementById('totalInvested').textContent = formatINR(invested);
  document.getElementById('currentValue').textContent = formatINR(current);
  document.getElementById('totalProfit').textContent = formatINR(profit);
  document.getElementById('overallReturn').textContent = returnPercent.toFixed(2) + '%';
  setProfitClass(document.getElementById('totalProfit'), profit);
  setProfitClass(document.getElementById('overallReturn'), returnPercent);
}

function renderInvestments() {
  const container = document.getElementById('investmentList');
  if (!investments.length) {
    container.innerHTML = `
      <div class="empty-investments">
        <h3>No investments yet</h3>
        <p>Add your first investment to start tracking your portfolio.</p>
      </div>`;
    return;
  }

  container.innerHTML = investments.map(item => {
    const profit = Number(item.current_value) - Number(item.invested_value);
    const returnPercent = Number(item.invested_value) > 0 ? (profit / Number(item.invested_value)) * 100 : 0;
    const updated = item.price_updated_at ? ` · ${escapeInvestment(item.quote_source || 'manual')} ${escapeInvestment(String(item.price_updated_at).slice(0, 16))}` : '';
    return `
      <div class="investment-row">
        <div class="investment-info">
          <div class="asset-icon">${getAssetIcon(item.asset_type)}</div>
          <div>
            <h3>${escapeInvestment(item.asset_name)}</h3>
            <p>${escapeInvestment(item.asset_type)}${item.symbol ? ' · ' + escapeInvestment(item.symbol) : ''}${updated}</p>
          </div>
        </div>
        <div class="investment-data"><small>Quantity</small><strong>${Number(item.quantity)}</strong></div>
        <div class="investment-data"><small>Avg cost</small><strong>${formatINR(item.buy_price)}</strong></div>
        <div class="investment-data"><small>Current</small><strong>${formatINR(item.current_price)}</strong></div>
        <div class="investment-data"><small>Invested</small><strong>${formatINR(item.invested_value)}</strong></div>
        <div class="investment-data"><small>Value</small><strong>${formatINR(item.current_value)}</strong></div>
        <div class="investment-performance ${profit >= 0 ? 'profit' : 'loss'}">
          <strong>${profit >= 0 ? '+' : '−'}${formatINR(Math.abs(profit))}</strong>
          <span>${returnPercent >= 0 ? '+' : ''}${returnPercent.toFixed(2)}%</span>
        </div>
        <div class="investment-actions">
          <button type="button" class="secondary inv-action" data-action="edit" data-id="${item.id}" title="Edit">✎</button>
          <button type="button" class="secondary inv-action" data-action="buy" data-id="${item.id}" title="Buy more">+</button>
          <button type="button" class="secondary inv-action" data-action="sell" data-id="${item.id}" title="Sell">−</button>
          <button type="button" class="secondary inv-action" data-action="history" data-id="${item.id}" title="History">☰</button>
          <button type="button" class="delete-investment inv-action" data-action="delete" data-id="${item.id}" title="Delete">×</button>
        </div>
      </div>`;
  }).join('');

  container.querySelectorAll('.inv-action').forEach(btn => {
    btn.addEventListener('click', () => handleInvestmentAction(btn.dataset.action, Number(btn.dataset.id)));
  });
}

async function handleInvestmentAction(action, id) {
  const item = investments.find(x => x.id === id);
  if (!item && action !== 'delete') return;
  if (action === 'edit') {
    openInvestmentModal(item);
  } else if (action === 'buy') {
    openTradeModal(item, 'buy');
  } else if (action === 'sell') {
    openTradeModal(item, 'sell');
  } else if (action === 'history') {
    await openHistoryModal(item);
  } else if (action === 'delete') {
    if (!confirm('Delete this investment and its history?')) return;
    try {
      await api(`/api/investments/${id}`, { method: 'DELETE' });
      showInvestmentToast('Investment deleted.');
      await loadInvestments();
    } catch (error) {
      showInvestmentToast(error.message, true);
    }
  }
}

function openTradeModal(item, action) {
  activeInvestmentId = item.id;
  document.getElementById('tradeAction').value = action;
  document.getElementById('tradeTitle').textContent = action === 'buy' ? `Buy more · ${item.asset_name}` : `Sell · ${item.asset_name}`;
  document.getElementById('tradeHint').textContent = action === 'buy'
    ? `Held: ${item.quantity}. New buys update your average cost.`
    : `Held: ${item.quantity}. You cannot sell more than you hold.`;
  document.getElementById('tradeQuantity').value = '';
  document.getElementById('tradePrice').value = item.current_price;
  document.getElementById('tradeDate').value = todayLocal();
  document.getElementById('tradeNotes').value = '';
  openModal('tradeModal');
}

async function submitTradeForm(event) {
  event.preventDefault();
  const action = document.getElementById('tradeAction').value;
  const id = activeInvestmentId;
  const payload = {
    quantity: Number(document.getElementById('tradeQuantity').value),
    price: Number(document.getElementById('tradePrice').value),
    date: document.getElementById('tradeDate').value,
    notes: document.getElementById('tradeNotes').value.trim()
  };
  const btn = event.target.querySelector('button[type="submit"]');
  btn.disabled = true;
  try {
    await api(`/api/investments/${id}/${action}`, { method: 'POST', body: JSON.stringify(payload) });
    showInvestmentToast(action === 'buy' ? 'Purchase recorded.' : 'Sale recorded.');
    closeModal('tradeModal');
    await loadInvestments();
  } catch (error) {
    showInvestmentToast(error.message, true);
  } finally {
    btn.disabled = false;
  }
}

async function openHistoryModal(item) {
  document.getElementById('historyTitle').textContent = `History · ${item.asset_name}`;
  document.getElementById('historyBody').innerHTML = '<p class="muted">Loading…</p>';
  openModal('historyModal');
  try {
    const data = await api(`/api/investments/${item.id}/history`);
    const rows = data.history || [];
    if (!rows.length) {
      document.getElementById('historyBody').innerHTML = '<p class="muted">No transactions recorded yet.</p>';
      return;
    }
    document.getElementById('historyBody').innerHTML = `
      <div class="table-wrap"><table>
        <thead><tr><th>Date</th><th>Action</th><th>Qty</th><th>Price</th><th>Amount</th><th>Notes</th></tr></thead>
        <tbody>
          ${rows.map(r => `<tr>
            <td>${escapeInvestment(r.date)}</td>
            <td><span class="pill">${escapeInvestment(r.action)}</span></td>
            <td>${Number(r.quantity)}</td>
            <td>${formatINR(r.price)}</td>
            <td>${formatINR(r.amount)}</td>
            <td>${escapeInvestment(r.notes || '')}</td>
          </tr>`).join('')}
        </tbody>
      </table></div>`;
  } catch (error) {
    document.getElementById('historyBody').innerHTML = `<p class="status-error">${escapeInvestment(error.message)}</p>`;
  }
}

async function refreshAllPrices() {
  const btn = document.getElementById('refreshPricesBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Refreshing…'; }
  try {
    const data = await api('/api/investments/refresh-prices', { method: 'POST', body: '{}' });
    showInvestmentToast(data.message || 'Prices refreshed.');
    await loadInvestments();
  } catch (error) {
    showInvestmentToast(error.message || 'Could not refresh prices.', true);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '↻ Refresh prices'; }
  }
}

function renderCategoryPerformance() {
  const container = document.getElementById('categoryPerformance');
  const categories = {};
  investments.forEach(item => {
    const category = item.asset_type;
    if (!categories[category]) categories[category] = { invested: 0, current: 0 };
    categories[category].invested += Number(item.invested_value);
    categories[category].current += Number(item.current_value);
  });
  if (!Object.keys(categories).length) {
    container.innerHTML = '<p class="muted">No category data available.</p>';
    return;
  }
  container.innerHTML = Object.entries(categories).map(([name, data]) => {
    const profit = data.current - data.invested;
    const percentage = data.invested > 0 ? (profit / data.invested) * 100 : 0;
    return `
      <div class="category-row">
        <div><strong>${escapeInvestment(name)}</strong><small>Invested ${formatINR(data.invested)}</small></div>
        <div class="${profit >= 0 ? 'profit' : 'loss'}">
          <strong>${profit >= 0 ? '+' : '−'}${formatINR(Math.abs(profit))}</strong>
          <small>${percentage >= 0 ? '+' : ''}${percentage.toFixed(2)}%</small>
        </div>
      </div>`;
  }).join('');
}

function renderDistribution() {
  const container = document.getElementById('portfolioDistribution');
  if (!investments.length) {
    container.innerHTML = '<p class="muted">No portfolio data available.</p>';
    return;
  }
  const categories = {};
  let total = 0;
  investments.forEach(item => {
    const value = Number(item.current_value);
    categories[item.asset_type] = (categories[item.asset_type] || 0) + value;
    total += value;
  });
  container.innerHTML = Object.entries(categories).map(([name, value]) => {
    const percentage = total > 0 ? (value / total) * 100 : 0;
    return `
      <div class="distribution-row">
        <div class="distribution-title"><span>${escapeInvestment(name)}</span><strong>${percentage.toFixed(1)}%</strong></div>
        <div class="distribution-bar"><div style="width:${percentage}%"></div></div>
      </div>`;
  }).join('');
}

async function analyzePortfolio() {
  const result = document.getElementById('aiResult');
  if (!investments.length) {
    result.innerHTML = 'Add investments first so FinPilot AI can analyze your portfolio.';
    return;
  }
  result.innerHTML = '<p>✦ FinPilot AI is analyzing your portfolio...</p>';
  try {
    const data = await api('/api/investments/ai-analysis');
    if (!data.success) {
      result.innerHTML = data.message || 'AI analysis unavailable.';
      return;
    }
    result.innerHTML = `
      <div class="ai-insights">
        <div class="ai-insight"><strong>Portfolio Overview</strong><p>${escapeInvestment(data.analysis.overview)}</p></div>
        <div class="ai-insight"><strong>Diversification</strong><p>${escapeInvestment(data.analysis.diversification)}</p></div>
        <div class="ai-insight"><strong>Risk Signal</strong><p>${escapeInvestment(data.analysis.risk)}</p></div>
        <div class="ai-insight"><strong>Performance</strong><p>${escapeInvestment(data.analysis.performance)}</p></div>
        <div class="ai-insight"><strong>Suggested Action</strong><p>${escapeInvestment(data.analysis.suggestion)}</p></div>
        <div class="ai-disclaimer">AI insights are educational and based on your portfolio data. They are not investment advice.</div>
      </div>`;
  } catch (error) {
    result.innerHTML = 'Unable to generate AI analysis.';
  }
}

function formatINR(value) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency', currency: 'INR', maximumFractionDigits: 2
  }).format(Number(value) || 0);
}

function setProfitClass(element, value) {
  element.classList.remove('profit', 'loss');
  if (value > 0) element.classList.add('profit');
  else if (value < 0) element.classList.add('loss');
}

function getAssetIcon(type) {
  const icons = {
    Stocks: '📈', Gold: '🪙', Silver: '🥈', 'Mutual Funds': '📊', Bonds: '🏦', Crypto: '₿', Other: '💼'
  };
  return icons[type] || '💼';
}

function escapeInvestment(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function escapeAttr(value) {
  return escapeInvestment(value);
}

function showInvestmentToast(message, error = false) {
  const toast = document.getElementById('investmentToast');
  if (!toast) return;
  toast.textContent = message;
  toast.className = 'investment-toast toast show' + (error ? ' error' : '');
  setTimeout(() => toast.classList.remove('show'), 3200);
}
