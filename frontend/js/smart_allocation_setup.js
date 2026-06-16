/** 智能资配 · 配置准备页交互 */

const HORIZON_OPTIONS = [
  { label: '一年以下', years: 1 },
  { label: '1～3年', years: 3 },
  { label: '3～5年', years: 5 },
  { label: '5年以上', years: 8 },
];

const SetupPage = {
  _openPopover: null,

  formatHorizon(years) {
    const y = Number(years) || 5;
    if (y <= 1) return '一年以下';
    if (y <= 3) return '1～3年';
    if (y <= 5) return '3～5年';
    return '5年以上';
  },

  getHorizonYears() {
    const cid = getCustomerId();
    const override = sessionStorage.getItem(`setupHorizonOverride_${cid}`);
    if (override) return Number(override);
    const c = CUSTOMERS.find(x => x.id === cid);
    return c?.invest_horizon_years || 5;
  },

  setHorizonYears(years) {
    sessionStorage.setItem(`setupHorizonOverride_${getCustomerId()}`, String(years));
  },

  getRiskProfileName() {
    const c = this.currentCustomer();
    if (c?.risk_profile_name) return c.risk_profile_name;
    const key = c?.risk_profile || ModelSelector._customerRisk();
    return RISK_PROFILE_LABELS[key] || key || '--';
  },

  getReturnRangeLabel(lossKey) {
    const key = lossKey || ModelSelector.getSelectedLossKey();
    const range = ModelSelector.buildReturnRanges().find(r => r.loss_key === key);
    return range?.label || '--';
  },

  currentCustomer() {
    return CUSTOMERS.find(c => c.id === getCustomerId());
  },

  closePopovers() {
    document.querySelectorAll('.setup-picker-popover, .setup-switch-popover').forEach(el => {
      el.classList.remove('open');
      el.hidden = true;
      el.style.position = '';
      el.style.left = '';
      el.style.top = '';
      el.style.right = '';
      el.style.transform = '';
      el.style.maxHeight = '';
    });
    document.querySelectorAll('[aria-expanded="true"].setup-picker-trigger, [aria-expanded="true"].setup-switch-btn')
      .forEach(btn => btn.setAttribute('aria-expanded', 'false'));
    this._openPopover = null;
  },

  positionCustomerSwitchPopover() {
    const btn = document.getElementById('btnSwitchCustomer');
    const popover = document.getElementById('customerSwitchPopover');
    const list = document.getElementById('customerSwitchList');
    if (!btn || !popover || popover.hidden) return;

    const width = 280;
    const rect = btn.getBoundingClientRect();
    let left = rect.left;
    if (left + width > window.innerWidth - 16) {
      left = window.innerWidth - width - 16;
    }
    if (left < 16) left = 16;

    const spaceBelow = window.innerHeight - rect.bottom - 16;
    const spaceAbove = rect.top - 16;
    const preferBelow = spaceBelow >= 160 || spaceBelow >= spaceAbove;

    popover.style.position = 'fixed';
    popover.style.left = `${left}px`;
    popover.style.width = `${width}px`;
    popover.style.right = 'auto';
    popover.style.transform = '';

    if (preferBelow) {
      popover.style.top = `${rect.bottom + 8}px`;
      popover.style.maxHeight = `${Math.min(360, spaceBelow - 8)}px`;
    } else {
      popover.style.top = `${rect.top - 8}px`;
      popover.style.transform = 'translateY(-100%)';
      popover.style.maxHeight = `${Math.min(360, spaceAbove - 8)}px`;
    }
    if (list) {
      list.style.maxHeight = `${Math.max(100, parseFloat(popover.style.maxHeight) - 36)}px`;
    }
  },

  togglePopover(triggerId, popoverId) {
    const trigger = document.getElementById(triggerId);
    const popover = document.getElementById(popoverId);
    if (!trigger || !popover) return;
    const isOpen = popover.classList.contains('open') && !popover.hidden;
    this.closePopovers();
    if (!isOpen) {
      popover.hidden = false;
      popover.classList.add('open');
      trigger.setAttribute('aria-expanded', 'true');
      this._openPopover = popoverId;
      if (popoverId === 'customerSwitchPopover') {
        requestAnimationFrame(() => this.positionCustomerSwitchPopover());
      }
    }
  },

  renderCustomerSwitchList() {
    const list = document.getElementById('customerSwitchList');
    if (!list) return;
    const current = getCustomerId();
    list.innerHTML = CUSTOMERS.map(c => `
      <button type="button" class="setup-switch-option${c.id === current ? ' active' : ''}"
        role="option" aria-selected="${c.id === current}"
        data-customer-id="${c.id}">
        <span class="setup-switch-option-name">${c.displayName || c.name}</span>
        <span class="setup-switch-option-meta">${c.risk_profile_name || ''}</span>
        ${c.id === current ? '<span class="setup-switch-check" aria-hidden="true">✓</span>' : ''}
      </button>
    `).join('');
    list.querySelectorAll('.setup-switch-option').forEach(btn => {
      btn.onclick = (e) => {
        e.stopPropagation();
        const id = btn.dataset.customerId;
        SetupPage.closePopovers();
        if (id === getCustomerId()) return;
        const sel = document.getElementById('customerSelect');
        if (sel) {
          sel.value = id;
          setSelectedCustomerId(id);
          sel.dispatchEvent(new Event('change'));
        }
      };
    });
  },

  renderHorizonPicker() {
    const list = document.getElementById('horizonPickerList');
    if (!list) return;
    const currentLabel = this.formatHorizon(this.getHorizonYears());
    list.innerHTML = HORIZON_OPTIONS.map(o => `
      <button type="button" class="setup-picker-option${o.label === currentLabel ? ' active' : ''}"
        data-years="${o.years}">${o.label}</button>
    `).join('');
    list.querySelectorAll('.setup-picker-option').forEach(btn => {
      btn.onclick = async () => {
        this.setHorizonYears(btn.dataset.years);
        document.getElementById('setupHorizonValue').textContent = btn.textContent;
        this.closePopovers();
      };
    });
  },

  renderReturnPicker() {
    const list = document.getElementById('returnPickerList');
    if (!list) return;
    const current = ModelSelector.getSelectedLossKey();
    const ranges = ModelSelector.buildReturnRanges();
    list.innerHTML = ranges.map(r => `
      <button type="button" class="setup-picker-option${r.loss_key === current ? ' active' : ''}"
        data-loss-key="${r.loss_key}">
        <span>${r.label}</span>
        <span class="setup-picker-option-sub">${r.row.model_code || ''}</span>
      </button>
    `).join('');
    list.querySelectorAll('.setup-picker-option').forEach(btn => {
      btn.onclick = async () => {
        ModelSelector.selectLossKey(btn.dataset.lossKey, 'return');
        this.closePopovers();
        this.updateReturnDisplay();
        await window.onSetupModelChange?.();
      };
    });
  },

  updateLossPreferenceDisplay() {
    const row = ModelSelector.getDefaultLossRow();
    document.getElementById('setupLossValue').textContent = row?.loss_label || '--';
  },

  updateReturnDisplay() {
    document.getElementById('setupReturnValue').textContent =
      this.getReturnRangeLabel(ModelSelector.getSelectedLossKey());
  },

  updateStatusDisplays() {
    document.getElementById('setupRiskValue').textContent = this.getRiskProfileName();
    this.updateLossPreferenceDisplay();
  },

  updateGoalDisplays() {
    document.getElementById('setupHorizonValue').textContent =
      this.formatHorizon(this.getHorizonYears());
    this.updateReturnDisplay();
  },

  bindInteractions() {
    document.getElementById('btnSwitchCustomer')?.addEventListener('click', (e) => {
      e.stopPropagation();
      this.renderCustomerSwitchList();
      this.togglePopover('btnSwitchCustomer', 'customerSwitchPopover');
    });

    const pickerMap = [
      ['btnEditHorizon', 'horizonPickerPopover', () => this.renderHorizonPicker()],
      ['btnEditReturn', 'returnPickerPopover', () => this.renderReturnPicker()],
    ];
    pickerMap.forEach(([btnId, popId, renderFn]) => {
      document.getElementById(btnId)?.addEventListener('click', (e) => {
        e.stopPropagation();
        renderFn();
        this.togglePopover(btnId, popId);
      });
    });

    document.addEventListener('click', () => this.closePopovers());
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') this.closePopovers();
    });
    window.addEventListener('resize', () => {
      if (this._openPopover === 'customerSwitchPopover') {
        this.positionCustomerSwitchPopover();
      }
    });
    document.querySelectorAll('.setup-picker-popover, .setup-switch-popover').forEach(el => {
      el.addEventListener('click', (e) => e.stopPropagation());
    });
  },
};
