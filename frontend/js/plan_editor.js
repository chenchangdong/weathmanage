/** 配置方案人工二次调整 — 产品目标联动大类占比与区间校验 */

const PlanEditor = {
  _pending: false,
  _lastEditedCode: null,
  _manualAddedCodes: new Set(),
  /** 个性化配仓：用户手工改过增减仓的大类（不含一键自动调仓填入） */
  _manualDeltaEditedCategories: new Set(),
  /** 进入配置方案时的产品目标快照 product_code -> target_amount */
  _entryProductTargets: null,
  /** 新增产品草稿校验失败时锁定 code -> 'idle' | 'max_over' | 'min' | 'zero_delta' */
  _manualValidationBlocked: new Map(),
  _pickerCategory: null,
  _pickerSelectedCode: null,
  _pickerTab: 'manual',
  _pickerRb: null,
  _pickerAiProducts: [],
  _categoryCandidatesCache: {},
  _productLimits: {},
  _productLimitValidationEnabled: false,
  /** 个性化配仓（标志驱动 / 最优比例）：大类 adjust_amount 处方 */
  _categoryPrescription: null,
  _categoryPrescriptionMeta: null,
  _categoryTargets: null,
  _prescriptionFrozenTotal: null,
  /** 添加产品时追加的追加持仓 product_code -> 金额（元） */
  _productIdleTopUps: {},

  async loadPageConstraints() {
    try {
      const res = await apiGet('/api/allocation/page_constraints');
      this._productLimitValidationEnabled = !!res.data.product_limit_validation_enabled;
    } catch (e) {
      this._productLimitValidationEnabled = false;
    }
  },

  isProductLimitValidationEnabled() {
    return !!this._productLimitValidationEnabled;
  },

  setLocalPlanSync(fn) {
    this._localPlanSync = typeof fn === 'function' ? fn : null;
  },

  _notifyLocalPlanSync() {
    if (this._localPlanSync) this._localPlanSync();
  },

  PRESCRIPTION_MODES: ['flag_personalized', 'optimal_personalized'],

  isPrescriptionMode(mode) {
    return this.PRESCRIPTION_MODES.includes(mode);
  },

  modeLabel(mode) {
    const labels = {
      smart_one_click: '智能一键',
      manual_tweak: '人工微调',
      manual_product_edit: '人工配置',
      flag_personalized: '个性化智能配仓',
      optimal_personalized: '个性化智能配仓（新）',
    };
    return labels[mode] || mode;
  },

  actionLabel(action) {
    if (action === 'buy') return '买入';
    if (action === 'sell') return '卖出';
    return '持有';
  },

  actionFromDelta(delta) {
    if (Math.abs(delta) < 0.01) return 'hold';
    return delta > 0 ? 'buy' : 'sell';
  },

  resetManualState() {
    this._manualAddedCodes = new Set();
    this._manualDeltaEditedCategories = new Set();
    this._entryProductTargets = null;
    this._manualValidationBlocked = new Map();
    this._categoryCandidatesCache = {};
    this._productLimits = {};
    this._categoryPrescription = null;
    this._categoryPrescriptionMeta = null;
    this._categoryTargets = null;
    this._prescriptionFrozenTotal = null;
    this._productIdleTopUps = {};
  },

  isPersonalizedOrchestration() {
    return this.hasCategoryPrescription();
  },

  cacheCategoryPrescription(rb, force = false) {
    if (!rb || !this.isPrescriptionMode(rb.mode)) return;
    if (this.hasCategoryPrescription() && !force) return;
    this._categoryPrescription = {};
    this._categoryPrescriptionMeta = {};
    this._categoryTargets = { ...(rb.category_targets || {}) };
    this._prescriptionFrozenTotal = rb.total_assets;
    (rb.category_summary || []).forEach((s) => {
      this._categoryPrescription[s.category] = s.adjust_amount;
      this._categoryPrescriptionMeta[s.category] = {
        category_name: s.category_name,
        current_ratio: s.current_ratio,
        final_ratio: s.final_ratio,
        current_amount: s.current_amount,
        target_amount: s.target_amount,
        band: s.band,
        in_band: s.in_band,
      };
    });
    this.captureEntryProductPlan(rb);
  },

  captureEntryProductPlan(rb) {
    if (!rb?.product_deltas?.length) {
      this._entryProductTargets = {};
      return;
    }
    this._entryProductTargets = {};
    rb.product_deltas.forEach((d) => {
      this._entryProductTargets[d.product_code] = d.target_amount;
    });
  },

  exportPrescriptionSnapshot() {
    if (!this.hasCategoryPrescription()) return null;
    return {
      adjust: { ...this._categoryPrescription },
      meta: JSON.parse(JSON.stringify(this._categoryPrescriptionMeta || {})),
      targets: { ...(this._categoryTargets || {}) },
      frozenAtTotal: this._prescriptionFrozenTotal,
      manualAddedCodes: [...this._manualAddedCodes],
      manualDeltaEditedCategories: [...this._manualDeltaEditedCategories],
      entryProductTargets: { ...(this._entryProductTargets || {}) },
      productIdleTopUps: { ...this._productIdleTopUps },
      savedIdleCash: null,
    };
  },

  attachPrescriptionSnapshot(data) {
    if (!data) return data;
    const snap = this.exportPrescriptionSnapshot();
    if (snap) {
      snap.savedIdleCash = data.rebalance?.idle_cash ?? 0;
      data.categoryPrescription = snap;
    }
    return data;
  },

  restorePrescriptionSnapshot(data) {
    const snap = data?.categoryPrescription;
    if (snap?.adjust && Object.keys(snap.adjust).length) {
      this._categoryPrescription = { ...snap.adjust };
      this._categoryPrescriptionMeta = { ...snap.meta };
      this._categoryTargets = { ...(snap.targets || {}) };
      this._prescriptionFrozenTotal = snap.frozenAtTotal ?? null;
      this._manualAddedCodes = new Set(snap.manualAddedCodes || []);
      this._manualDeltaEditedCategories = new Set(snap.manualDeltaEditedCategories || []);
      this._entryProductTargets = snap.entryProductTargets
        ? { ...snap.entryProductTargets }
        : null;
      this._productIdleTopUps = { ...(snap.productIdleTopUps || {}) };
      if (!this._entryProductTargets && data?.rebalance) {
        this.captureEntryProductPlan(data.rebalance);
      }
      return true;
    }
    if (data?.rebalance && this.isPrescriptionMode(data.rebalance.mode)) {
      this.cacheCategoryPrescription(data.rebalance, true);
      return true;
    }
    return false;
  },

  syncPlanIdleCash(rb, idleCash, holdingsBaseTotal) {
    if (!rb) return;
    rb.idle_cash = idleCash;
    rb.total_assets = (holdingsBaseTotal || 0) + idleCash;
  },

  isPersonalizedPlanCache(cached) {
    if (!cached?.rebalance) return false;
    if (cached.categoryPrescription) return true;
    return this.isPrescriptionMode(cached.rebalance.mode);
  },

  isPlanCacheForCurrentContext(cached) {
    if (!cached?.rebalance) return false;
    const cid = typeof getSelectedCustomerId === 'function' ? getSelectedCustomerId() : null;
    const cat = typeof getProductCategory === 'function' ? getProductCategory() : null;
    if (cid && cached.rebalance.customer_id !== cid) return false;
    if (cat && cached.product_category && cached.product_category !== cat) return false;
    return true;
  },

  discardPlanCacheIfWrongContext() {
    if (typeof loadResult !== 'function') return false;
    const cached = loadResult();
    if (!cached?.rebalance) return false;
    if (this.isPlanCacheForCurrentContext(cached)) return false;
    this.resetManualState();
    sessionStorage.removeItem('rebalanceResult');
    return true;
  },

  hasSavedPersonalizedPlan() {
    if (typeof loadResult !== 'function') return false;
    const cached = loadResult();
    if (!this.isPersonalizedPlanCache(cached)) return false;
    return this.isPlanCacheForCurrentContext(cached);
  },

  /**
   * 配置页追加持仓关闭/减少后，缓存处方是否仍可继续落实。
   * 不可恢复时按首次进入处理（清缓存、不重载方案）。
   */
  isSavedPrescriptionRestorable(cached, newIdle, holdingsBaseTotal) {
    if (!cached?.rebalance) return false;
    if (!cached.categoryPrescription && !this.isPrescriptionMode(cached.rebalance.mode)) {
      return false;
    }

    const rb = cached.rebalance;
    const savedIdle = cached.categoryPrescription?.savedIdleCash ?? rb.idle_cash ?? 0;
    const idle = Math.max(0, Number(newIdle) || 0);
    const addonOff = typeof isAddonEnabled === 'function' && !isAddonEnabled();

    if (addonOff && savedIdle > 0.01) return false;

    const testRb = {
      ...rb,
      idle_cash: idle,
      total_assets: (holdingsBaseTotal || 0) + idle,
      product_deltas: rb.product_deltas || [],
    };

    if (cached.categoryPrescription || this.isPrescriptionMode(rb.mode)) {
      return this.isIdleCashSufficient(this.calcIdleCashUsageFromDeltas(testRb));
    }
    return true;
  },

  initPrescriptionRegenModal() {
    const modal = document.getElementById('prescriptionRegenModal');
    const msgEl = document.getElementById('prescriptionRegenMessage');
    const confirmBtn = document.getElementById('prescriptionRegenConfirm');
    const cancelBtn = document.getElementById('prescriptionRegenCancel');
    if (!modal || modal.dataset.bound) return;
    modal.dataset.bound = '1';

    const close = (regenerate) => {
      modal.classList.remove('open');
      const resolve = this._rxRegenResolve;
      this._rxRegenResolve = null;
      if (resolve) resolve(!!regenerate);
    };

    if (confirmBtn) confirmBtn.onclick = () => close(true);
    if (cancelBtn) cancelBtn.onclick = () => close(false);
    modal.addEventListener('click', (e) => {
      if (e.target === modal) close(false);
    });
    this._prescriptionRegenModal = modal;
    this._prescriptionRegenMessageEl = msgEl;
  },

  promptRegeneratePrescription(oldTotal, newTotal) {
    this.initPrescriptionRegenModal();
    const modal = this._prescriptionRegenModal;
    const msgEl = this._prescriptionRegenMessageEl;
    if (!modal) return Promise.resolve(true);

    let detail = '重新生成将覆盖当前大类处方；已添加的产品明细会尽量保留，但处方目标可能变化。';
    if (oldTotal != null && newTotal != null && Math.abs(oldTotal - newTotal) >= 1) {
      detail = `追加持仓/总资产已变更（${formatMoney(oldTotal)} → ${formatMoney(newTotal)}）。`
        + detail;
    }
    if (msgEl) msgEl.textContent = detail;

    return new Promise((resolve) => {
      this._rxRegenResolve = resolve;
      modal.classList.add('open');
    });
  },

  getPrescriptionMeta(category) {
    return this._categoryPrescriptionMeta?.[category] || null;
  },

  isCategoryActionable(category) {
    const adj = this.getPrescribedAdjust(category);
    return adj != null && Math.abs(adj) >= 1;
  },

  renderPrescriptionBadge(adjustAmount) {
    const adj = adjustAmount || 0;
    if (Math.abs(adj) < 1) {
      return '<span class="personalized-rx-badge personalized-rx-badge--neutral">保持不变</span>';
    }
    if (adj > 0) {
      return '<span class="personalized-rx-badge personalized-rx-badge--buy">需增配</span>';
    }
    return '<span class="personalized-rx-badge personalized-rx-badge--sell">需减配</span>';
  },

  calcCategoryPlannedAmount(rb, category) {
    return (rb.product_deltas || [])
      .filter((d) => d.category === category)
      .reduce((sum, d) => {
        const tgt = d.target_amount != null
          ? d.target_amount
          : (d.current_amount || 0) + (d.delta_amount || 0);
        return sum + tgt;
      }, 0);
  },

  /** 本类是否已有产品层落实（增减不为 0） */
  hasCategoryProductActivity(rb, category) {
    return (rb.product_deltas || [])
      .filter((d) => d.category === category)
      .some((d) => Math.abs(d.delta_amount || 0) >= 1);
  },

  isCategoryPlannedInBand(rb, category) {
    const meta = this.getPrescriptionMeta(category);
    if (!meta || !meta.band || !rb.total_assets) return true;
    const ratio = this.calcCategoryPlannedAmount(rb, category) / rb.total_assets;
    return ratio >= meta.band[0] - 0.0001 && ratio <= meta.band[1] + 0.0001;
  },

  /** 个性化配仓：未落实产品前看处方 in_band，落实后按产品汇总占比实时判定 */
  resolvePersonalizedBandInBand(rb, category) {
    if (!this.hasCategoryPrescription()) return true;
    if (this.hasCategoryProductActivity(rb, category)) {
      return this.isCategoryPlannedInBand(rb, category);
    }
    const meta = this.getPrescriptionMeta(category);
    return meta?.in_band !== false;
  },

  renderPersonalizedBandBadge(inBand) {
    return inBand
      ? '<span class="badge-yes rx-band-badge">✓ 在区间内</span>'
      : '<span class="badge-no rx-band-badge">△ 次优解</span>';
  },

  syncPersonalizedBandUI(rb, category) {
    if (!this.hasCategoryPrescription()) return;
    const card = document.querySelector(`.personalized-card.${category}`);
    if (!card) return;
    const inBand = this.resolvePersonalizedBandInBand(rb, category);
    const badge = card.querySelector('.rx-summary-meta .rx-band-badge');
    if (badge) {
      badge.className = inBand ? 'badge-yes rx-band-badge' : 'badge-no rx-band-badge';
      badge.textContent = inBand ? '✓ 在区间内' : '△ 次优解';
    }
    const bandSlot = card.querySelector('.rx-band-warn-slot');
    if (!bandSlot) return;
    const bandHtml = this.renderCategoryBandWarning(rb, category);
    bandSlot.innerHTML = bandHtml;
    bandSlot.style.display = bandHtml ? 'block' : 'none';
  },

  renderCategoryBandWarning(rb, category) {
    if (!this.hasCategoryProductActivity(rb, category)) return '';
    if (this.isCategoryPlannedInBand(rb, category)) return '';
    const meta = this.getPrescriptionMeta(category);
    if (!meta || !rb.total_assets) return '';
    const ratio = this.calcCategoryPlannedAmount(rb, category) / rb.total_assets;
    const lo = meta.band[0];
    const hi = meta.band[1];
    let msg = '';
    if (ratio > hi + 0.0001) {
      msg = `已落实产品占比 ${formatPct(ratio)} 高于模型上限 ${formatPct(hi)}，请继续落实`;
    } else if (ratio < lo - 0.0001) {
      msg = `已落实产品占比 ${formatPct(ratio)} 低于模型下限 ${formatPct(lo)}，请继续落实`;
    }
    if (!msg) return '';
    return `<div class="rx-band-warn">${msg}</div>`;
  },

  renderPersonalizedRxSummary(rb, category) {
    const meta = this.getPrescriptionMeta(category);
    if (!meta) return '';
    const adj = this.getPrescribedAdjust(category) ?? 0;
    const actionable = Math.abs(adj) >= 1;
    const bandTip = typeof formatBandTooltip === 'function' ? formatBandTooltip(meta.band) : '';
    const bandRange = typeof formatBandRange === 'function' ? formatBandRange(meta.band) : '--';
    const bandBadge = this.renderPersonalizedBandBadge(
      this.resolvePersonalizedBandInBand(rb, category)
    );

    if (!actionable) {
      return `
        <div class="rx-summary rx-summary--neutral">
          <div class="rx-summary-static">
            <span>占比 <strong>${formatPct(meta.current_ratio)}</strong></span>
            <span>现仓 ${formatMoney(meta.current_amount)}</span>
            <span class="rx-summary-static-note">大类处方：保持不变</span>
          </div>
          <div class="rx-summary-meta" title="${this._escapeAttr(bandTip)}">
            ${bandBadge}
            <span class="rx-summary-band">模型区间 ${bandRange}</span>
          </div>
        </div>`;
    }

    const arrowCls = adj >= 0 ? 'rx-summary-arrow--buy' : 'rx-summary-arrow--sell';
    return `
      <div class="rx-summary">
        <div class="rx-summary-flow">
          <div class="rx-summary-node">
            <span class="rx-summary-label">当前现仓</span>
            <strong class="rx-summary-pct rx-summary-pct--primary">${formatPct(meta.current_ratio)}</strong>
            <span class="rx-summary-amt">${formatMoney(meta.current_amount)}</span>
          </div>
          <div class="rx-summary-arrow ${arrowCls}">
            <span class="rx-summary-delta">${adj >= 0 ? '+' : ''}${formatMoney(adj)}</span>
            <span class="rx-arrow-icon" aria-hidden="true">→</span>
          </div>
          <div class="rx-summary-node rx-summary-node--target">
            <span class="rx-summary-label">处方目标</span>
            <strong class="rx-summary-pct rx-summary-pct--primary">${formatPct(meta.final_ratio)}</strong>
            <span class="rx-summary-amt">${formatMoney(meta.target_amount)}</span>
          </div>
        </div>
        <div class="rx-summary-meta" title="${this._escapeAttr(bandTip)}">
          ${bandBadge}
          <span class="rx-summary-band">模型区间 ${bandRange}</span>
        </div>
      </div>`;
  },

  _escapeAttr(text) {
    return String(text || '')
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;');
  },

  renderPrescriptionProgressBar(rb, category) {
    if (!this.hasCategoryPrescription()) return '';
    const prescribed = this.getPrescribedAdjust(category);
    if (prescribed == null || Math.abs(prescribed) < 1) return '';
    const allocated = this.categoryAllocatedDelta(rb, category);
    const remaining = prescribed - allocated;
    const done = Math.abs(remaining) < 1;
    const over = (prescribed > 0.01 && remaining < -0.01) || (prescribed < -0.01 && remaining > 0.01);
    let wrapCls = '';
    let statusHtml = '';
    let pct = 0;

    if (over) {
      wrapCls = 'rx-progress-wrap--over';
      const excess = Math.abs(remaining);
      statusHtml = `<span class="rx-progress-over">超过目标 ${formatMoney(excess)}</span>`;
      pct = Math.min(100, Math.max(0, Math.round((Math.abs(allocated) / Math.abs(prescribed)) * 100)));
    } else if (done) {
      wrapCls = 'rx-progress-wrap--done';
      statusHtml = '<span class="badge-yes">✓ 已落实</span>';
      pct = 100;
    } else if (prescribed > 0.01) {
      statusHtml = `<span class="rx-progress-remaining">还需增配 ${formatMoney(remaining)}</span>`;
      pct = Math.min(100, Math.max(0, Math.round((allocated / prescribed) * 100)));
    } else {
      statusHtml = `<span class="rx-progress-remaining">还需减配 ${formatMoney(Math.abs(remaining))}</span>`;
      pct = Math.min(100, Math.max(0, Math.round((Math.abs(allocated) / Math.abs(prescribed)) * 100)));
    }

    return `
      <div class="rx-progress-wrap ${wrapCls}">
        <div class="rx-progress-head">
          <span>产品落实进度</span>
          <span class="rx-progress-stats">
            ${allocated >= 0 ? '+' : ''}${formatMoney(allocated)}
            / ${prescribed >= 0 ? '+' : ''}${formatMoney(prescribed)}
            ${statusHtml}
          </span>
        </div>
        <div class="rx-progress-track"><div class="rx-progress-fill" style="width:${pct}%"></div></div>
      </div>`;
  },

  renderPersonalizedContextPanel(diagnosis, validationNotes, rb) {
    const el = document.getElementById('flagContextPanel');
    if (!el) return;
    if (rb?.mode === 'optimal_personalized') {
      el.style.display = 'block';
      el.innerHTML = `
        <div class="flag-context-title">依据全账户最优比例生成大类处方</div>
        <div class="flag-context-hint">各资产类型目标由模型区间与最小异动策略求解；需调整的大类会给出「现仓 → 处方目标」与调整金额。可点「一键自动调仓」快速填入参考分配，再按需微调。</div>`;
      return;
    }
    const flags = ((diagnosis && diagnosis.flags) || [])
      .filter((f) => f.code !== 'four_money_mismatch');
    const flagHtml = flags.length
      ? flags.map((f) => `<span class="flag-chip">${f.label}</span>`).join('')
      : '';
    const note = (validationNotes || []).find((n) => n.includes('个性化配仓依据'));
    el.style.display = 'block';
    el.innerHTML = `
      <div class="flag-context-title">依据财富健康标志生成大类处方</div>
      ${flagHtml ? `<div class="flag-context-chips">${flagHtml}</div>` : ''}
      ${note ? `<div class="flag-context-note">${note}</div>` : ''}
      <div class="flag-context-hint">需调整的大类会给出「现仓 → 处方目标」与调整金额；可点「一键自动调仓」快速填入参考分配，再按需微调。</div>`;
  },

  /** @deprecated use renderPersonalizedContextPanel */
  renderFlagContextPanel(diagnosis, validationNotes, rb) {
    this.renderPersonalizedContextPanel(diagnosis, validationNotes, rb);
  },

  hideFlagContextPanel() {
    const el = document.getElementById('flagContextPanel');
    if (!el) {
      return;
    }
    el.style.display = 'none';
    el.innerHTML = '';
  },

  hasCategoryPrescription() {
    return !!this._categoryPrescription && Object.keys(this._categoryPrescription).length > 0;
  },

  getPrescribedAdjust(category) {
    if (!this.hasCategoryPrescription()) return null;
    return this._categoryPrescription[category] ?? 0;
  },

  categoryAllocatedDelta(rb, category) {
    return (rb.product_deltas || [])
      .filter((d) => d.category === category)
      .reduce((sum, d) => sum + (d.delta_amount || 0), 0);
  },

  validateCategoryPrescription(rb, category) {
    if (!this.isCategoryActionable(category)) return { ok: true };
    const prescribed = this.getPrescribedAdjust(category);
    if (prescribed == null) return { ok: true };
    const allocated = this.categoryAllocatedDelta(rb, category);
    const remaining = prescribed - allocated;
    if (Math.abs(remaining) >= 1) {
      const catName = this.categoryName(rb, category);
      const hint = prescribed > 0.01
        ? `，还需增配 ${formatMoney(remaining)}`
        : `，还需减配 ${formatMoney(Math.abs(remaining))}`;
      return {
        ok: false,
        message: `${catName}产品增减合计${allocated >= 0 ? '+' : ''}${formatMoney(allocated)}，`
          + `距大类建议${prescribed >= 0 ? '+' : ''}${formatMoney(prescribed)}${hint}，请继续落实`,
      };
    }
    return { ok: true };
  },

  renderCategoryPrescriptionProgress(rb, category) {
    return this.renderPrescriptionProgressBar(rb, category);
  },

  categoryHasManualAddedProducts(rb, category) {
    return (rb.product_deltas || []).some(
      (d) => d.category === category && this._manualAddedCodes.has(d.product_code)
    );
  },

  /** 本类产品目标是否与进入配置方案时一致（用于还原按钮） */
  categoryProductPlanMatchesEntry(rb, category) {
    if (!this._entryProductTargets) return true;
    const inCategory = (rb.product_deltas || []).filter((d) => d.category === category);
    for (const d of inCategory) {
      if (this._manualAddedCodes.has(d.product_code)) continue;
      const entry = this._entryProductTargets[d.product_code];
      if (entry == null) {
        if (Math.abs(d.target_amount) >= 0.01 || Math.abs(d.delta_amount) >= 0.01) {
          return false;
        }
        continue;
      }
      if (Math.abs(d.target_amount - entry) >= 0.01) {
        return false;
      }
    }
    return true;
  },

  getCategoryOrchestrationButtonMode(rb, category) {
    if (this.categoryHasManualAddedProducts(rb, category)) return 'disabled';
    if (!this.categoryProductPlanMatchesEntry(rb, category)) return 'restore';
    return 'suggest';
  },

  getCategoryOrchestrationButtonMeta(rb, category) {
    const mode = this.getCategoryOrchestrationButtonMode(rb, category);
    if (mode === 'restore') {
      return {
        mode,
        label: '一键还原配仓',
        action: 'category-restore',
        disabled: false,
        title: '还原至进入配置方案时的本类产品配仓',
      };
    }
    if (mode === 'disabled') {
      return {
        mode,
        label: '一键自动调仓',
        action: 'category-suggest',
        disabled: true,
        title: '本类已手工添加产品，一键自动调仓不可用',
      };
    }
    return {
      mode,
      label: '一键自动调仓',
      action: 'category-suggest',
      disabled: false,
      title: '',
    };
  },

  isCategorySuggestDisabled(rb, category) {
    return this.getCategoryOrchestrationButtonMode(rb, category) === 'disabled';
  },

  categorySuggestDisabledReason(rb, category) {
    if (this.categoryHasManualAddedProducts(rb, category)) {
      return '本类已手工添加产品，一键自动调仓不可用';
    }
    return '';
  },

  syncCategorySuggestButtons(rb) {
    if (!this.hasCategoryPrescription()) return;
    document.querySelectorAll('[data-action="category-suggest"], [data-action="category-restore"]').forEach((btn) => {
      const category = btn.dataset.category;
      if (!category) return;
      const meta = this.getCategoryOrchestrationButtonMeta(rb, category);
      btn.disabled = meta.disabled;
      btn.textContent = meta.label;
      btn.dataset.action = meta.action;
      btn.title = meta.title || '';
      btn.classList.toggle('btn-category-suggest--disabled', meta.disabled);
    });
  },

  renderPersonalizedOrchestration(rb, category, actionable) {
    const btnMeta = this.getCategoryOrchestrationButtonMeta(rb, category);
    const suggestDisabledAttr = btnMeta.disabled ? ' disabled' : '';
    const suggestTitle = btnMeta.title
      ? ` title="${this._escapeAttr(btnMeta.title)}"`
      : '';
    const head = actionable
      ? `<div class="personalized-orchestration-head">
          <span class="product-section-label">产品落实</span>
          <button type="button" class="btn btn-sm btn-secondary btn-category-suggest${btnMeta.disabled ? ' btn-category-suggest--disabled' : ''}"
            data-action="${btnMeta.action}" data-category="${category}"${suggestDisabledAttr}${suggestTitle}>${btnMeta.label}</button>
        </div>`
      : '<div class="product-section-label personalized-orchestration-label">本类产品调仓明细</div>';
    return `
      <div class="personalized-orchestration">
        ${head}
        <div class="product-detail plan-product-detail always-open" id="products-plan-${category}">
          ${this.renderEditableCategoryProductRows(rb, category)}
        </div>
      </div>`;
  },

  renderPersonalizedPlanCards(rb) {
    return rb.category_summary.map((s) => {
      const prescribed = this.getPrescribedAdjust(s.category);
      const adj = prescribed != null ? prescribed : (s.adjust_amount || 0);
      const actionable = Math.abs(adj) >= 1;
      const meta = this.getPrescriptionMeta(s.category);
      const name = meta?.category_name || s.category_name;
      const bandWarn = this.renderCategoryBandWarning(rb, s.category);
      return `
        <div class="category-card plan-card personalized-card ${s.category}">
          <div class="card-title">
            <span>${name}</span>
            ${this.renderPrescriptionBadge(adj)}
          </div>
          ${this.renderPersonalizedRxSummary(rb, s.category)}
          ${actionable ? this.renderPrescriptionProgressBar(rb, s.category) : ''}
          <div class="rx-band-warn-slot" id="band-warn-${s.category}"${bandWarn ? '' : ' style="display:none"'}>${bandWarn}</div>
          ${this.renderPersonalizedOrchestration(rb, s.category, actionable)}
        </div>`;
    }).join('');
  },

  mergeCategorySuggestDeltas(rb, category, suggested) {
    const merged = (rb.product_deltas || []).map((d) => ({ ...d }));
    suggested
      .filter((sd) => sd.category === category)
      .forEach((sd) => {
        const idx = merged.findIndex((d) => d.product_code === sd.product_code);
        if (idx >= 0) {
          const existing = merged[idx];
          if (this._manualAddedCodes.has(sd.product_code)) return;
          if (Math.abs(existing.delta_amount) >= 1) return;
          merged[idx] = { ...existing, ...sd };
        } else {
          merged.push({ ...sd });
        }
      });
    merged.sort((a, b) =>
      (a.category + a.product_code).localeCompare(b.category + b.product_code)
    );
    return merged;
  },

  validateCategorySuggestMerge(rb, category, mergedDeltas) {
    const testRb = { ...rb, product_deltas: mergedDeltas };
    const idleStats = this.calcIdleCashUsageForPlan(testRb);
    if (!this.isIdleCashSufficient(idleStats)) {
      const shortfall = -idleStats.remaining;
      const netSell = mergedDeltas.reduce((s, d) => s + Math.min(d.delta_amount || 0, 0), 0);
      return {
        ok: false,
        code: 'idle',
        shortfall,
        needsReduceFirst: netSell > -0.01,
        message: `增配金额将超出追加持仓（超出 ${formatMoney(shortfall)}）。需先减配释放资金后再试`,
      };
    }
    if (!this.isCategoryActionable(category)) return { ok: true };
    const prescribed = this.getPrescribedAdjust(category);
    const allocated = mergedDeltas
      .filter((d) => d.category === category)
      .reduce((sum, d) => sum + (d.delta_amount || 0), 0);
    if (prescribed > 0.01 && allocated > prescribed + 0.01) {
      const manual = this.categoryAllocatedDelta(rb, category);
      return {
        ok: false,
        code: 'prescription',
        message: `本类增配处方 ${formatMoney(prescribed)}，当前已填 ${formatMoney(manual)}，`
          + `一键自动调仓后合计 ${formatMoney(allocated)} 将超出 ${formatMoney(allocated - prescribed)}。`
          + '请先调整已添加产品金额后再试',
      };
    }
    if (prescribed < -0.01 && allocated < prescribed - 0.01) {
      return {
        ok: false,
        code: 'prescription',
        message: `本类减配处方 ${formatMoney(prescribed)}，一键自动调仓后合计 ${formatMoney(allocated)} `
          + '将超出减配幅度。请先调整后再试',
      };
    }
    return { ok: true };
  },

  applyIdleCashTopUp(rb, topUpYuan, onSynced) {
    const add = Math.max(0, Number(topUpYuan) || 0);
    if (add < 0.01) return 0;
    rb.idle_cash = (rb.idle_cash || 0) + add;
    rb.total_assets = (rb.total_assets || 0) + add;
    if (typeof commitAddonIdleCash === 'function') {
      commitAddonIdleCash(rb.idle_cash);
    }
    if (typeof onSynced === 'function') onSynced();
    this.updateIdleCashPanel(rb, { showPlanStats: true });
    return add;
  },

  applyIdleCashRevert(rb, revertYuan, onSynced) {
    const revert = Math.min(Math.max(0, Number(revertYuan) || 0), rb.idle_cash || 0);
    if (revert < 0.01) return 0;
    rb.idle_cash = (rb.idle_cash || 0) - revert;
    rb.total_assets = Math.max(0, (rb.total_assets || 0) - revert);
    if (typeof commitAddonIdleCash === 'function') {
      commitAddonIdleCash(rb.idle_cash);
    }
    if (typeof onSynced === 'function') onSynced();
    this.updateIdleCashPanel(rb, { showPlanStats: true });
    return revert;
  },

  initIdleCashRevertModal(onSynced) {
    this._idleRevertOnSynced = onSynced;
    const modal = document.getElementById('idleCashRevertModal');
    const msgEl = document.getElementById('idleCashRevertMessage');
    const yesBtn = document.getElementById('idleCashRevertYes');
    const noBtn = document.getElementById('idleCashRevertNo');
    if (!modal || modal.dataset.bound) return;
    modal.dataset.bound = '1';

    const close = (revert) => {
      modal.classList.remove('open');
      const resolve = this._idleRevertResolve;
      this._idleRevertResolve = null;
      this._idleRevertRb = null;
      this._idleRevertAmount = 0;
      if (resolve) resolve(!!revert);
    };

    if (noBtn) noBtn.onclick = () => close(false);
    if (yesBtn) {
      yesBtn.onclick = () => {
        const rb = this._idleRevertRb;
        const amount = this._idleRevertAmount;
        if (rb && amount > 0.01) {
          const reverted = this.applyIdleCashRevert(rb, amount, this._idleRevertOnSynced);
          if (reverted > 0.01) {
            showToast(`已取消追加持仓追加 ${formatMoney(reverted)}`);
          }
        }
        close(true);
      };
    }
    modal.addEventListener('click', (e) => {
      if (e.target === modal) close(false);
    });
  },

  promptRevertIdleTopUp(rb, storedAmount, productName) {
    this.initIdleCashRevertModal(this._idleRevertOnSynced || this._idleCashOnSynced);
    const modal = document.getElementById('idleCashRevertModal');
    const msgEl = document.getElementById('idleCashRevertMessage');
    if (!modal || !msgEl) return Promise.resolve(false);

    const stats = this.calcIdleCashUsageForPlan(rb);
    const revertible = Math.min(storedAmount, rb.idle_cash || 0, Math.max(0, stats.remaining));
    if (revertible < 0.01) return Promise.resolve(false);

    let msg = `删除「${productName}」后，是否一并取消此前为添加该产品追加的追加持仓 ${formatMoney(storedAmount)}？`;
    if (revertible < storedAmount - 0.01) {
      msg += `（当前方案已占用部分追加金额，最多可取消 ${formatMoney(revertible)}）`;
    }
    msgEl.textContent = msg;
    this._idleRevertRb = rb;
    this._idleRevertAmount = revertible;

    return new Promise((resolve) => {
      this._idleRevertResolve = resolve;
      modal.classList.add('open');
    });
  },

  initIdleCashGuideModal(onSynced) {
    this._idleCashOnSynced = onSynced;
    const modal = document.getElementById('idleCashGuideModal');
    const msgEl = document.getElementById('idleCashGuideMessage');
    const inputPanel = document.getElementById('idleCashGuideInputPanel');
    const inputEl = document.getElementById('idleCashGuideInput');
    const yesBtn = document.getElementById('idleCashGuideYes');
    const noBtn = document.getElementById('idleCashGuideNo');
    const confirmBtn = document.getElementById('idleCashGuideConfirm');
    if (!modal || modal.dataset.bound) return;
    modal.dataset.bound = '1';

    const close = (result) => {
      modal.classList.remove('open');
      if (inputPanel) inputPanel.style.display = 'none';
      if (yesBtn) yesBtn.style.display = '';
      if (confirmBtn) confirmBtn.style.display = 'none';
      if (inputEl) inputEl.value = '';
      const resolve = this._idleGuideResolve;
      this._idleGuideResolve = null;
      this._idleGuideRb = null;
      this._idleGuideShortfall = 0;
      if (resolve) resolve(!!result);
    };

    if (noBtn) {
      noBtn.onclick = () => close(false);
    }
    if (modal) {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) close(false);
      });
    }
    if (yesBtn) {
      yesBtn.onclick = () => {
        if (inputPanel) inputPanel.style.display = 'block';
        yesBtn.style.display = 'none';
        if (confirmBtn) confirmBtn.style.display = '';
        const wan = this._idleGuideShortfall && typeof yuanToWanInputDefault === 'function'
          ? yuanToWanInputDefault(this._idleGuideShortfall)
          : '';
        if (inputEl) {
          inputEl.value = wan;
          inputEl.focus();
        }
      };
    }
    if (confirmBtn) {
      confirmBtn.onclick = () => {
        const rb = this._idleGuideRb;
        if (!rb || !inputEl) {
          close(false);
          return;
        }
        const parsed = typeof parseAddonInput === 'function'
          ? parseAddonInput(inputEl.value)
          : { ok: true, value: parseFloat(inputEl.value) * 10000 || 0 };
        if (!parsed.ok || parsed.value < 0.01) {
          showToast('请输入有效的追加金额（万）');
          return;
        }
        const need = this._idleGuideShortfall || 0;
        if (need > 0.01 && parsed.value < need - 0.01) {
          const hint = typeof yuanToWanInputDefault === 'function'
            ? yuanToWanInputDefault(need)
            : '';
          showToast(`追加金额不足，至少 ${formatMoney(need)}${hint ? `（${hint} 万）` : ''}`);
          return;
        }
        this.applyIdleCashTopUp(rb, parsed.value, this._idleCashOnSynced);
        showToast(`已追加追加持仓 ${formatMoney(parsed.value)}`);
        close(true);
      };
    }
  },

  promptIdleCashGuide(rb, gate, options = {}) {
    this.initIdleCashGuideModal(this._idleCashOnSynced);
    const modal = document.getElementById('idleCashGuideModal');
    const msgEl = document.getElementById('idleCashGuideMessage');
    if (!modal || !msgEl) return Promise.resolve(false);

    const shortfall = gate.shortfall || 0;
    if (options.forAddProduct) {
      if (gate.needsReduceFirst) {
        msgEl.textContent = `添加产品需占用追加持仓，当前剩余不足（还差 ${formatMoney(shortfall)}）。`
          + '可先减配其他产品释放资金，或追加追加持仓。是否追加？';
      } else {
        msgEl.textContent = `添加产品需占用追加持仓，当前剩余不足（还差 ${formatMoney(shortfall)}）。是否追加追加持仓？`;
      }
    } else {
      const lead = gate.needsReduceFirst !== false
        ? '当前增配所需资金超过追加持仓余额。需先在其他产品/大类减配释放资金，再执行增配；'
        : '当前方案增配合计超过追加持仓余额；';
      msgEl.textContent = `${lead}或追加追加持仓金额（还差 ${formatMoney(shortfall)}）。是否追加追加持仓？`;
    }

    this._idleGuideRb = rb;
    this._idleGuideShortfall = shortfall;

    return new Promise((resolve) => {
      this._idleGuideResolve = resolve;
      modal.classList.add('open');
    });
  },

  async tryApplyCategorySuggestMerge(rb, category, merged) {
    const gate = this.validateCategorySuggestMerge(rb, category, merged);
    if (gate.ok) {
      rb.product_deltas = merged;
      this.updateIdleCashPanel(rb, { showPlanStats: true });
      return true;
    }
    if (gate.code === 'idle') {
      const msg = gate.needsReduceFirst
        ? `增配金额将超出追加持仓（超出 ${formatMoney(gate.shortfall)}）。需先减配释放资金后再试`
        : gate.message;
      showToast(msg);
      return false;
    }
    showToast(gate.message);
    return false;
  },

  async applyCategorySuggest(rb, category) {
    if (this.categoryHasManualAddedProducts(rb, category)) {
      showToast('本类已手工添加产品，请手动落实调仓');
      return false;
    }
    if (!this._categoryTargets) {
      showToast('缺少大类处方，请重新发起个性化配仓');
      return false;
    }
    const baseline = this.buildFullProductTargets(rb);
    try {
      const res = await apiPost('/api/allocation/flag_category_suggest', withLossKey({
        customer_id: rb.customer_id,
        category,
        category_targets: this._categoryTargets,
        baseline_product_targets: baseline,
        product_category: typeof getProductCategory === 'function' ? getProductCategory() : undefined,
        idle_cash: rb.idle_cash,
      }));
      const suggested = res.data.product_deltas || [];
      if (!suggested.length) {
        showToast('本类暂无可用的自动调仓建议');
        return false;
      }
      const merged = this.mergeCategorySuggestDeltas(rb, category, suggested);
      const applied = await this.tryApplyCategorySuggestMerge(rb, category, merged);
      if (!applied) return false;
      this.cacheProductLimitsFromDeltas(rb.product_deltas);
      this.revalidateAllProductLimits(rb);
      this.refreshCategoryPlanRows(rb, category);
      this.refreshPrescriptionProgressUI(rb);
      this.refreshDetailTable(rb);
      this.syncAllProductLimitUI(rb);
      const totalEl = document.getElementById('totalAssets');
      if (totalEl && rb.total_assets != null) {
        totalEl.textContent = formatMoney(rb.total_assets);
      }
      this.updateIdleCashPanel(rb, { showPlanStats: true });
      showToast('已填入一键自动调仓建议，可继续微调');
      return true;
    } catch (e) {
      showToast('智能建议失败: ' + e.message);
      return false;
    }
  },

  async applyCategoryRestore(rb, category, onUpdated) {
    if (this.categoryHasManualAddedProducts(rb, category)) {
      showToast('本类已手工添加产品，无法一键还原');
      return false;
    }
    if (!this._entryProductTargets) {
      showToast('缺少进入时的配仓快照，请重新进入配置方案');
      return false;
    }
    const baseline = this.buildFullProductTargets(rb);
    const product_targets = { ...baseline };
    let changed = false;
    (rb.product_deltas || []).forEach((d) => {
      if (d.category !== category) return;
      const entry = this._entryProductTargets[d.product_code];
      if (entry == null) return;
      if (Math.abs((product_targets[d.product_code] || 0) - entry) >= 0.01) {
        changed = true;
      }
      product_targets[d.product_code] = entry;
    });
    if (!changed) {
      this._manualDeltaEditedCategories.delete(category);
      this.syncCategorySuggestButtons(rb);
      this.refreshPrescriptionProgressUI(rb);
      showToast('本类已是进入时的配仓');
      return true;
    }
    try {
      const res = await apiPost('/api/allocation/manual_adjust', withLossKey({
        customer_id: rb.customer_id,
        product_category: typeof getProductCategory === 'function' ? getProductCategory() : undefined,
        idle_cash: this.planIdleCash(rb),
        product_targets,
        baseline_product_targets: baseline,
      }));
      this._manualDeltaEditedCategories.delete(category);
      if (typeof onUpdated === 'function') {
        onUpdated(res.data);
      }
      showToast('已还原至进入时的配仓');
      return true;
    } catch (e) {
      showToast('还原失败: ' + e.message);
      return false;
    }
  },

  shouldShowProductPicker(_category) {
    return true;
  },

  initCategoryAddProductConfirmModal() {
    const modal = document.getElementById('reduceCategoryAddModal');
    const msgEl = document.getElementById('reduceCategoryAddMessage');
    const confirmBtn = document.getElementById('reduceCategoryAddConfirm');
    const cancelBtn = document.getElementById('reduceCategoryAddCancel');
    if (!modal || modal.dataset.bound) return;
    modal.dataset.bound = '1';

    const close = (confirmed) => {
      modal.classList.remove('open');
      const resolve = this._categoryAddConfirmResolve;
      this._categoryAddConfirmResolve = null;
      if (resolve) resolve(!!confirmed);
    };

    if (confirmBtn) confirmBtn.onclick = () => close(true);
    if (cancelBtn) cancelBtn.onclick = () => close(false);
    modal.addEventListener('click', (e) => {
      if (e.target === modal) close(false);
    });
    this._categoryAddConfirmModal = modal;
    this._categoryAddConfirmMessageEl = msgEl;
  },

  promptCategoryAddProductConfirm(message) {
    this.initCategoryAddProductConfirmModal();
    const modal = this._categoryAddConfirmModal;
    const msgEl = this._categoryAddConfirmMessageEl;
    if (!modal) return Promise.resolve(true);

    if (msgEl) msgEl.textContent = message;

    return new Promise((resolve) => {
      this._categoryAddConfirmResolve = resolve;
      modal.classList.add('open');
    });
  },

  getCategoryAddProductConfirmMessage(category) {
    if (!this.hasCategoryPrescription()) return null;
    const prescribed = this.getPrescribedAdjust(category);
    if (prescribed == null) return null;
    if (prescribed < -0.01) {
      return '该笔钱建议减配，确认要新增产品么？';
    }
    if (Math.abs(prescribed) < 1) {
      return '该笔钱建议保持不变，确认要新增产品么？';
    }
    return null;
  },

  async tryOpenProductPicker(category, rb, categoryName) {
    const confirmMessage = this.getCategoryAddProductConfirmMessage(category);
    if (confirmMessage) {
      const confirmed = await this.promptCategoryAddProductConfirm(confirmMessage);
      if (!confirmed) return;
    }
    await this.openProductPicker(category, rb, categoryName);
  },

  holdingsFromOverview(overview) {
    const map = {};
    (overview?.categories || []).forEach(cat => {
      (cat.products || []).forEach(p => {
        const amount = Number(p.amount) || 0;
        if (p.code && amount > 0.01) map[p.code] = amount;
      });
    });
    return map;
  },

  async beginManualConfig(customerId, productCategory, overview) {
    this.resetManualState();
    const holdings = this.holdingsFromOverview(overview);
    const res = await apiPost('/api/allocation/manual_adjust', withLossKey({
      customer_id: customerId,
      product_category: productCategory,
      product_targets: holdings,
      baseline_product_targets: holdings,
      idle_cash: overview.idle_cash,
    }));
    return res.data;
  },

  getProductLimits(d) {
    if (d.min_amount != null) {
      return {
        min: d.min_amount || 0,
        max: d.max_amount != null ? d.max_amount : Infinity,
      };
    }
    const cached = this._productLimits[d.product_code];
    if (cached) return cached;
    return { min: 0, max: Infinity };
  },

  cacheProductLimits(products) {
    (products || []).forEach(p => {
      this._productLimits[p.code] = {
        min: p.min_amount || 0,
        max: p.max_amount != null ? p.max_amount : Infinity,
      };
    });
  },

  cacheProductLimitsFromDeltas(deltas) {
    (deltas || []).forEach(d => {
      if (d.min_amount == null) return;
      this._productLimits[d.product_code] = {
        min: d.min_amount || 0,
        max: d.max_amount != null ? d.max_amount : Infinity,
      };
    });
  },

  limitSideMessage(side, d) {
    if (side === 'max_over') {
      const max = d ? this.getProductLimits(d).max : Infinity;
      if (max < Infinity) {
        return `超过产品最高购买金额（${formatMoney(max)}）！`;
      }
      return '超过产品最高购买金额！';
    }
    if (side === 'max') return '已达产品上限！';
    if (side === 'min') {
      const minAmt = d ? this.getProductLimits(d).min : 0;
      if (minAmt > 0.01) {
        return `不满足起购金额（${formatMoney(minAmt)}）！`;
      }
      return '不满足起购金额！';
    }
    if (side === 'liquidate') return '类内调仓清仓！';
    if (side === 'zero_delta') return '添加产品无追加金额！请调整或删除该产品';
    return '';
  },

  zeroDeltaDraftMessage() {
    return '添加产品无追加金额！请调整或删除该产品';
  },

  isZeroDeltaNewDraft(d) {
    return this.isNewManualDraftProduct(d) && Math.abs(d.delta_amount) < 0.01;
  },

  /** 超过上限 / 不满足起购：强校验（已有产品失焦恢复，新增产品草稿锁定） */
  isBlockingLimitViolation(side) {
    if (!this.isProductLimitValidationEnabled()) return false;
    return side === 'max_over' || side === 'min';
  },

  isNewManualDraftProduct(d) {
    return !!d
      && this._manualAddedCodes.has(d.product_code)
      && d.current_amount <= 0.01;
  },

  getBlockingInvalidManualProducts(rb) {
    return [...this._manualValidationBlocked.keys()];
  },

  getValidationBlockReason(code) {
    return this._manualValidationBlocked.get(code);
  },

  setValidationBlock(code, reason) {
    this._manualValidationBlocked.set(code, reason);
  },

  clearValidationBlock(code, reason) {
    if (!reason || this._manualValidationBlocked.get(code) === reason) {
      this._manualValidationBlocked.delete(code);
    }
  },

  getActiveManualDraftBlockers(rb) {
    const reasons = new Map(this._manualValidationBlocked);
    (rb.product_deltas || []).forEach(d => {
      if (this.isZeroDeltaNewDraft(d)) {
        reasons.set(d.product_code, 'zero_delta');
      }
    });
    return reasons;
  },

  blockingEditGate(rb, editingCode) {
    const reasonMap = this.getActiveManualDraftBlockers(rb);
    const blockers = [...reasonMap.keys()];
    if (!blockers.length) return { ok: true };
    if (blockers.includes(editingCode)) return { ok: true };

    const parts = blockers.map((code) => {
      const d = rb.product_deltas.find((x) => x.product_code === code);
      if (!d) return null;
      const reason = reasonMap.get(code);
      if (reason === 'idle') {
        return `新增产品「${d.product_name}」：${this.idleCashInsufficientMessage()}`;
      }
      if (reason === 'max_over') {
        const { max } = this.getProductLimits(d);
        return `新增产品「${d.product_name}」超过产品最高购买金额${formatMoney(max)}`;
      }
      if (reason === 'min') {
        const { min } = this.getProductLimits(d);
        return `新增产品「${d.product_name}」不满足起购金额${formatMoney(min)}`;
      }
      if (reason === 'zero_delta') {
        return `新增产品「${d.product_name}」：${this.zeroDeltaDraftMessage()}`;
      }
      return `新增产品「${d.product_name}」未通过校验`;
    }).filter(Boolean);

    return {
      ok: false,
      message: `${parts.join('；')}，请先调整该产品或删除后再修改其他产品`,
    };
  },

  limitSideTag(side, d) {
    const msg = this.limitSideMessage(side, d);
    return msg ? msg.replace(/！$/, '') : '';
  },

  evaluateProductLimit(d) {
    const raw = d.target_amount;
    const cur = d.current_amount;
    const delta = d.delta_amount ?? (raw - cur);
    if (!this.isProductLimitValidationEnabled()) {
      if (raw <= 0.01 && cur > 0.01) return 'liquidate';
      return null;
    }
    const { min, max } = this.getProductLimits(d);
    if (raw > max + 0.01) return 'max_over';
    if (raw > 0.01 && max < Infinity && raw >= max - 0.01) return 'max';
    if (raw <= 0.01 && cur > 0.01) return 'liquidate';
    // 0 持仓首次买入：目标金额不低于起购
    if (cur <= 0.01 && raw > 0.01 && min > 0.01 && raw < min - 0.01) return 'min';
    // 已有持仓且已达起购：追加买入增量不低于起购（低于起购的存量持仓除外）
    if (
      cur > 0.01
      && cur >= min - 0.01
      && delta > 0.01
      && min > 0.01
      && delta < min - 0.01
    ) {
      return 'min';
    }
    return null;
  },

  revalidateAllProductLimits(rb) {
    (rb.product_deltas || []).forEach(d => {
      const side = this.evaluateProductLimit(d);
      if (d.limit_side === 'zero_delta') {
        d.limit_hit = true;
        d.limit_side = 'zero_delta';
      } else {
        d.limit_hit = !!side;
        d.limit_side = side || '';
      }
    });
  },

  syncAllProductLimitUI(rb) {
    this.editableDeltas(rb).forEach(d => this.syncProductRow(d));
    this.syncNewDraftValidationBlockedUI(rb);
  },

  syncNewDraftValidationBlockedUI(rb) {
    const grid = document.getElementById('categoryGrid');
    if (!grid) return;
    this._manualValidationBlocked.forEach((reason, code) => {
      const row = grid.querySelector(`.product-edit-row[data-product-code="${code}"]`);
      if (!row) return;
      const item = (rb.product_deltas || []).find(d => d.product_code === code);
      if (reason === 'idle') {
        this._setRowIdleError(row, true);
      } else if (item) {
        this._setRowIdleError(row, false);
        this._syncProductLimitState(row, item);
      }
    });
  },

  validateCanAddProduct(rb, picked) {
    if (this.getActiveManualDraftBlockers(rb).size) {
      return {
        ok: false,
        message: this.blockingEditGate(rb, '').message,
      };
    }
    const stats = this.calcIdleCashUsageForPlan(rb);
    const remaining = stats.remaining;
    const min = picked.min_amount || 0;
    const netSell = (rb.product_deltas || []).reduce(
      (s, d) => s + Math.min(d.delta_amount || 0, 0), 0
    );
    const needsReduceFirst = netSell > -0.01;

    if (remaining <= 0.01) {
      return {
        ok: false,
        code: 'idle',
        needsReduceFirst,
        shortfall: Math.max(min, -remaining),
        message: needsReduceFirst
          ? '追加持仓不足，可先减配其他产品释放资金，或追加追加持仓'
          : this.idleCashInsufficientMessage(),
      };
    }
    if (min > 0.01 && remaining < min - 0.01) {
      return {
        ok: false,
        code: 'idle',
        needsReduceFirst: false,
        shortfall: min - remaining,
        message: `剩余可追加 ${formatMoney(remaining)} 低于「${picked.name}」起购金额 ${formatMoney(min)}`,
      };
    }
    return { ok: true };
  },

  isPlanRowVisible(d) {
    return d.current_amount > 0
      || this._manualAddedCodes.has(d.product_code)
      || Math.abs(d.delta_amount) >= 1
      || d.target_amount > 0.01;
  },

  canDeleteManualProduct(d) {
    return d.current_amount <= 0.01 && this._manualAddedCodes.has(d.product_code);
  },

  editableDeltas(rb) {
    return [...rb.product_deltas]
      .filter(d => this.isPlanRowVisible(d))
      .sort((a, b) =>
        (a.category + a.product_code).localeCompare(b.category + b.product_code)
      );
  },

  categoryEditableDeltas(rb, category) {
    return rb.product_deltas
      .filter(d => d.category === category && this.isPlanRowVisible(d))
      .sort((a, b) => a.product_code.localeCompare(b.product_code));
  },

  /**
   * 追加持仓口径（方案态）：
   * - 本次已配置 = 调仓金额（delta）之和
   * - 剩余可追加 = 追加持仓 − 本次已配置
   */
  _idleCashStats(idleCash, amounts) {
    const configured = (amounts || []).reduce((sum, amount) => sum + (amount || 0), 0);
    const remaining = idleCash - configured;
    const releasedFromHoldings = configured < -0.01 && remaining > idleCash + 0.01
      ? -configured
      : 0;
    return {
      configured,
      remaining,
      releasedFromHoldings,
    };
  },

  calcIdleCashUsage(idleCash, categorySummary) {
    const amounts = (categorySummary || []).map((item) => item.adjust_amount || 0);
    return this._idleCashStats(idleCash, amounts);
  },

  calcIdleCashUsageFromDeltas(rb) {
    const amounts = (rb.product_deltas || []).map((d) => d.delta_amount || 0);
    return this._idleCashStats(rb.idle_cash || 0, amounts);
  },

  /** 方案态追加持仓统计：个性化按产品 delta 联动；引擎方案按大类 adjust 净额（避免类内调仓重复计入） */
  calcIdleCashUsageForPlan(rb) {
    if (this.isPersonalizedOrchestration()) {
      return this.calcIdleCashUsageFromDeltas(rb);
    }
    return this.calcIdleCashUsage(rb.idle_cash || 0, rb.category_summary);
  },

  planIdleCash(rb) {
    return rb && rb.idle_cash != null ? rb.idle_cash : 0;
  },

  isIdleCashSufficient(stats) {
    return stats.remaining >= -0.01;
  },

  idleCashInsufficientMessage() {
    return '追加持仓不足，请调整其他产品释放！';
  },

  _idleReleaseNoteHtml(stats) {
    const released = stats && stats.releasedFromHoldings > 0.01 ? stats.releasedFromHoldings : 0;
    if (!released) return '';
    return `<span class="idle-cash-release-note">（含存量持仓释放资金 ${formatMoney(released)}）</span>`;
  },

  updateIdleCashPanel(rb, options = {}) {
    const { showPlanStats = false } = options;
    const idleEl = document.getElementById('idleCash');
    const cfgEl = document.getElementById('configuredIdle');
    const remEl = document.getElementById('remainingIdle');
    if (!idleEl) return;

    const idle = rb.idle_cash || 0;
    const group = document.getElementById('idleCashGroup');
    const showIdlePanel = idle > 0.01 || showPlanStats;
    if (group) group.style.display = showIdlePanel ? '' : 'none';
    if (!showIdlePanel) {
      if (cfgEl) cfgEl.style.display = 'none';
      if (remEl) remEl.style.display = 'none';
      return;
    }

    idleEl.textContent = '追加持仓 ' + formatMoney(idle);

    const stats = showPlanStats
      ? this.calcIdleCashUsageForPlan(rb)
      : this._idleCashStats(idle, []);

    if (cfgEl) {
      cfgEl.style.display = 'block';
      cfgEl.innerHTML = '本次已配置追加持仓 ' + formatMoney(stats.configured)
        + this._idleReleaseNoteHtml(stats);
    }
    if (remEl) {
      remEl.style.display = 'block';
      remEl.innerHTML = '剩余可追加 ' + formatMoney(stats.remaining)
        + this._idleReleaseNoteHtml(stats);
    }
  },

  _clearRowIdleErrors(container) {
    if (!container) return;
    container.querySelectorAll('.product-edit-block').forEach(block => {
      block.querySelector('.product-edit-row')?.classList.remove('idle-edit-error');
      const err = block.querySelector('.product-row-error');
      if (err) err.style.display = 'none';
    });
  },

  _clearRowProductLimitErrors(container) {
    if (!container) return;
    container.querySelectorAll('.product-edit-block').forEach(block => {
      const row = block.querySelector('.product-edit-row');
      if (row) row.classList.remove('limit-hit-error');
      const err = block.querySelector('.product-limit-error');
      if (err) {
        err.textContent = '';
        err.style.display = 'none';
      }
    });
  },

  _setRowIdleError(row, hasError) {
    if (!row) return;
    const block = row.closest('.product-edit-block');
    if (!block) return;
    row.classList.toggle('idle-edit-error', hasError);
    const err = block.querySelector('.product-row-error');
    if (err) {
      if (hasError) {
        err.textContent = this.idleCashInsufficientMessage();
      }
      err.style.display = hasError ? 'block' : 'none';
    }
  },

  buildFullProductTargets(rb) {
    const map = {};
    (rb.product_deltas || []).forEach(d => {
      map[d.product_code] = d.target_amount;
    });
    return map;
  },

  buildAdjustPayload(rb, editedCode) {
    const baseline = this.buildFullProductTargets(rb);
    if (!editedCode || baseline[editedCode] === undefined) {
      return { product_targets: baseline, baseline_product_targets: baseline };
    }
    return {
      product_targets: { [editedCode]: baseline[editedCode] },
      baseline_product_targets: baseline,
    };
  },

  mergeProductDeltas(prevDeltas, newDeltas, editedCode) {
    if (!editedCode) return newDeltas;
    const newMap = Object.fromEntries(newDeltas.map(d => [d.product_code, d]));
    const merged = prevDeltas.map(d => {
      const updated = newMap[d.product_code];
      return updated ? { ...d, ...updated } : d;
    });
    const codes = new Set(merged.map(d => d.product_code));
    prevDeltas.forEach(d => {
      if (!codes.has(d.product_code) && this._manualAddedCodes.has(d.product_code)) {
        merged.push(d);
      }
    });
    newDeltas.forEach(d => {
      if (!codes.has(d.product_code)) {
        merged.push(d);
        codes.add(d.product_code);
      }
    });
    return merged.sort((a, b) =>
      (a.category + a.product_code).localeCompare(b.category + b.product_code)
    );
  },

  updatePlanCardSummaries(rb) {
    rb.category_summary.forEach(s => {
      const card = document.querySelector(`.plan-card.${s.category}`);
      if (!card) return;
      const badge = card.querySelector('.card-title span:last-child');
      if (badge) {
        badge.className = s.in_band ? 'badge-yes' : 'badge-no';
        badge.textContent = s.in_band ? '✓ 在区间内' : '△ 次优解';
      }
      const fields = card.querySelectorAll(':scope > .field:not(.prescription-progress):not(.band-cell)');
      if (fields.length >= 4) {
        fields[0].querySelector('.value').textContent = formatPct(s.current_ratio);
        fields[1].querySelector('.value').textContent = formatPct(s.target_ratio);
        const adjustEl = fields[2].querySelector('.value');
        adjustEl.textContent = `${s.adjust_amount >= 0 ? '+' : ''}${formatMoney(s.adjust_amount)}`;
        adjustEl.className = `value ${s.adjust_amount >= 0 ? 'action-buy' : 'action-sell'}`;
        fields[3].querySelector('.value').textContent = formatPct(s.final_ratio);
      }
      const bandField = card.querySelector(':scope > .field.band-cell');
      if (bandField) {
        bandField.title = formatBandTooltip(s.band);
        const bandVal = bandField.querySelector('.value');
        if (bandVal) bandVal.textContent = formatBandRange(s.band);
      }
    });
    this.refreshPrescriptionProgressUI(rb);
  },

  refreshPrescriptionProgressUI(rb) {
    if (!this.hasCategoryPrescription()) return;
    (rb.category_summary || []).forEach((s) => {
      const card = document.querySelector(`.personalized-card.${s.category}`);
      if (!card) return;
      const actionable = this.isCategoryActionable(s.category);
      if (actionable) {
        const existing = card.querySelector('.rx-progress-wrap');
        const html = this.renderPrescriptionProgressBar(rb, s.category).trim();
        if (!html) {
          if (existing) existing.remove();
        } else if (existing) {
          existing.outerHTML = html;
        } else {
          const summary = card.querySelector('.rx-summary');
          if (summary) summary.insertAdjacentHTML('afterend', html);
        }
      }
      this.syncPersonalizedBandUI(rb, s.category);
    });
  },

  _syncTargetDisplay(row, amount) {
    const display = row.querySelector('[data-field="target-display"]');
    if (display) display.textContent = formatMoney(amount);
  },

  syncProductRow(d) {
    if (!d) return;
    const row = document.querySelector(
      `.product-edit-row[data-product-code="${d.product_code}"], tr[data-product-code="${d.product_code}"]`
    );
    if (!row) return;
    const deltaInput = row.querySelector('[data-field="delta"]');
    this._syncTargetDisplay(row, d.target_amount);
    if (deltaInput) deltaInput.value = Math.round(d.delta_amount);
    this._syncActionDisplay(row, d.action);
    this._syncProductLimitState(row, d);
  },

  _syncProductLimitState(row, d) {
    const block = row.closest('.product-edit-block');
    if (!block) return;
    const msg = this.limitSideMessage(d.limit_side, d);
    row.classList.toggle('limit-hit-error', !!msg);
    const limitErr = block.querySelector('.product-limit-error');
    if (limitErr) {
      limitErr.textContent = msg;
      limitErr.style.display = msg ? 'block' : 'none';
    }
  },

  applyPlanLinkage(data, editedCode) {
    const rb = data.rebalance;
    const ex = data.explanation;

    this.updatePlanBanner(rb);

    if (this.isPersonalizedOrchestration()) {
      this.refreshPrescriptionProgressUI(rb);
      this.syncCategorySuggestButtons(rb);
      if (editedCode) {
        const item = rb.product_deltas.find((d) => d.product_code === editedCode);
        if (item) this.syncProductRow(item);
      }
    } else {
      this.updatePlanCardSummaries(rb);
    }
    const totalEl = document.getElementById('totalAssets');
    if (totalEl && rb.total_assets != null) {
      totalEl.textContent = formatMoney(rb.total_assets);
    }
    this.updateIdleCashPanel(rb, { showPlanStats: true });

    const detailBody = document.getElementById('detailBody');
    if (detailBody) detailBody.innerHTML = this.renderReadonlyDetailRows(rb);

    this.updateExplanation(ex);

    this.revalidateAllProductLimits(rb);
    this.syncAllProductLimitUI(rb);
  },

  renderSummaryRows(rb) {
    return rb.category_summary.map(s => `
      <tr>
        <td>${s.category_name}</td>
        <td>${formatPct(s.current_ratio)}</td>
        <td>${formatPct(s.target_ratio)}</td>
        <td class="${s.adjust_amount >= 0 ? 'action-buy' : 'action-sell'}">${s.adjust_amount >= 0 ? '+' : ''}${formatMoney(s.adjust_amount)}</td>
        <td>${formatPct(s.final_ratio)}</td>
        <td class="band-cell ${s.in_band ? 'badge-yes' : 'badge-no'}" title="${formatBandTooltip(s.band)}">${s.in_band ? '✓ 在区间内' : '△ 次优解'} <span class="band-hint">ⓘ</span></td>
      </tr>
    `).join('');
  },

  renderPlanCards(rb, options = {}) {
    const { smartAllocation = false } = options;
    return rb.category_summary.map(s => `
      <div class="category-card plan-card ${s.category}">
        <div class="card-title">
          <span>${s.category_name}</span>
          <span class="${s.in_band ? 'badge-yes' : 'badge-no'}">${s.in_band ? '✓ 在区间内' : '△ 次优解'}</span>
        </div>
        <div class="field"><span>当前占比</span><span class="value">${formatPct(s.current_ratio)}</span></div>
        <div class="field"><span>目标占比</span><span class="value">${formatPct(s.target_ratio)}</span></div>
        <div class="field">
          <span>调整金额</span>
          <span class="value ${s.adjust_amount >= 0 ? 'action-buy' : 'action-sell'}">${s.adjust_amount >= 0 ? '+' : ''}${formatMoney(s.adjust_amount)}</span>
        </div>
        ${smartAllocation && !this.hasCategoryPrescription() ? this.renderCategoryPrescriptionProgress(rb, s.category) : ''}
        <div class="field"><span>最终占比</span><span class="value plan-highlight">${formatPct(s.final_ratio)}</span></div>
        <div class="field band-cell" title="${formatBandTooltip(s.band)}">
          <span>模型区间 <span class="band-hint">ⓘ</span></span>
          <span class="value">${formatBandRange(s.band)}</span>
        </div>
        <div class="product-section-label">本类产品调仓明细</div>
        <div class="product-detail plan-product-detail always-open" id="products-plan-${s.category}">
          ${smartAllocation
            ? this.renderEditableCategoryProductRows(rb, s.category)
            : this.renderCategoryProductRows(rb.product_deltas, s.category)}
        </div>
      </div>
    `).join('');
  },

  renderCategoryProductRows(deltas, category) {
    const rows = deltas.filter(
      d => d.category === category && (Math.abs(d.delta_amount) >= 1 || d.current_amount > 0)
    );
    if (!rows.length) return '<div class="product-row muted">暂无产品变动</div>';
    return rows.map(d => `
      <div class="product-plan-row">
        <div class="product-plan-name">${d.product_name}</div>
        <div class="product-plan-metrics">
          <span>持仓 ${formatMoney(d.current_amount)}</span>
          <span>→ ${formatMoney(d.target_amount)}</span>
          <span class="${d.delta_amount >= 0 ? 'action-buy' : 'action-sell'}">${d.delta_amount >= 0 ? '+' : ''}${formatMoney(d.delta_amount)}</span>
          <span class="action-tag action-${d.action}">${this.actionLabel(d.action)}</span>
          ${d.limit_hit ? `<span class="limit-hit-tag">${this.limitSideTag(d.limit_side, d)}</span>` : ''}
        </div>
      </div>
    `).join('');
  },

  renderProductEditBlock(d) {
    const deletable = this.canDeleteManualProduct(d);
    return `
      <div class="product-edit-block">
        <div class="product-plan-row product-edit-row${d.limit_hit ? ' limit-hit-error' : ''}" data-product-code="${d.product_code}">
          <div class="product-plan-name-row">
            <div class="product-plan-name">${d.product_name}</div>
            ${deletable ? `<button type="button" class="btn btn-link btn-remove-product" data-action="remove-product" data-code="${d.product_code}">删除</button>` : ''}
          </div>
          <div class="product-plan-metrics">
            <span class="metric-label">持仓 ${formatMoney(d.current_amount)}</span>
            <span class="metric-edit">目标
              <span class="metric-value" data-field="target-display">${formatMoney(d.target_amount)}</span>
            </span>
            <label class="metric-edit">增减
              <input type="number" class="edit-input edit-input-sm" data-field="delta"
                value="${Math.round(d.delta_amount)}" step="1000" data-code="${d.product_code}">
            </label>
            <span class="metric-edit">操作
              <span class="action-tag action-${d.action}" data-field="action-display">${this.actionLabel(d.action)}</span>
            </span>
          </div>
        </div>
        <div class="product-limit-error" style="display:${d.limit_hit ? 'block' : 'none'}">${this.limitSideMessage(d.limit_side, d)}</div>
        <div class="product-row-error" style="display:none">追加持仓不足，请调整其他产品释放！</div>
      </div>
    `;
  },

  renderEditableCategoryProductRows(rb, category) {
    const rows = this.categoryEditableDeltas(rb, category);
    const rowHtml = rows.length
      ? rows.map(d => this.renderProductEditBlock(d)).join('')
      : '';
    const pickerHtml = this.shouldShowProductPicker(category)
      ? `<div class="product-picker-bar">
        <button type="button" class="btn btn-link btn-picker" data-action="pick-product" data-category="${category}">+ 选择产品</button>
      </div>`
      : '';
    return `${rowHtml}${pickerHtml}`;
  },

  refreshCategoryPlanRows(rb, category) {
    const el = document.getElementById(`products-plan-${category}`);
    if (el) {
      el.innerHTML = this.renderEditableCategoryProductRows(rb, category);
    }
    this.syncCategorySuggestButtons(rb);
  },

  refreshDetailTable(rb) {
    const detailBody = document.getElementById('detailBody');
    if (!detailBody) return;
    if (detailBody.closest('.editable-detail-table')) {
      detailBody.innerHTML = this.renderEditableDetailRows(rb);
    } else {
      detailBody.innerHTML = this.renderReadonlyDetailRows(rb);
    }
  },

  async loadCategoryCandidates(category) {
    if (this._categoryCandidatesCache[category]) {
      return this._categoryCandidatesCache[category];
    }
    const res = await apiGet(`/api/products/candidates?category=${encodeURIComponent(category)}`);
    this._categoryCandidatesCache[category] = res.data.products || [];
    this.cacheProductLimits(this._categoryCandidatesCache[category]);
    return this._categoryCandidatesCache[category];
  },

  async openProductPicker(category, rb, categoryName) {
    this._pickerCategory = category;
    this._pickerRb = rb;
    this._pickerSelectedCode = null;
    this._pickerTab = 'manual';
    this._pickerAiProducts = [];
    const modal = document.getElementById('productPickerModal');
    const nameEl = document.getElementById('pickerCategoryName');
    const confirmBtn = document.getElementById('productPickerConfirm');
    if (!modal) return;

    if (nameEl) nameEl.textContent = categoryName || category;
    if (confirmBtn) confirmBtn.disabled = true;
    this._updatePickerHint(rb);
    this._setPickerTab('manual');
    modal.classList.add('open');
    await this._loadManualPickerList(rb, category);
  },

  _updatePickerHint(rb) {
    const hintEl = document.getElementById('productPickerHint');
    const stats = this.calcIdleCashUsageForPlan(rb);
    if (hintEl) {
      hintEl.textContent = `当前剩余可追加：${formatMoney(stats.remaining)}（添加新产品须剩余金额 > 0 且不低于产品起购金额）`;
    }
  },

  _setPickerTab(tab) {
    this._pickerTab = tab;
    this._pickerSelectedCode = null;
    const confirmBtn = document.getElementById('productPickerConfirm');
    if (confirmBtn) confirmBtn.disabled = true;

    document.querySelectorAll('[data-picker-tab]').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.pickerTab === tab);
    });
    const manualPanel = document.getElementById('productPickerManualPanel');
    const aiPanel = document.getElementById('productPickerAiPanel');
    if (manualPanel) manualPanel.style.display = tab === 'manual' ? 'block' : 'none';
    if (aiPanel) aiPanel.style.display = tab === 'ai' ? 'block' : 'none';
  },

  _getPickerExcludeCodes(rb, category) {
    return this.categoryEditableDeltas(rb, category).map(d => d.product_code);
  },

  async _loadManualPickerList(rb, category) {
    const listEl = document.getElementById('productPickerList');
    if (!listEl) return;
    listEl.innerHTML = '<div class="product-row muted">加载中...</div>';

    try {
      const candidates = await this.loadCategoryCandidates(category);
      const existing = new Set(this._getPickerExcludeCodes(rb, category));
      const available = candidates.filter(p => !existing.has(p.code));
      if (!available.length) {
        listEl.innerHTML = '<div class="product-row muted">该大类候选产品已全部在明细中</div>';
        return;
      }
      listEl.innerHTML = available.map(p => this._renderPickerChoice(p, 'productPickerChoice')).join('');
      this._bindPickerRadios(listEl, 'productPickerChoice');
    } catch (e) {
      listEl.innerHTML = `<div class="product-row muted">加载失败: ${e.message}</div>`;
    }
  },

  async _loadAiPickerList(rb, category) {
    const listEl = document.getElementById('productPickerAiList');
    const metaEl = document.getElementById('productPickerAiMeta');
    if (!listEl) return;
    listEl.innerHTML = '<div class="product-row muted">AI 选品分析中...</div>';
    if (metaEl) metaEl.innerHTML = '';

    const cid = getCustomerId();
    if (!cid) {
      listEl.innerHTML = '<div class="product-row muted">请先选择客户</div>';
      return;
    }

    try {
      const exclude = this._getPickerExcludeCodes(rb, category).join(',');
      const res = await apiGet(
        `/api/products/ai_recommend?customer_id=${encodeURIComponent(cid)}`
        + `&category=${encodeURIComponent(category)}`
        + (exclude ? `&exclude=${encodeURIComponent(exclude)}` : '')
      );
      const data = res.data;
      this._pickerAiProducts = data.products || [];
      this.cacheProductLimits(this._pickerAiProducts);

      if (metaEl) {
        metaEl.innerHTML = `
          <span class="product-picker-ai-badge">AI 模拟推荐</span>
          <span>基于客户风险档位 <strong>${data.customer_risk_level_name || ''}</strong>
          （档位 ${data.customer_risk_level}）匹配本类未持仓产品</span>`;
      }

      if (!this._pickerAiProducts.length) {
        listEl.innerHTML = '<div class="product-row muted">暂无合适推荐（可能均已持仓或无可匹配产品）</div>';
        return;
      }

      listEl.innerHTML = this._pickerAiProducts.map(p => this._renderAiPickerChoice(p)).join('');
      this._bindPickerRadios(listEl, 'productPickerAiChoice');
    } catch (e) {
      listEl.innerHTML = `<div class="product-row muted">推荐失败: ${e.message}</div>`;
    }
  },

  _renderPickerChoice(p, inputName) {
    return `
      <label class="product-picker-item">
        <input type="radio" name="${inputName}" value="${p.code}">
        <span class="product-picker-item-body">
          <span class="product-picker-item-name">${this._escapeHtml(p.name)}</span>
          <span class="product-picker-item-meta">${p.code} · 起购 ${formatMoney(p.min_amount)}</span>
        </span>
      </label>`;
  },

  _renderAiPickerChoice(p) {
    return `
      <label class="product-picker-item product-picker-item-ai">
        <input type="radio" name="productPickerAiChoice" value="${p.code}">
        <span class="product-picker-item-body">
          <span class="product-picker-item-name">${this._escapeHtml(p.name)}</span>
          <span class="product-picker-item-meta">${p.code} · R${p.risk_level} · 起购 ${formatMoney(p.min_amount)}</span>
          <span class="product-picker-item-reason">${this._escapeHtml(p.recommend_reason || '')}</span>
        </span>
      </label>`;
  },

  _bindPickerRadios(listEl, inputName) {
    const confirmBtn = document.getElementById('productPickerConfirm');
    listEl.querySelectorAll(`input[name="${inputName}"]`).forEach(input => {
      input.addEventListener('change', () => {
        this._pickerSelectedCode = input.value;
        if (confirmBtn) confirmBtn.disabled = !this._pickerSelectedCode;
      });
    });
  },

  _escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text == null ? '' : String(text);
    return d.innerHTML;
  },

  _getPickerProduct(code) {
    const category = this._pickerCategory;
    const fromManual = (this._categoryCandidatesCache[category] || []).find(p => p.code === code);
    if (fromManual) return fromManual;
    return (this._pickerAiProducts || []).find(p => p.code === code);
  },

  async switchProductPickerTab(tab) {
    if (tab === this._pickerTab) return;
    this._setPickerTab(tab);
    const rb = this._pickerRb;
    const category = this._pickerCategory;
    if (!rb || !category) return;
    if (tab === 'ai') {
      await this._loadAiPickerList(rb, category);
    } else {
      await this._loadManualPickerList(rb, category);
    }
  },

  closeProductPicker() {
    const modal = document.getElementById('productPickerModal');
    if (modal) modal.classList.remove('open');
    this._pickerCategory = null;
    this._pickerRb = null;
    this._pickerSelectedCode = null;
    this._pickerTab = 'manual';
    this._pickerAiProducts = [];
  },

  async removeManualProduct(rb, code, getContext, onUpdated) {
    const item = rb.product_deltas.find(d => d.product_code === code);
    if (!item || !this.canDeleteManualProduct(item)) return false;

    const hadAllocation = Math.abs(item.delta_amount) >= 1 || item.target_amount > 0.01;
    const category = item.category;
    const name = item.product_name;
    const topUpAmount = this._productIdleTopUps[code] || 0;

    rb.product_deltas = rb.product_deltas.filter(d => d.product_code !== code);
    this._manualAddedCodes.delete(code);
    delete this._productIdleTopUps[code];
    this.clearValidationBlock(code);
    this.refreshCategoryPlanRows(rb, category);
    this.refreshDetailTable(rb);
    this.updateIdleCashPanel(rb, { showPlanStats: true });

    if (topUpAmount > 0.01) {
      const stats = this.calcIdleCashUsageForPlan(rb);
      const revertible = Math.min(
        topUpAmount, rb.idle_cash || 0, Math.max(0, stats.remaining)
      );
      if (revertible < 0.01) {
        showToast('为添加该产品追加的金额已被方案占用，无法自动取消');
      } else {
        const reverted = await this.promptRevertIdleTopUp(rb, topUpAmount, name);
        if (reverted) {
          const totalEl = document.getElementById('totalAssets');
          if (totalEl) totalEl.textContent = formatMoney(rb.total_assets);
        }
      }
    }

    if (hadAllocation && onUpdated) {
      const ctx = getContext();
      if (ctx) {
        this._submitPlanRefresh(ctx, onUpdated);
        return true;
      }
    }
    showToast(`已移除 ${name}`);
    this._notifyLocalPlanSync();
    return true;
  },

  async confirmProductPicker(rb, categoryNameMap) {
    const category = this._pickerCategory;
    const code = this._pickerSelectedCode;
    if (!category || !code || !rb) return false;

    if (rb.product_deltas.some(d => d.product_code === code)) {
      this.closeProductPicker();
      return false;
    }

    const picked = this._getPickerProduct(code);
    if (!picked) return false;

    const idleBefore = rb.idle_cash || 0;
    let gate = this.validateCanAddProduct(rb, picked);
    if (!gate.ok && gate.code === 'idle') {
      const topped = await this.promptIdleCashGuide(rb, gate, { forAddProduct: true });
      if (!topped) return false;
      const added = (rb.idle_cash || 0) - idleBefore;
      if (added > 0.01) {
        this._productIdleTopUps[code] = (this._productIdleTopUps[code] || 0) + added;
      }
      gate = this.validateCanAddProduct(rb, picked);
      if (!gate.ok) {
        showToast(gate.message || '追加后仍不足，请继续追加或减配释放资金');
        return false;
      }
    } else if (!gate.ok) {
      showToast(gate.message);
      return false;
    }

    this.cacheProductLimits([picked]);
    this._manualAddedCodes.add(code);
    rb.product_deltas.push({
      product_code: picked.code,
      product_name: picked.name,
      category: picked.category || category,
      min_amount: picked.min_amount,
      max_amount: picked.max_amount,
      current_amount: 0,
      target_amount: 0,
      delta_amount: 0,
      action: 'hold',
      limit_hit: false,
      limit_side: '',
    });
    rb.product_deltas.sort((a, b) =>
      (a.category + a.product_code).localeCompare(b.category + b.product_code)
    );

    this.refreshCategoryPlanRows(rb, category);
    this.refreshDetailTable(rb);
    this.syncCategorySuggestButtons(rb);
    this.closeProductPicker();
    showToast(`已添加 ${picked.name}，请填写增减仓金额`);
    this._notifyLocalPlanSync();
    return true;
  },

  bindPlanGrid(container, getContext, onUpdated) {
    if (!container) return;
    container.addEventListener('click', (e) => {
      const orchestrationBtn = e.target.closest('[data-action="category-suggest"], [data-action="category-restore"]');
      if (orchestrationBtn) {
        if (orchestrationBtn.disabled) return;
        const ctx = getContext();
        if (!ctx) return;
        const category = orchestrationBtn.dataset.category;
        if (orchestrationBtn.dataset.action === 'category-restore') {
          this.applyCategoryRestore(ctx.rb, category, (data) => onUpdated(data));
        } else {
          this.applyCategorySuggest(ctx.rb, category);
        }
        return;
      }
      const pickBtn = e.target.closest('[data-action="pick-product"]');
      if (pickBtn) {
        const ctx = getContext();
        if (!ctx) return;
        const gate = this.blockingEditGate(ctx.rb, '');
        if (!gate.ok) {
          showToast(gate.message);
          return;
        }
        const category = pickBtn.dataset.category;
        const catSummary = ctx.rb.category_summary.find(s => s.category === category);
        const categoryName = catSummary ? catSummary.category_name : category;
        this.tryOpenProductPicker(category, ctx.rb, categoryName);
        return;
      }
      const removeBtn = e.target.closest('[data-action="remove-product"]');
      if (removeBtn) {
        const ctx = getContext();
        if (!ctx) return;
        this.removeManualProduct(ctx.rb, removeBtn.dataset.code, getContext, onUpdated);
      }
    });
  },

  initProductPicker(getContext) {
    const cancelBtn = document.getElementById('productPickerCancel');
    const confirmBtn = document.getElementById('productPickerConfirm');
    const modal = document.getElementById('productPickerModal');
    const tabs = document.getElementById('productPickerTabs');
    if (cancelBtn) {
      cancelBtn.onclick = () => this.closeProductPicker();
    }
    if (modal) {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) this.closeProductPicker();
      });
    }
    if (tabs) {
      tabs.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-picker-tab]');
        if (!btn) return;
        this.switchProductPickerTab(btn.dataset.pickerTab);
      });
    }
    if (confirmBtn) {
      confirmBtn.onclick = async () => {
        const ctx = getContext();
        if (ctx) await this.confirmProductPicker(ctx.rb);
      };
    }
  },

  renderReadonlyDetailRows(rb) {
    return this.editableDeltas(rb).map(d => `
        <tr class="${d.limit_hit ? 'limit-hit-row' : ''}">
          <td>${this.categoryName(rb, d.category)}</td>
          <td>${d.product_name}${d.limit_hit ? ` <span class="limit-hit-tag">${this.limitSideTag(d.limit_side, d)}</span>` : ''}</td>
          <td>${formatMoney(d.current_amount)}</td>
          <td>${formatMoney(d.target_amount)}</td>
          <td class="${d.delta_amount >= 0 ? 'action-buy' : 'action-sell'}">${d.delta_amount >= 0 ? '+' : ''}${formatMoney(d.delta_amount)}</td>
          <td><span class="action-tag action-${d.action}">${this.actionLabel(d.action)}</span></td>
        </tr>
      `).join('');
  },

  renderEditableDetailRows(rb) {
    const deltas = this.editableDeltas(rb);
    return deltas.map(d => `
      <tr data-product-code="${d.product_code}">
        <td>${this.categoryName(rb, d.category)}</td>
        <td>${d.product_name}</td>
        <td>${formatMoney(d.current_amount)}</td>
        <td><span data-field="target-display">${formatMoney(d.target_amount)}</span></td>
        <td>
          <input type="number" class="edit-input" data-field="delta"
            value="${Math.round(d.delta_amount)}" step="1000"
            data-code="${d.product_code}">
        </td>
        <td>
          <span class="action-tag action-${d.action}" data-field="action-display">${this.actionLabel(d.action)}</span>
        </td>
      </tr>
    `).join('');
  },

  categoryName(rb, code) {
    const item = rb.category_summary.find(s => s.category === code);
    return item ? item.category_name : code;
  },

  toggleProducts(id) {
    const el = document.getElementById('products-' + id);
    if (el) el.classList.toggle('open');
  },

  bindDetailEditor(container, getContext, onUpdated) {
    if (!container) return;
    container.addEventListener('input', (e) => {
      const el = e.target;
      if (!el.classList.contains('edit-input')) return;
      this._onFieldPreview(el);
    });
    container.addEventListener('focusin', (e) => {
      const el = e.target;
      if (!el.classList.contains('edit-input') || el.dataset.field !== 'delta') return;
      const ctx = getContext();
      if (!ctx) return;
      const code = el.dataset.code;
      const gate = this.blockingEditGate(ctx.rb, code);
      if (!gate.ok) {
        showToast(gate.message);
        el.blur();
        return;
      }
      const item = ctx.rb.product_deltas.find(d => d.product_code === code);
      if (item) {
        el.dataset.committedDelta = String(Math.round(item.delta_amount));
      }
    });
    container.addEventListener('keydown', (e) => {
      const el = e.target;
      if (!el.classList.contains('edit-input')) return;
      if (e.key !== 'Enter') return;
      e.preventDefault();
      el._skipNextBlur = true;
      this._onFieldCommit(el, getContext, onUpdated);
    });
    container.addEventListener('focusout', (e) => {
      const el = e.target;
      if (!el.classList.contains('edit-input') || el.dataset.field !== 'delta') return;
      if (el._skipNextBlur) {
        el._skipNextBlur = false;
        return;
      }
      this._onFieldCommit(el, getContext, onUpdated);
    });
    container.addEventListener('change', (e) => {
      const el = e.target;
      if (!el.classList.contains('edit-select')) return;
      this._onActionChange(el, getContext, onUpdated);
    });
  },

  _findEditRow(el) {
    return el.closest('.product-edit-row') || el.closest('tr[data-product-code]');
  },

  _syncActionDisplay(row, action) {
    const actionSelect = row.querySelector('[data-field="action"]');
    if (actionSelect) {
      actionSelect.value = action;
      return;
    }
    const display = row.querySelector('[data-field="action-display"]');
    if (display) {
      display.textContent = this.actionLabel(action);
      display.className = `action-tag action-${action}`;
    }
  },

  _onFieldPreview(el) {
    const row = this._findEditRow(el);
    if (!row || el.dataset.field !== 'delta') return;
    const delta = parseFloat(el.value) || 0;
    this._syncActionDisplay(row, this.actionFromDelta(delta));
  },

  _revertDeltaCommit(el, row, item, committedDelta, rb) {
    item.delta_amount = committedDelta;
    item.target_amount = item.current_amount + committedDelta;
    item.action = this.actionFromDelta(committedDelta);
    const deltaInput = row.querySelector('[data-field="delta"]');
    if (deltaInput) deltaInput.value = Math.round(committedDelta);
    this._syncTargetDisplay(row, item.target_amount);
    this._syncActionDisplay(row, item.action);
    const limitSide = this.evaluateProductLimit(item);
    item.limit_hit = !!limitSide;
    item.limit_side = limitSide || '';
    this._syncProductLimitState(row, item);
    el.dataset.committedDelta = String(Math.round(committedDelta));
    if (rb) {
      this.updateIdleCashPanel(rb, { showPlanStats: true });
    }
  },

  _onFieldCommit(el, getContext, onUpdated) {
    const ctx = getContext();
    if (!ctx) return;
    const code = el.dataset.code;
    const field = el.dataset.field;
    const row = this._findEditRow(el);
    if (!row) return;
    if (field !== 'delta') return;

    const deltaInput = row.querySelector('[data-field="delta"]');
    const item = ctx.rb.product_deltas.find(d => d.product_code === code);
    if (!item) return;

    const gate = this.blockingEditGate(ctx.rb, code);
    if (!gate.ok) {
      showToast(gate.message);
      return;
    }

    this._lastEditedCode = code;

    const delta = parseFloat(el.value) || 0;
    const committed = el.dataset.committedDelta !== undefined
      ? parseFloat(el.dataset.committedDelta)
      : item.delta_amount;
    if (Math.abs(delta - committed) < 0.01) return;

    item.delta_amount = delta;
    item.target_amount = item.current_amount + delta;
    item.action = this.actionFromDelta(delta);
    if (deltaInput) deltaInput.value = Math.round(delta);
    this._syncTargetDisplay(row, item.target_amount);
    this._syncActionDisplay(row, item.action);

    if (this.isZeroDeltaNewDraft(item)) {
      showToast(this.zeroDeltaDraftMessage());
      item.limit_hit = true;
      item.limit_side = 'zero_delta';
      this.setValidationBlock(code, 'zero_delta');
      this._syncProductLimitState(row, item);
      return;
    }
    this.clearValidationBlock(code, 'zero_delta');

    const limitSide = this.evaluateProductLimit(item);
    if (this.isBlockingLimitViolation(limitSide)) {
      showToast(this.limitSideMessage(limitSide, item));
      if (this.isNewManualDraftProduct(item)) {
        item.limit_hit = true;
        item.limit_side = limitSide;
        this.setValidationBlock(code, limitSide);
        this._syncProductLimitState(row, item);
        return;
      }
      this._revertDeltaCommit(el, row, item, committed, ctx.rb);
      return;
    }

    item.limit_hit = !!limitSide;
    item.limit_side = limitSide || '';
    const prevBlock = this.getValidationBlockReason(code);
    if (prevBlock === 'max_over' || prevBlock === 'min') {
      this.clearValidationBlock(code, prevBlock);
    }
    this.clearValidationBlock(code, 'zero_delta');
    this._syncProductLimitState(row, item);

    this._afterEditValidate(ctx, onUpdated, row, el, committed, item);
  },

  _afterEditValidate(ctx, onUpdated, row, el, committedDelta, item) {
    const stats = this.calcIdleCashUsageForPlan(ctx.rb);
    if (!this.isIdleCashSufficient(stats)) {
      const netSell = (ctx.rb.product_deltas || []).reduce(
        (s, d) => s + Math.min(d.delta_amount || 0, 0), 0
      );
      const needsReduceFirst = netSell > -0.01;
      const finishReject = () => {
        if (this.isNewManualDraftProduct(item)) {
          this.setValidationBlock(item.product_code, 'idle');
          this._setRowIdleError(row, true);
          this.updateIdleCashPanel(ctx.rb, { showPlanStats: true });
          this.revalidateAllProductLimits(ctx.rb);
          this.syncAllProductLimitUI(ctx.rb);
          return;
        }
        this._revertDeltaCommit(el, row, item, committedDelta, ctx.rb);
        this.revalidateAllProductLimits(ctx.rb);
        this.syncAllProductLimitUI(ctx.rb);
      };

      const msg = needsReduceFirst
        ? `增配金额将超出追加持仓（超出 ${formatMoney(-stats.remaining)}）。需先减配释放资金后再试`
        : this.idleCashInsufficientMessage();
      showToast(msg);
      finishReject();
      return;
    }

    this._afterEditValidateContinue(ctx, onUpdated, row, el, committedDelta, item);
  },

  _afterEditValidateContinue(ctx, onUpdated, row, el, committedDelta, item) {
    this.clearValidationBlock(item.product_code, 'idle');
    this._setRowIdleError(row, false);
    el.dataset.committedDelta = String(Math.round(item.delta_amount));
    this.revalidateAllProductLimits(ctx.rb);
    this.syncAllProductLimitUI(ctx.rb);
    this.updateIdleCashPanel(ctx.rb, { showPlanStats: true });

    if (this.hasCategoryPrescription()) {
      this.refreshPrescriptionProgressUI(ctx.rb);
      const rx = this.validateCategoryPrescription(ctx.rb, item.category);
      if (!rx.ok) {
        showToast(rx.message);
      }
      if (Math.abs(item.delta_amount - committedDelta) >= 1) {
        this._manualDeltaEditedCategories.add(item.category);
        this.syncCategorySuggestButtons(ctx.rb);
      }
    }

    this._submit(ctx, onUpdated);
  },

  async _submit(ctx, onUpdated) {
    if (this._pending) return;
    if (this.getActiveManualDraftBlockers(ctx.rb).size) return;
    if (!this.isIdleCashSufficient(this.calcIdleCashUsageForPlan(ctx.rb))) return;
    const edited = ctx.rb.product_deltas.find(d => d.product_code === this._lastEditedCode);
    if (edited && this.isZeroDeltaNewDraft(edited)) return;
    if (edited && this.isBlockingLimitViolation(this.evaluateProductLimit(edited))) return;

    this._pending = true;
    try {
      const editedCode = this._lastEditedCode;
      const payload = this.buildAdjustPayload(ctx.rb, editedCode);
      const res = await apiPost('/api/allocation/manual_adjust', withLossKey({
        customer_id: ctx.rb.customer_id,
        product_category: typeof getProductCategory === 'function' ? getProductCategory() : undefined,
        idle_cash: this.planIdleCash(ctx.rb),
        ...payload,
      }));
      onUpdated(res.data, editedCode);
    } catch (e) {
      showToast('调整失败: ' + e.message);
    } finally {
      this._pending = false;
    }
  },

  async _submitPlanRefresh(ctx, onUpdated) {
    if (this._pending) return;
    this._pending = true;
    try {
      const baseline = this.buildFullProductTargets(ctx.rb);
      const res = await apiPost('/api/allocation/manual_adjust', withLossKey({
        customer_id: ctx.rb.customer_id,
        product_category: typeof getProductCategory === 'function' ? getProductCategory() : undefined,
        idle_cash: this.planIdleCash(ctx.rb),
        product_targets: baseline,
        baseline_product_targets: baseline,
      }));
      this._lastEditedCode = null;
      onUpdated(res.data, null);
      showToast('已移除产品，方案已更新');
    } catch (e) {
      showToast('更新失败: ' + e.message);
    } finally {
      this._pending = false;
    }
  },

  updateExplanation(ex) {
    const fields = [
      'allocationLogic', 'overUnderReason', 'customerFit',
      'managerSummary', 'clientScript',
    ];
    const map = {
      allocationLogic: ex.allocation_logic,
      overUnderReason: ex.over_under_reason,
      customerFit: ex.customer_fit,
      managerSummary: ex.manager_summary,
      clientScript: ex.client_script,
    };
    fields.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = map[id] || '--';
    });
  },

  renderValidationNotes(notes) {
    return '校验备注：' + (notes || []).join('；');
  },

  updatePlanBanner(rb) {
    const el = document.getElementById('planBanner');
    if (!el || !rb) return;
    const isManual = rb.mode === 'manual_product_edit';
    const isPrescription = this.isPrescriptionMode(rb.mode);
    let title = '配置方案已生成';
    if (isManual) title = '配置方案已更新';
    else if (isPrescription || this.isPersonalizedOrchestration()) {
      title = rb.mode === 'optimal_personalized'
        ? '个性化智能配仓（新）· 大类处方已生成'
        : '个性化智能配仓 · 大类处方已生成';
    }
    const notes = (rb.validation_notes || []).filter(Boolean);
    el.style.display = 'block';
    el.innerHTML = `
      <div class="plan-banner-main">
        <strong>${title}</strong>
        · 客户 ${rb.customer_id} · ${riskProfileLabel(rb)}
        · 总资产 ${formatMoney(rb.total_assets)}
        · 模式 ${this.modeLabel(rb.mode)}
      </div>`;
    if (notes.length) {
      const notesEl = document.createElement('div');
      notesEl.className = 'plan-banner-notes';
      notesEl.textContent = this.renderValidationNotes(notes);
      el.appendChild(notesEl);
    }
  },

  hidePlanBanner() {
    const el = document.getElementById('planBanner');
    if (!el) return;
    el.style.display = 'none';
    el.innerHTML = '';
  },

  updateValidationNotes(rb) {
    this.updatePlanBanner(rb);
  },
};
