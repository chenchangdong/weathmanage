const API_BASE = '';

let CUSTOMERS = [];

const PLANNING_TYPES = ['投资规划', '综合规划'];
const PRODUCT_CATEGORY_KEY = 'productCategory';
const SELECTED_CUSTOMER_KEY = 'selectedCustomerId';

const RISK_PROFILE_LABELS = {
  conservative: '保守型',
  prudent: '稳健型',
  balanced: '平衡型',
  growth: '成长型',
  aggressive: '进取型',
};

function riskProfileLabel(rb) {
  if (!rb) return '--';
  if (rb.risk_profile_name) return rb.risk_profile_name;
  return RISK_PROFILE_LABELS[rb.risk_profile] || rb.risk_profile || '--';
}

function formatMoney(n) {
  return '¥' + Number(n).toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

function formatPct(n) {
  return (Number(n) * 100).toFixed(1) + '%';
}

function formatBandRange(band) {
  if (!band || band.length < 2) return '--';
  return `${formatPct(band[0])} ~ ${formatPct(band[1])}`;
}

function formatBandTooltip(band) {
  if (!band || band.length < 2) return '暂无阈值数据';
  return `阈值范围：下限 ${formatPct(band[0])}，上限 ${formatPct(band[1])}`;
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

async function apiGet(path) {
  const res = await fetch(API_BASE + path);
  const json = await res.json();
  if (!res.ok) throw new Error(json.detail || '请求失败');
  return json;
}

async function apiPost(path, body) {
  const res = await fetch(API_BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const json = await res.json();
  if (!res.ok) throw new Error(json.detail || '请求失败');
  return json;
}

function getCustomerId() {
  const sel = document.getElementById('customerSelect');
  return sel ? sel.value : (CUSTOMERS[0] && CUSTOMERS[0].id);
}

function getProductCategory() {
  const sel = document.getElementById('planningTypeSelect');
  if (sel && sel.value) {
    sessionStorage.setItem(PRODUCT_CATEGORY_KEY, sel.value);
    return sel.value;
  }
  return sessionStorage.getItem(PRODUCT_CATEGORY_KEY) || '投资规划';
}

function setSelectedCustomerId(customerId) {
  if (customerId) sessionStorage.setItem(SELECTED_CUSTOMER_KEY, customerId);
}

function getSelectedCustomerId() {
  const fromUrl = new URLSearchParams(window.location.search).get('customer_id');
  if (fromUrl) return fromUrl;
  return sessionStorage.getItem(SELECTED_CUSTOMER_KEY) || '';
}

function navigateWithCustomer(path, customerId) {
  setSelectedCustomerId(customerId);
  window.location.href = `${path}?customer_id=${encodeURIComponent(customerId)}`;
}

function formatModelMetrics(ret, vol) {
  const parts = [];
  if (ret != null && ret !== '') parts.push(`预期收益 ${ret}%`);
  if (vol != null && vol !== '') parts.push(`波动 ${vol}%`);
  return parts.length ? `（${parts.join(' / ')}）` : '';
}

function renderMappingBannerHtml(data) {
  const m = data.allocation_mapping;
  if (!m) return '';
  const cat = data.product_category || getProductCategory();
  const metrics = formatModelMetrics(m.expect_annual_return, m.expect_volatility);
  const thresholdNote = data.view_mode === 'asset_type'
    ? '资产类型阈值已按模型五类资产直接映射（保障类不计入总资产）'
    : '四笔钱阈值已按模型聚合';
  const excluded = data.excluded_insurance_amount > 0
    ? ` · 保障类持仓 ${Number(data.excluded_insurance_amount).toLocaleString('zh-CN')} 元未计入`
    : '';
  return `<strong>配置链路</strong>：${cat} · ${data.risk_profile_name}
          → 投资组合偏好「${m.loss_label}」
          → 模型 <strong>${m.model_code}</strong>${metrics}
          → ${thresholdNote}${excluded}`;
}

function saveResult(data) {
  if (data && typeof data === 'object') {
    data.product_category = getProductCategory();
  }
  sessionStorage.setItem('rebalanceResult', JSON.stringify(data));
  sessionStorage.setItem(PRODUCT_CATEGORY_KEY, getProductCategory());
}

function loadResult() {
  const raw = sessionStorage.getItem('rebalanceResult');
  return raw ? JSON.parse(raw) : null;
}

async function loadCustomerList() {
  try {
    const res = await apiGet('/api/customer/list');
    CUSTOMERS = res.data.customers.map(c => ({
      id: c.customer_id,
      name: `${c.name}（${c.risk_profile_name}）`,
      risk_profile: c.risk_profile,
      product_category: c.product_category || '投资规划',
    }));
  } catch (e) {
    CUSTOMERS = [
      { id: 'C20250602001', name: '张女士（平衡型）', risk_profile: 'balanced', product_category: '投资规划' },
      { id: 'C20250602002', name: '李先生（保守型）', risk_profile: 'conservative', product_category: '投资规划' },
      { id: 'C20250602003', name: '王先生（进取型）', risk_profile: 'aggressive', product_category: '投资规划' },
    ];
  }
}

function initPlanningTypeSelect(onChange) {
  const sel = document.getElementById('planningTypeSelect');
  if (!sel) return;
  const saved = sessionStorage.getItem(PRODUCT_CATEGORY_KEY) || '投资规划';
  sel.innerHTML = PLANNING_TYPES.map(
    t => `<option value="${t}"${t === saved ? ' selected' : ''}>${t}</option>`
  ).join('');
  sel.addEventListener('change', () => {
    sessionStorage.setItem(PRODUCT_CATEGORY_KEY, sel.value);
    if (onChange) onChange();
  });
}

function initCustomerSelect(onChange, options = {}) {
  const sel = document.getElementById('customerSelect');
  if (!sel) return;
  loadCustomerList().then(() => {
    sel.innerHTML = CUSTOMERS.map(c => `<option value="${c.id}">${c.name}</option>`).join('');
    const preset = getSelectedCustomerId();
    if (preset && CUSTOMERS.some(c => c.id === preset)) {
      sel.value = preset;
      setSelectedCustomerId(preset);
    }
    sel.addEventListener('change', () => {
      setSelectedCustomerId(sel.value);
      if (onChange) onChange();
    });
    if (!options.skipPlanningType) {
      initPlanningTypeSelect(onChange);
    }
    if (onChange) onChange();
  });
}

function renderNav(active) {
  const nav = document.getElementById('navBar');
  if (!nav) return;
  const pages = [
    { href: 'wealth_inventory.html', label: '财富盘点' },
    { href: 'asset_diagnosis.html', label: '资产诊断' },
    { href: 'smart_allocation.html', label: '智能资配' },
    { href: 'index.html', label: '客户资产', muted: true },
    { href: 'result.html', label: '配置方案', muted: true },
    { href: 'aftercare.html', label: '投后陪伴' },
  ];
  const adminPages = [
    { href: 'admin/model_config.html', label: '模型建立', key: 'model_config' },
    { href: 'admin/portfolio_mapping.html', label: '模型指派', key: 'portfolio_mapping' },
    { href: 'admin/aftercare_system.html', label: '投后陪伴配置', key: 'aftercare_system' },
  ];
  const mainLinks = pages.map(p => {
    const pageKey = p.href.replace('.html', '');
    const isActive = active === pageKey || (active && p.href.includes(active));
    const muted = p.muted ? ' nav-muted' : '';
    return `<a href="${p.href}" class="${isActive ? 'active' : ''}${muted}">${p.label}</a>`;
  }).join('');
  const adminLinks = adminPages.map(p => {
    const isActive = active === p.key;
    return `<a href="${p.href}" class="nav-admin ${isActive ? 'active' : ''}">${p.label}</a>`;
  }).join('');
  nav.innerHTML = `<div class="nav-bar-main">${mainLinks}</div><div class="nav-bar-admin">${adminLinks}</div>`;
}
