const state = {
  products: [], transactions: [], events: [], stats: {}, config: {},
  page: 'dashboard', selectedProductId: 'watch-pro', negotiated: null,
  transcript: [], selectedTransactionId: null, toastTimer: null
};

const $ = (selector) => document.querySelector(selector);
const money = (amount) => new Intl.NumberFormat('en-US', {style:'currency', currency:'USD'}).format(Number(amount || 0));
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const timeAgo = (iso) => {
  const date = new Date(iso);
  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds/60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds/3600)}h ago`;
  return date.toLocaleDateString();
};
const dateTime = (iso) => new Date(iso).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});

async function api(url, options={}) {
  const response = await fetch(url, {
    headers: {'Content-Type':'application/json', ...(options.headers || {})},
    ...options
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function toast(message) {
  const el = $('#toast');
  el.textContent = message;
  el.classList.add('show');
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => el.classList.remove('show'), 3200);
}

function navigate(page) {
  state.page = page;
  document.querySelectorAll('.page').forEach(el => el.classList.toggle('active', el.id === `page-${page}`));
  document.querySelectorAll('.nav-item').forEach(el => el.classList.toggle('active', el.dataset.page === page));
  const titles = {dashboard:'Overview',buyer:'Buyer agent',merchant:'Merchant shield',activity:'Audit timeline'};
  $('#breadcrumb-current').textContent = titles[page] || 'Overview';
  window.scrollTo({top:0,behavior:'smooth'});
  if (page === 'merchant') renderTransactions();
}

function productById(id) { return state.products.find(item => item.id === id); }

function renderStats() {
  const s = state.stats;
  $('#stat-total').textContent = s.total_transactions ?? 0;
  $('#stat-approved').textContent = s.approved_transactions ?? 0;
  $('#stat-review').textContent = s.review_queue ?? 0;
  $('#stat-volume').textContent = money(s.gross_volume);
  $('#nav-review-count').textContent = s.review_queue ?? 0;
  $('#merchant-approved').textContent = s.cleared_transactions ?? s.approved_transactions ?? 0;
  $('#merchant-review').textContent = s.review_queue ?? 0;
  $('#merchant-rate').textContent = `${s.approval_rate ?? 0}%`;
  const scoreValues = state.transactions.map(tx => Number(tx.risk_score || 0));
  const avg = scoreValues.length ? Math.round(scoreValues.reduce((a,b)=>a+b,0)/scoreValues.length) : 0;
  $('#risk-meter-value').textContent = avg;
  $('#risk-meter-fill').style.background = `conic-gradient(#2867e8 0deg ${avg*3.6}deg, #e9eef6 ${avg*3.6}deg 360deg)`;
  $('#risk-summary-title').textContent = avg >= 60 ? 'Elevated risk signals' : avg >= 30 ? 'A few orders need attention' : 'Risk signals look controlled';
}

function riskClass(level) { return `risk-${String(level || 'low').toLowerCase()}`; }
function statusClass(status) { return `status-${String(status || '').toLowerCase()}`; }
function statusLabel(status) {
  return ({APPROVED:'Approved', REVIEW_REQUIRED:'Review required', RESOLVED:'Resolved'})[status] || status || 'Unknown';
}

function txRow(tx, compact=false) {
  const buyerProduct = `<div class="buyer-cell"><strong>${escapeHtml(tx.buyer)}</strong><small>${escapeHtml(tx.product_name)} · Qty ${tx.quantity}</small></div>`;
  if (compact) return `<tr data-tx="${escapeHtml(tx.id)}"><td><span class="tx-id">${escapeHtml(tx.id)}</span></td><td>${buyerProduct}</td><td class="amount-cell">${money(tx.total)}</td><td><span class="risk-pill ${riskClass(tx.risk_level)}">${escapeHtml(tx.risk_level)} · ${tx.risk_score}</span></td><td><span class="status-pill ${statusClass(tx.status)}">${escapeHtml(statusLabel(tx.status))}</span></td></tr>`;
  return `<tr data-tx="${escapeHtml(tx.id)}"><td><span class="tx-id">${escapeHtml(tx.id)}</span></td><td>${escapeHtml(tx.buyer)}</td><td>${escapeHtml(tx.product_name)}</td><td class="amount-cell">${money(tx.total)}</td><td><span class="risk-pill ${riskClass(tx.risk_level)}">${escapeHtml(tx.risk_level)}</span></td><td><span class="status-pill ${statusClass(tx.status)}">${escapeHtml(statusLabel(tx.status))}</span></td></tr>`;
}

function renderRecent() {
  const rows = state.transactions.slice(0,5);
  $('#recent-rows').innerHTML = rows.length ? rows.map(tx => txRow(tx, false)).join('') : '<tr><td colspan="6">No transactions yet. Run a buyer checkout to create one.</td></tr>';
  $('#recent-rows').querySelectorAll('tr[data-tx]').forEach(row => row.addEventListener('click', () => {
    state.selectedTransactionId = row.dataset.tx;
    navigate('merchant');
    loadTransactionDetail(row.dataset.tx);
  }));
}

function renderProducts() {
  $('#product-grid').innerHTML = state.products.map(product => `
    <article class="product-card ${product.id === state.selectedProductId ? 'selected' : ''}" data-product="${escapeHtml(product.id)}">
      <div class="product-visual visual-${escapeHtml(product.color)}"><span class="product-tag">${escapeHtml(product.tag)}</span><span class="product-symbol">${escapeHtml(product.icon)}</span></div>
      <div class="product-info"><div class="product-category">${escapeHtml(product.category)}</div><h3>${escapeHtml(product.name)}</h3><p>${escapeHtml(product.description)}</p><div class="product-price-row"><span class="product-price">${money(product.price)}</span><span class="select-product">${product.id === state.selectedProductId ? 'SELECTED ✓' : 'SELECT ↗'}</span></div></div>
    </article>`).join('');
  $('#product-grid').querySelectorAll('[data-product]').forEach(card => card.addEventListener('click', () => selectProduct(card.dataset.product)));
  renderSelectedProduct();
}

function selectProduct(id) {
  if (!productById(id)) return;
  state.selectedProductId = id;
  state.negotiated = null;
  state.transcript = [];
  $('#buyer-message').value = '';
  $('#chat-area').innerHTML = '<div class="chat-date">TODAY · NEGOTIATION SESSION</div><div class="chat-bubble agent-bubble"><div class="bubble-label">PAYAGENT</div>Great choice. Tell me your target price or ask for your best member deal.</div>';
  $('#negotiated-price').textContent = '—';
  $('#negotiated-saving').textContent = 'Start a negotiation';
  $('#checkout-button').disabled = true;
  renderProducts();
}

function renderSelectedProduct() {
  const product = productById(state.selectedProductId);
  if (!product) return;
  $('#selected-product').innerHTML = `<div><strong>${escapeHtml(product.name)}</strong><small>${escapeHtml(product.category)} · List price</small></div><b>${money(product.price)}</b>`;
}

function appendChat(role, text) {
  const bubble = document.createElement('div');
  bubble.className = `chat-bubble ${role === 'buyer' ? 'buyer-bubble' : 'agent-bubble'}`;
  bubble.innerHTML = `<div class="bubble-label">${role === 'buyer' ? 'YOU' : 'PAYAGENT'}</div>${escapeHtml(text)}`;
  $('#chat-area').appendChild(bubble);
  $('#chat-area').scrollTop = $('#chat-area').scrollHeight;
}

async function sendOffer(useBestPrice=false) {
  const product = productById(state.selectedProductId);
  if (!product) return;
  const message = useBestPrice ? '' : $('#buyer-message').value.trim();
  if (!useBestPrice && !message) { toast('Enter a price offer or message first.'); return; }
  const quantity = Number($('#buyer-quantity').value || 1);
  if (!useBestPrice) appendChat('buyer', message);
  $('#send-offer').disabled = true;
  try {
    const result = await api('/api/negotiate', {method:'POST', body:JSON.stringify({product_id:product.id, quantity, message})});
    appendChat('agent', `${result.headline}. ${result.message}`);
    state.negotiated = result;
    state.transcript = [...state.transcript, ...result.transcript];
    $('#negotiated-price').textContent = money(result.suggested_price);
    $('#negotiated-saving').textContent = result.savings_per_item > 0 ? `Save ${money(result.savings_per_item)} / item` : 'Best available member price';
    $('#checkout-button').disabled = false;
    $('#buyer-message').value = '';
    renderSelectedProduct();
    if (result.decision === 'COUNTER_OFFER') toast('The agent returned a counter-offer.');
  } catch (error) { toast(error.message); }
  finally { $('#send-offer').disabled = false; }
}

async function checkout() {
  if (!state.negotiated) { toast('Negotiate a price before checkout.'); return; }
  const product = productById(state.selectedProductId);
  const button = $('#checkout-button');
  button.disabled = true;
  button.textContent = 'Processing checkout…';
  try {
    const result = await api('/api/checkout', {method:'POST', body:JSON.stringify({
      product_id:product.id,
      quantity:Number($('#buyer-quantity').value || 1),
      unit_price:state.negotiated.suggested_price,
      buyer_message:state.transcript.filter(x=>x.role==='buyer').map(x=>x.text).join(' | '),
      transcript:state.transcript,
      device_new:$('#flag-new-device').checked,
      country_mismatch:$('#flag-country').checked
    })});
    if (result.paypal && result.approve_url) {
      toast('Opening PayPal Sandbox approval…');
      window.location.href = result.approve_url;
      return;
    }
    await refreshState();
    toast(`${result.message} Transaction ${result.id} · Risk ${result.risk.level}.`);
    state.selectedTransactionId = result.id;
    navigate('merchant');
    await loadTransactionDetail(result.id);
    button.textContent = 'Continue to checkout →';
  } catch (error) {
    toast(error.message);
    button.disabled = false;
    button.innerHTML = 'Continue to checkout <span>→</span>';
  }
}

async function runRiskyDemo() {
  selectProduct('watch-pro');
  $('#buyer-quantity').value = '5';
  $('#flag-new-device').checked = true;
  $('#flag-country').checked = true;
  await sendOffer(true);
  if (state.negotiated) {
    toast('High-risk scenario prepared. Continue to checkout to send it to merchant review.');
  }
}

function renderTransactions() {
  const search = ($('#transaction-search')?.value || '').trim().toLowerCase();
  const filter = $('#status-filter')?.value || 'ALL';
  const filtered = state.transactions.filter(tx => {
    const matchesText = !search || [tx.id,tx.buyer,tx.product_name].some(value => String(value).toLowerCase().includes(search));
    const matchesStatus = filter === 'ALL' || tx.status === filter;
    return matchesText && matchesStatus;
  });
  $('#transaction-rows').innerHTML = filtered.length ? filtered.map(tx => txRow(tx,true)).join('') : '<tr><td colspan="5" style="padding:22px;text-align:center;color:#98a3b3">No matching transactions.</td></tr>';
  $('#grid-count').textContent = `${filtered.length} transaction${filtered.length === 1 ? '' : 's'}`;
  $('#transaction-rows').querySelectorAll('tr[data-tx]').forEach(row => row.addEventListener('click', () => {
    state.selectedTransactionId = row.dataset.tx;
    $('#transaction-rows').querySelectorAll('tr').forEach(el => el.classList.toggle('selected-row', el.dataset.tx === state.selectedTransactionId));
    loadTransactionDetail(state.selectedTransactionId);
  }));
  if (state.selectedTransactionId) {
    const selected = $('#transaction-rows').querySelector(`[data-tx="${CSS.escape(state.selectedTransactionId)}"]`);
    if (selected) selected.classList.add('selected-row');
  }
}

async function loadTransactionDetail(txId) {
  try {
    const data = await api(`/api/transactions/${encodeURIComponent(txId)}`);
    renderTransactionDetail(data.transaction, data.events);
  } catch (error) { toast(error.message); }
}

function renderTransactionDetail(tx, events) {
  const reasons = tx.risk_reasons.map(reason => `<li>${escapeHtml(reason)}</li>`).join('');
  const evidence = tx.evidence.map(item => `<div class="evidence-row"><span>${escapeHtml(item.label)}</span><strong>${escapeHtml(item.value)}</strong></div>`).join('');
  const width = Math.max(3, Math.min(100, tx.risk_score));
  const color = tx.risk_level === 'HIGH' ? '#d65b58' : tx.risk_level === 'MEDIUM' ? '#e1a04a' : '#21a57c';
  const isReview = tx.status === 'REVIEW_REQUIRED';
  $('#transaction-detail').innerHTML = `
    <div class="detail-top"><div><div class="eyebrow">ORDER INSPECTION</div><h3>${escapeHtml(tx.id)}</h3><p>${escapeHtml(tx.buyer)} · ${dateTime(tx.created_at)}</p></div><span class="status-pill ${statusClass(tx.status)}">${escapeHtml(statusLabel(tx.status))}</span></div>
    <div class="detail-amount">${money(tx.total)}</div><div class="detail-sub">${escapeHtml(tx.product_name)} · ${tx.quantity} item(s) · ${money(tx.unit_price)} each</div>
    <div class="detail-risk-card"><div class="detail-risk-head"><strong>AI Grid risk assessment</strong><span class="risk-score" style="color:${color}">${tx.risk_score}/100</span></div><div class="risk-bar"><span style="width:${width}%;background:${color}"></span></div><ul class="risk-reasons">${reasons}</ul></div>
    <div class="detail-section-title">EVIDENCE SNAPSHOT</div><div class="evidence-list">${evidence}</div>
    <div class="detail-section-title">AUDIT EVENTS · ${events.length}</div><div class="evidence-list">${events.slice(-4).map(e=>`<div class="evidence-row"><span>${escapeHtml(e.event_type.replaceAll('_',' '))}</span><strong>${escapeHtml(e.detail)}</strong></div>`).join('')}</div>
    <div class="detail-actions"><button class="evidence-button" id="download-evidence">↓ Export evidence</button><button class="resolve-button" id="resolve-transaction" ${!isReview?'disabled style="opacity:.45;cursor:not-allowed"':''}>✓ Mark resolved</button></div>
    <button class="text-button" id="request-evidence" style="margin-top:10px">Request additional evidence →</button>`;
  $('#download-evidence').addEventListener('click', () => downloadEvidence(tx.id));
  $('#resolve-transaction').addEventListener('click', () => resolveTransaction(tx.id));
  $('#request-evidence').addEventListener('click', () => requestEvidence(tx.id));
}

async function resolveTransaction(txId) {
  try {
    const result = await api(`/api/transactions/${encodeURIComponent(txId)}/action`, {method:'POST',body:JSON.stringify({action:'resolve'})});
    toast(result.message);
    await refreshState();
    await loadTransactionDetail(txId);
    renderTransactions();
  } catch (error) { toast(error.message); }
}

async function requestEvidence(txId) {
  try {
    const result = await api(`/api/transactions/${encodeURIComponent(txId)}/action`, {method:'POST',body:JSON.stringify({action:'request_evidence'})});
    toast(result.message);
    await refreshState();
    await loadTransactionDetail(txId);
  } catch (error) { toast(error.message); }
}

async function downloadEvidence(txId) {
  try {
    const packet = await api(`/api/transactions/${encodeURIComponent(txId)}/evidence`);
    const blob = new Blob([JSON.stringify(packet,null,2)], {type:'application/json'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = `payagent-evidence-${txId}.json`; a.click();
    URL.revokeObjectURL(url);
    toast('Evidence packet exported as JSON.');
  } catch (error) { toast(error.message); }
}

function renderActivity() {
  const events = state.events;
  $('#activity-list').innerHTML = events.length ? events.map(event => `
    <div class="activity-item"><div class="activity-icon">${event.event_type.includes('RISK') || event.event_type.includes('SHIELD') ? '⬡' : event.event_type.includes('PAYMENT') ? '$' : '✓'}</div><div class="activity-copy"><strong>${escapeHtml(event.event_type.replaceAll('_',' '))} · ${escapeHtml(event.transaction_id)}</strong><p>${escapeHtml(event.detail)}</p><small>${dateTime(event.created_at)}</small></div><div class="activity-time">${timeAgo(event.created_at)}</div></div>`).join('') : '<p style="color:#98a3b3;font-size:10px">No audit events yet.</p>';
}

async function refreshState() {
  const data = await api('/api/state');
  state.products = data.products || [];
  state.transactions = data.transactions || [];
  state.events = data.events || [];
  state.stats = data.stats || {};
  state.config = data.config || {};
  renderStats(); renderRecent(); renderTransactions(); renderActivity();
  if (state.products.length && !productById(state.selectedProductId)) state.selectedProductId = state.products[0].id;
  renderProducts();
}

async function resetDemo() {
  if (!window.confirm('Reset all demo transactions and restore the sample data?')) return;
  try {
    await api('/api/reset-demo', {method:'POST',body:JSON.stringify({})});
    state.selectedTransactionId = null;
    await refreshState();
    $('#transaction-detail').innerHTML = '<div class="empty-detail"><div class="empty-shield">⬡</div><h3>Select a transaction</h3><p>Choose an order from the grid to inspect its risk analysis, timeline and evidence packet.</p></div>';
    toast('Demo data reset to the original sample transactions.');
  } catch (error) { toast(error.message); }
}

function init() {
  document.querySelectorAll('.nav-item').forEach(button => button.addEventListener('click', () => navigate(button.dataset.page)));
  document.querySelectorAll('[data-go]').forEach(button => button.addEventListener('click', () => navigate(button.dataset.go)));
  $('#send-offer').addEventListener('click', () => sendOffer(false));
  $('#buyer-message').addEventListener('keydown', event => { if (event.key === 'Enter') sendOffer(false); });
  $('#best-price').addEventListener('click', () => sendOffer(true));
  $('#checkout-button').addEventListener('click', checkout);
  $('#risky-demo').addEventListener('click', runRiskyDemo);
  $('#reset-demo').addEventListener('click', resetDemo);
  $('#transaction-search').addEventListener('input', renderTransactions);
  $('#status-filter').addEventListener('change', renderTransactions);
  $('#buyer-quantity').addEventListener('change', () => { state.negotiated = null; $('#checkout-button').disabled = true; $('#negotiated-price').textContent = '—'; $('#negotiated-saving').textContent = 'Quantity changed — negotiate again'; });
  $('#help-button').addEventListener('click', () => $('#help-modal').hidden = false);
  $('#close-help').addEventListener('click', () => $('#help-modal').hidden = true);
  $('#help-modal').addEventListener('click', event => { if (event.target.id === 'help-modal') $('#help-modal').hidden = true; });
  refreshState().then(() => {
    if (new URLSearchParams(location.search).get('payment') === 'success') {
      toast(`PayPal Sandbox payment captured. Transaction ${new URLSearchParams(location.search).get('transaction') || ''}`);
      navigate('merchant');
    } else if (new URLSearchParams(location.search).get('payment') === 'cancelled') toast('PayPal Sandbox checkout was cancelled.');
    else if (new URLSearchParams(location.search).has('payment')) toast('PayPal Sandbox could not complete the order. Check the merchant console.');
  }).catch(error => toast(`Could not load demo data: ${error.message}`));
}

document.addEventListener('DOMContentLoaded', init);
