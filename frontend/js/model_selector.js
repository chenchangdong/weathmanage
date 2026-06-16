/** 智能资配页 — 模型指派（配置准备页按预期年化收益区间选模） */

const ModelSelector = {
  rows: [],
  riskLossDefault: {},
  mode: 'return',
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

  getDefaultLossRow() {
    const key = this.defaultLossKey();
    return this.rows.find(r => r.loss_key === key) || null;
  },

  getSelectedLossKey() {
    return this.selectedLossKey || this.defaultLossKey();
  },

  getSelectedRow() {
    const key = this.getSelectedLossKey();
    return this.rows.find(r => r.loss_key === key) || null;
  },

  _formatRetNum(ret) {
    const v = Number(ret);
    if (!Number.isFinite(v)) return '--';
    return v.toFixed(2).replace(/\.?0+$/, '');
  },

  buildReturnRanges(rows = this.rows) {
    const sorted = [...rows].sort((a, b) => (Number(a.ret) || 0) - (Number(b.ret) || 0));
    return sorted.map((row, i) => {
      const ret = Number(row.ret);
      let label;
      if (i === 0) {
        label = `小于${this._formatRetNum(ret)}%`;
      } else if (i === sorted.length - 1) {
        const prev = Number(sorted[i - 1].ret);
        label = `${this._formatRetNum(prev)}%以上`;
      } else {
        const prev = Number(sorted[i - 1].ret);
        label = `${this._formatRetNum(prev)}%～${this._formatRetNum(ret)}%`;
      }
      return { loss_key: row.loss_key, label, row };
    });
  },

  getReturnRangeLabel(lossKey) {
    const key = lossKey || this.getSelectedLossKey();
    const range = this.buildReturnRanges().find(r => r.loss_key === key);
    return range?.label || '--';
  },

  selectLossKey(lossKey, mode) {
    if (mode) this.setMode(mode, { persist: false });
    this.selectedLossKey = lossKey;
    const sel = document.getElementById('modelSelectorSelect');
    if (sel) sel.value = lossKey;
    this.persistSelection();
    if (this._onChange) this._onChange();
  },

  _goalModeStorageKey() {
    const cid = typeof getCustomerId === 'function' ? getCustomerId() : '';
    return cid ? `setupGoalMode_${cid}` : 'setupGoalMode';
  },

  getMode() {
    return this.mode;
  },

  setMode(mode, { persist = true } = {}) {
    this._setMode(mode);
    if (persist) this.persistMode();
  },

  persistMode() {
    sessionStorage.setItem(this._goalModeStorageKey(), this.mode);
  },

  restoreMode() {
    const saved = sessionStorage.getItem(this._goalModeStorageKey());
    if (saved === 'loss' || saved === 'return') {
      this._setMode(saved);
    } else {
      this._setMode('return');
    }
  },

  async loadOptions() {
    const cat = encodeURIComponent(getProductCategory());
    const res = await apiGet(`/api/portfolio/map?product_category=${cat}`);
    this.rows = res.data.rows || [];
    this.riskLossDefault = res.data.risk_loss_default || {};
  },

  _resetToDefaults() {
    this.mode = 'return';
    this.selectedLossKey = this.defaultLossKey();
  },

  _optionLabel(row) {
    if (this.mode === 'return') {
      return this.getReturnRangeLabel(row.loss_key);
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
      this.persistMode();
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

  persistSelection() {
    sessionStorage.setItem('allocationLossKey', this.getSelectedLossKey() || '');
    this.persistMode();
  },

  restoreSelection() {
    const saved = sessionStorage.getItem('allocationLossKey');
    if (saved) this.selectedLossKey = saved;
  },

  async initHeadless() {
    await this.loadOptions();
    this.restoreSelection();
    this.restoreMode();
    if (!this.selectedLossKey || !this.rows.some(r => r.loss_key === this.selectedLossKey)) {
      this.selectedLossKey = this.defaultLossKey();
    }
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
    this.restoreSelection();
    this.restoreMode();
    if (!this.selectedLossKey || !this.rows.some(r => r.loss_key === this.selectedLossKey)) {
      this.selectedLossKey = this.defaultLossKey();
    }
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
