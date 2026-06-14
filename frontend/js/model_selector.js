/** 智能资配页 — 模型指派选择（投资组合偏好 / 预期年化收益，二选一） */

const ModelSelector = {
  rows: [],
  riskLossDefault: {},
  mode: 'loss',
  selectedLossKey: null,
  _onChange: null,
  _bound: false,

  _customerRisk() {
    const cid = getCustomerId();
    const c = CUSTOMERS.find(x => x.id === cid);
    return c?.risk_profile || 'balanced';
  },

  defaultLossKey() {
    const cat = getProductCategory();
    const risk = this._customerRisk();
    return (this.riskLossDefault[cat] || {})[risk] || this.rows[0]?.loss_key || null;
  },

  getSelectedLossKey() {
    return this.selectedLossKey || this.defaultLossKey();
  },

  async loadOptions() {
    const cat = encodeURIComponent(getProductCategory());
    const res = await apiGet(`/api/portfolio/map?product_category=${cat}`);
    this.rows = res.data.rows || [];
    this.riskLossDefault = res.data.risk_loss_default || {};
  },

  _resetToDefaults() {
    this.mode = 'loss';
    this.selectedLossKey = this.defaultLossKey();
  },

  _optionLabel(row) {
    if (this.mode === 'return') {
      const ret = row.ret != null ? Number(row.ret).toFixed(2) : '--';
      return `${ret}%`;
    }
    return row.loss_label || row.loss_key;
  },

  _sortedRows() {
    const list = [...this.rows];
    if (this.mode === 'return') {
      list.sort((a, b) => (Number(a.ret) || 0) - (Number(b.ret) || 0));
    }
    return list;
  },

  _setMode(mode) {
    if (mode !== 'loss' && mode !== 'return') return;
    this.mode = mode;
    const isLoss = mode === 'loss';
    document.querySelectorAll('.model-selector-tab').forEach(tab => {
      const active = tab.dataset.mode === mode;
      tab.classList.toggle('active', active);
      tab.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    const wrap = document.querySelector('.model-selector-wrap');
    if (wrap) {
      wrap.classList.toggle('mode-loss', isLoss);
      wrap.classList.toggle('mode-return', !isLoss);
    }
  },

  renderSelect() {
    const sel = document.getElementById('modelSelectorSelect');
    if (!sel) return;

    const rows = this._sortedRows();
    if (!this.selectedLossKey || !rows.some(r => r.loss_key === this.selectedLossKey)) {
      this.selectedLossKey = this.defaultLossKey();
    }

    sel.innerHTML = rows.map(r =>
      `<option value="${r.loss_key}"${r.loss_key === this.selectedLossKey ? ' selected' : ''}>${this._optionLabel(r)}</option>`
    ).join('');

    this._setMode(this.mode);
  },

  resetToCustomerDefault() {
    this._resetToDefaults();
    this.renderSelect();
  },

  async reloadForCategory({ resetMode = false } = {}) {
    await this.loadOptions();
    if (resetMode) {
      this._resetToDefaults();
    } else if (!this.rows.some(r => r.loss_key === this.selectedLossKey)) {
      this.selectedLossKey = this.defaultLossKey();
    }
    this.renderSelect();
  },

  appendQuery(url) {
    const lk = this.getSelectedLossKey();
    if (!lk) return url;
    const sep = url.includes('?') ? '&' : '?';
    return `${url}${sep}loss_key=${encodeURIComponent(lk)}`;
  },

  appendBody(body) {
    const lk = this.getSelectedLossKey();
    if (lk) body.loss_key = lk;
    return body;
  },

  bindEvents() {
    if (this._bound) return;
    this._bound = true;

    document.querySelectorAll('.model-selector-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        const next = tab.dataset.mode;
        if (next === this.mode) return;
        this._setMode(next);
        this.renderSelect();
        if (this._onChange) this._onChange();
      });
    });

    const sel = document.getElementById('modelSelectorSelect');
    if (sel) {
      sel.addEventListener('change', () => {
        this.selectedLossKey = sel.value;
        if (this._onChange) this._onChange();
      });
    }
  },

  async init({ onChange } = {}) {
    this._onChange = onChange || null;
    this.bindEvents();
    await this.loadOptions();
    this._resetToDefaults();
    this.renderSelect();
  },
};

function getSelectedLossKey() {
  return typeof ModelSelector !== 'undefined' ? ModelSelector.getSelectedLossKey() : null;
}

function withLossKey(body) {
  if (typeof ModelSelector !== 'undefined') ModelSelector.appendBody(body);
  return body;
}
