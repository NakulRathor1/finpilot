'use strict';

const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, ch => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[ch]));
const currency = value => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(Number(value || 0));
const localDate = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; };

let dashboardData = null;

async function getJson(url, options = {}) {
  const response = await fetch(url, { ...options, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } });
  const data = await response.json().catch(() => ({ success: false, message: 'Unexpected server response.' }));
  if (response.status === 401) { location.href = '/login'; throw new Error('Please sign in again.'); }
  if (!response.ok || data.success === false) throw new Error(data.message || 'Request failed.');
  return data;
}
function notify(message, error = false) {
  let node = $('#dashboardToast');
  if (!node) { node = document.createElement('div'); node.id = 'dashboardToast'; node.className = 'dashboard-toast'; document.body.appendChild(node); }
  node.textContent = message; node.classList.toggle('error', error); node.classList.add('show');
  window.clearTimeout(notify.timer); notify.timer = window.setTimeout(() => node.classList.remove('show'), 2800);
}
function modal(id, show = true) { document.getElementById(id)?.classList.toggle('show', show); }

async function loadDashboard() {
  try {
    const [data, user] = await Promise.all([getJson(`/api/dashboard?period=${$('#chartFilter').value === 'month' ? 'month' : 'all'}`), getJson('/api/user')]);
    dashboardData = data;
    const summary = data.summary;
    const first = (user.user.name || 'User').trim().split(/\s+/)[0];
    $('#userName').textContent = first;
    $('#profileName').textContent = user.user.name || 'FinPilot Member';
    $('#profileAvatar').textContent = first.charAt(0).toUpperCase() || 'U';
    $('#totalBalance').textContent = currency(summary.total_balance);
    $('#totalIncome').textContent = currency(summary.total_income);
    $('#totalExpenses').textContent = currency(summary.total_expenses);
    $('#totalSavings').textContent = currency(summary.month_savings);
    $('#savingsRate').textContent = `${summary.savings_rate.toFixed(1)}% monthly savings rate`;
    if ($('#investmentValue')) {
      $('#investmentValue').textContent = currency(data.investment_value || 0);
      const gain = Number(data.investment_gain || 0);
      $('#investmentGain').textContent = `${gain >= 0 ? '+' : ''}${currency(gain)} unrealized`;
    }
    $('#healthScore').textContent = summary.financial_score;
    $('#healthLabel').textContent = summary.financial_label;
    $('#healthMessage').textContent = summary.financial_message;
    $('#healthBar').style.width = `${summary.financial_score}%`;
    renderTransactions(data.transactions || []);
    renderGoals(data.goals || []);
    updateBudget(summary);
    renderCategoryChart(data.categories || []);
    renderInsight(summary);
  } catch (error) { notify(error.message, true); }
}
function renderTransactions(transactions) {
  const container = $('#transactionsList');
  if (!transactions.length) {
    container.innerHTML = '<div class="empty-state">No transactions yet.<br>Add your first income or expense.</div>';
    return;
  }
  container.innerHTML = transactions.map(tx => {
    const income = tx.type === 'income';
    return `<div class="transaction-row"><div class="transaction-left"><div class="transaction-icon">${income ? '↗' : '↘'}</div><div><strong>${escapeHtml(tx.name)}</strong><small>${escapeHtml(tx.category)} · ${escapeHtml(tx.date)}</small></div></div><div class="transaction-right"><strong class="${income ? 'income-text' : 'expense-text'}">${income ? '+' : '−'}${currency(tx.amount)}</strong><button class="delete-transaction" data-delete-tx="${tx.id}" title="Delete transaction" aria-label="Delete ${escapeHtml(tx.name)}">×</button></div></div>`;
  }).join('');
}
function renderGoals(goals) {
  const container = $('#goalsList');
  if (!goals.length) { container.innerHTML = '<div class="empty-state">No savings goals yet. Create your first goal to start tracking progress.</div>'; return; }
  container.innerHTML = goals.slice(0, 3).map(goal => {
    const percent = Math.min(100, Number(goal.target) > 0 ? Number(goal.saved) / Number(goal.target) * 100 : 0);
    return `<div class="goal-card"><div class="goal-top"><div class="goal-icon">🎯</div><div><strong>${escapeHtml(goal.name)}</strong><small>${goal.deadline ? `Target date: ${escapeHtml(goal.deadline)}` : 'No deadline set'}</small></div></div><div class="goal-progress"><span style="width:${percent}%"></span></div><div class="goal-bottom"><span>${currency(goal.saved)} saved of ${currency(goal.target)}</span><strong>${Math.round(percent)}%</strong></div></div>`;
  }).join('');
}
function updateBudget(summary) {
  $('#budgetSpent').textContent = currency(summary.budget_spent);
  const progress = $('#budgetProgress');
  const total = Number(summary.budget_total || 0);
  const spent = Number(summary.budget_spent || 0);
  progress.style.width = `${total > 0 ? Math.min(100, spent / total * 100) : 0}%`;
  progress.classList.toggle('over', total > 0 && spent > total);
  $('#budgetStatus').textContent = total > 0 ? (spent <= total ? `${currency(total - spent)} remaining` : `${currency(spent - total)} over budget`) : 'Set category budgets on the Budget page';
}
function renderCategoryChart(categories) {
  const canvas = $('#spendingChart'); const empty = $('#chartEmpty');
  const rows = categories.filter(item => Number(item.amount) > 0).slice(0, 6);
  if (!rows.length) { empty.style.display = 'block'; canvas.style.display = 'none'; return; }
  empty.style.display = 'none'; canvas.style.display = 'block';
  const rect = canvas.getBoundingClientRect(); const dpr = window.devicePixelRatio || 1;
  const width = Math.max(280, rect.width || 520), height = 260;
  canvas.width = width * dpr; canvas.height = height * dpr; canvas.style.height = `${height}px`;
  const ctx = canvas.getContext('2d'); ctx.scale(dpr, dpr); ctx.clearRect(0,0,width,height);
  const styles = getComputedStyle(document.body); const text = styles.getPropertyValue('--text').trim() || '#f2f8f5'; const muted = styles.getPropertyValue('--muted-text').trim() || '#91a69e'; const green = styles.getPropertyValue('--green').trim() || '#37d39b';
  const max = Math.max(...rows.map(r => Number(r.amount)), 1); const labelWidth = Math.min(125, width * .34); const valueWidth = 82; const barWidth = Math.max(40, width - labelWidth - valueWidth - 28); const rowH = Math.min(38, (height - 18) / rows.length);
  ctx.font = '12px Inter, system-ui, sans-serif'; ctx.textBaseline = 'middle';
  rows.forEach((row, index) => {
    const y = 16 + index * rowH; const label = String(row.category || 'Other');
    ctx.fillStyle = muted; ctx.textAlign = 'left'; ctx.fillText(label.length > 18 ? label.slice(0,17)+'…' : label, 0, y + 8);
    const x = labelWidth; ctx.fillStyle = 'rgba(145,166,158,.14)'; ctx.beginPath(); ctx.roundRect(x, y, barWidth, 16, 8); ctx.fill();
    ctx.fillStyle = green; ctx.beginPath(); ctx.roundRect(x, y, Math.max(3, barWidth * Number(row.amount) / max), 16, 8); ctx.fill();
    ctx.fillStyle = text; ctx.textAlign = 'right'; ctx.fillText(currency(row.amount), width, y + 8);
  });
}
function renderInsight(summary) {
  if (summary.month_income <= 0 && summary.month_expenses <= 0) {
    $('#insightTitle').textContent = 'Your financial journey starts here.';
    $('#insightText').textContent = 'Add income and expenses to start seeing your monthly cash flow and spending patterns.';
  } else if (summary.budget_total > 0 && summary.budget_spent > summary.budget_total) {
    $('#insightTitle').textContent = 'Your spending is above the planned budget.';
    $('#insightText').textContent = `${currency(summary.budget_spent - summary.budget_total)} over your combined category budgets this month. Review the Budget page to spot categories to adjust.`;
  } else if (summary.month_savings > 0) {
    $('#insightTitle').textContent = 'You are keeping money after this month’s expenses.';
    $('#insightText').textContent = `Your recorded monthly net is ${currency(summary.month_savings)} (${summary.savings_rate.toFixed(1)}% of income). Keep your categories and recurring bills up to date for a clearer picture.`;
  } else {
    $('#insightTitle').textContent = 'Your recorded expenses are meeting or exceeding income.';
    $('#insightText').textContent = 'Check recent transactions and upcoming bills, then review category budgets to understand the largest pressure points.';
  }
}

function bindPage() {
  const theme = $('#themeToggle');
  if (localStorage.getItem('finpilot-theme') === 'light') document.body.classList.add('light');
  theme?.addEventListener('click', () => {
    document.body.classList.toggle('light');
    localStorage.setItem('finpilot-theme', document.body.classList.contains('light') ? 'light' : 'dark');
    if (dashboardData) renderCategoryChart(dashboardData.categories || []);
  });
  $('#transactionDate').value = localDate();
  $('#openTransactionModal').addEventListener('click', () => { $('#transactionForm').reset(); $('#transactionDate').value = localDate(); modal('transactionModal'); });
  $('#openGoalModal').addEventListener('click', () => { $('#goalForm').reset(); $('#goalSaved').value = '0'; modal('goalModal'); });
  document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => modal(button.dataset.close, false)));
  document.querySelectorAll('.modal').forEach(node => node.addEventListener('click', event => { if (event.target === node) modal(node.id, false); }));
  $('#chartFilter').addEventListener('change', loadDashboard);
  $('#transactionForm').addEventListener('submit', async event => {
    event.preventDefault();
    const payload = { type: $('#transactionType').value, name: $('#transactionName').value.trim(), category: $('#transactionCategory').value, amount: $('#transactionAmount').value, date: $('#transactionDate').value };
    try { await getJson('/api/transactions', { method: 'POST', body: JSON.stringify(payload) }); modal('transactionModal', false); notify('Transaction saved'); await loadDashboard(); }
    catch (error) { notify(error.message, true); }
  });
  $('#goalForm').addEventListener('submit', async event => {
    event.preventDefault();
    const payload = { name: $('#goalName').value.trim(), target: $('#goalTarget').value, saved: $('#goalSaved').value || 0, deadline: $('#goalDeadline').value || null };
    try { await getJson('/api/goals', { method: 'POST', body: JSON.stringify(payload) }); modal('goalModal', false); notify('Savings goal created'); await loadDashboard(); }
    catch (error) { notify(error.message, true); }
  });
  $('#transactionsList').addEventListener('click', async event => {
    const button = event.target.closest('[data-delete-tx]'); if (!button) return;
    if (!confirm('Delete this transaction?')) return;
    try { await getJson(`/api/transactions/${button.dataset.deleteTx}`, { method: 'DELETE' }); notify('Transaction deleted'); await loadDashboard(); }
    catch (error) { notify(error.message, true); }
  });
  window.addEventListener('resize', () => { if (dashboardData) renderCategoryChart(dashboardData.categories || []); });
}
document.addEventListener('DOMContentLoaded', () => { bindPage(); loadDashboard(); });
