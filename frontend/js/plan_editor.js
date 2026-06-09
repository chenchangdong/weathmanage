/** 配置方案人工二次调整 — 产品目标联动大类占比与区间校验 */

const PlanEditor = {
  _pending: false,
  _lastEditedCode: null,
  _manualAddedCodes: new Set(),
  /** 新增产品草稿校验失败时锁定 code -> 'idle' | 'max_over' | 'min' */
  _manualValidationBlocked: new Map(),
  _pickerCategory: null,
  _pickerSelectedCode: null,
  _pickerTab: 'manual',
  _pickerRb: null,
  _pickerAiProducts: [],
  _categoryCandidatesCache: {},
  _productLimits: {},
  _productLimitValidationEnabled: false,

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

  modeLabel(mode) {
    const labels = {
      smart_one_click: '智能一键',
      manual_tweak: '人工微调',
      manual_product_edit: '人工二次调整',
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
    this._manualValidationBlocked = new Map();
    this._categoryCandidatesCache = {};
    this._productLimits = {};
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
    return '';
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

  blockingEditGate(rb, editingCode) {
    const blockers = this.getBlockingInvalidManualProducts(rb);
    if (!blockers.length) return { ok: true };
    if (blockers.includes(editingCode)) return { ok: true };

    const parts = blockers.map((code) => {
      const d = rb.product_deltas.find((x) => x.product_code === code);
      if (!d) return null;
      const reason = this.getValidationBlockReason(code);
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
      d.limit_hit = !!side;
      d.limit_side = side || '';
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
      if (reason !== 'idle') return;
      const row = grid.querySelector(`.product-edit-row[data-product-code="${code}"]`);
      if (row) this._setRowIdleError(row, true);
    });
  },

  validateCanAddProduct(rb, picked) {
    if (this.getBlockingInvalidManualProducts(rb).length) {
      return {
        ok: false,
        message: this.blockingEditGate(rb, '').message,
      };
    }
    const stats = this.calcIdleCashUsageFromDeltas(rb);
    const remaining = stats.remaining;
    const min = picked.min_amount || 0;
    if (remaining <= 0.01) {
      return {
        ok: false,
        message: this.idleCashInsufficientMessage(),
      };
    }
    if (this.isProductLimitValidationEnabled() && remaining < min - 0.01) {
      return {
        ok: false,
        message: `剩余可配置闲置资金 ${formatMoney(remaining)} 低于「${picked.name}」起购金额 ${formatMoney(min)}，请先释放足够金额后再添加`,
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
   * 可配置闲置资金口径：
   * - 本次已配置 = 调仓金额（delta / adjust_amount）之和
   * - 剩余可配置 = 可配置闲置资金 − 本次已配置
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

  isIdleCashSufficient(stats) {
    return stats.remaining >= -0.01;
  },

  idleCashInsufficientMessage() {
    return '本次可配置闲置资金不足，请调整其他产品释放！';
  },

  _idleReleaseNoteHtml(stats) {
    const released = stats && stats.releasedFromHoldings > 0.01 ? stats.releasedFromHoldings : 0;
    if (!released) return '';
    return `<span class="idle-cash-release-note">（含存量持仓释放资金 ${formatMoney(released)}）</span>`;
  },

  updateIdleCashPanel(rb, options = {}) {
    const { showPlanStats = false, fromSummary = false } = options;
    const idleEl = document.getElementById('idleCash');
    const cfgEl = document.getElementById('configuredIdle');
    const remEl = document.getElementById('remainingIdle');
    if (!idleEl) return;

    const idle = rb.idle_cash || 0;
    idleEl.textContent = (showPlanStats ? '可配置闲置资金 ' : '闲置资金 ') + formatMoney(idle);

    if (!showPlanStats) {
      if (cfgEl) cfgEl.style.display = 'none';
      if (remEl) remEl.style.display = 'none';
      return;
    }

    const stats = rb.product_deltas && rb.product_deltas.length
      ? this.calcIdleCashUsageFromDeltas(rb)
      : this.calcIdleCashUsage(idle, rb.category_summary);

    if (cfgEl) {
      cfgEl.style.display = 'block';
      cfgEl.innerHTML = '本次已配置闲置资金 ' + formatMoney(stats.configured)
        + this._idleReleaseNoteHtml(stats);
    }
    if (remEl) {
      remEl.style.display = 'block';
      remEl.innerHTML = '剩余可配置闲置资金 ' + formatMoney(stats.remaining)
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
      const values = card.querySelectorAll(':scope > .field .value');
      if (values.length >= 5) {
        values[0].textContent = formatPct(s.current_ratio);
        values[1].textContent = formatPct(s.target_ratio);
        values[2].textContent = `${s.adjust_amount >= 0 ? '+' : ''}${formatMoney(s.adjust_amount)}`;
        values[2].className = `value ${s.adjust_amount >= 0 ? 'action-buy' : 'action-sell'}`;
        values[3].textContent = formatPct(s.final_ratio);
        values[4].textContent = formatBandRange(s.band);
      }
      const bandField = card.querySelector(':scope > .field.band-cell');
      if (bandField) bandField.title = formatBandTooltip(s.band);
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
    const isManual = rb.mode === 'manual_product_edit';

    const banner = document.getElementById('planBanner');
    if (banner) {
      banner.style.display = 'block';
      banner.innerHTML = `
        <strong>${isManual ? '配置方案已更新' : '配置方案已生成'}</strong>
        · 客户 ${rb.customer_id} · ${riskProfileLabel(rb)}
        · 总资产 ${formatMoney(rb.total_assets)}
        · 模式 ${this.modeLabel(rb.mode)}`;
    }

    this.updatePlanCardSummaries(rb);
    this.updateIdleCashPanel(rb, { showPlanStats: true, fromSummary: false });

    const detailBody = document.getElementById('detailBody');
    if (detailBody) detailBody.innerHTML = this.renderReadonlyDetailRows(rb);

    const validationNotes = document.getElementById('validationNotes');
    if (validationNotes) {
      this.updateValidationNotes(rb);
    }

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
        <div class="product-row-error" style="display:none">本次可配置闲置资金不足，请调整其他产品释放！</div>
      </div>
    `;
  },

  renderEditableCategoryProductRows(rb, category) {
    const rows = this.categoryEditableDeltas(rb, category);
    const rowHtml = rows.length
      ? rows.map(d => this.renderProductEditBlock(d)).join('')
      : '';
    return `${rowHtml}
      <div class="product-picker-bar">
        <button type="button" class="btn btn-link btn-picker" data-action="pick-product" data-category="${category}">+ 选择产品</button>
      </div>`;
  },

  refreshCategoryPlanRows(rb, category) {
    const el = document.getElementById(`products-plan-${category}`);
    if (el) {
      el.innerHTML = this.renderEditableCategoryProductRows(rb, category);
    }
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
    const stats = this.calcIdleCashUsageFromDeltas(rb);
    if (hintEl) {
      hintEl.textContent = `当前剩余可配置闲置资金：${formatMoney(stats.remaining)}（添加新产品须剩余金额 > 0 且不低于产品起购金额）`;
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

  removeManualProduct(rb, code, getContext, onUpdated) {
    const item = rb.product_deltas.find(d => d.product_code === code);
    if (!item || !this.canDeleteManualProduct(item)) return false;

    const hadAllocation = Math.abs(item.delta_amount) >= 1 || item.target_amount > 0.01;
    const category = item.category;
    const name = item.product_name;

    rb.product_deltas = rb.product_deltas.filter(d => d.product_code !== code);
    this._manualAddedCodes.delete(code);
    this.clearValidationBlock(code);
    this.refreshCategoryPlanRows(rb, category);
    this.refreshDetailTable(rb);
    this.updateIdleCashPanel(rb, { showPlanStats: true, fromSummary: false });

    if (hadAllocation && onUpdated) {
      const ctx = getContext();
      if (ctx) {
        this._submitPlanRefresh(ctx, onUpdated);
        return true;
      }
    }
    showToast(`已移除 ${name}`);
    return true;
  },

  confirmProductPicker(rb, categoryNameMap) {
    const category = this._pickerCategory;
    const code = this._pickerSelectedCode;
    if (!category || !code || !rb) return false;

    if (rb.product_deltas.some(d => d.product_code === code)) {
      this.closeProductPicker();
      return false;
    }

    const picked = this._getPickerProduct(code);
    if (!picked) return false;

    const gate = this.validateCanAddProduct(rb, picked);
    if (!gate.ok) {
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
    this.closeProductPicker();
    showToast(`已添加 ${picked.name}，请填写不低于起购金额 ${formatMoney(picked.min_amount || 0)} 的增减仓`);
    return true;
  },

  bindPlanGrid(container, getContext, onUpdated) {
    if (!container) return;
    container.addEventListener('click', (e) => {
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
        this.openProductPicker(category, ctx.rb, catSummary ? catSummary.category_name : category);
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
      confirmBtn.onclick = () => {
        const ctx = getContext();
        if (ctx) this.confirmProductPicker(ctx.rb);
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
      this.updateIdleCashPanel(rb, { showPlanStats: true, fromSummary: false });
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
    this._syncProductLimitState(row, item);

    this._afterEditValidate(ctx, onUpdated, row, el, committed, item);
  },

  _afterEditValidate(ctx, onUpdated, row, el, committedDelta, item) {
    const stats = this.calcIdleCashUsageFromDeltas(ctx.rb);
    if (!this.isIdleCashSufficient(stats)) {
      showToast(this.idleCashInsufficientMessage());
      if (this.isNewManualDraftProduct(item)) {
        this.setValidationBlock(item.product_code, 'idle');
        this._setRowIdleError(row, true);
        this.updateIdleCashPanel(ctx.rb, { showPlanStats: true, fromSummary: false });
        this.revalidateAllProductLimits(ctx.rb);
        this.syncAllProductLimitUI(ctx.rb);
        return;
      }
      this._revertDeltaCommit(el, row, item, committedDelta, ctx.rb);
      this.revalidateAllProductLimits(ctx.rb);
      this.syncAllProductLimitUI(ctx.rb);
      return;
    }

    this.clearValidationBlock(item.product_code, 'idle');
    this._setRowIdleError(row, false);
    el.dataset.committedDelta = String(Math.round(item.delta_amount));
    this.revalidateAllProductLimits(ctx.rb);
    this.syncAllProductLimitUI(ctx.rb);
    this._submit(ctx, onUpdated);
  },

  async _submit(ctx, onUpdated) {
    if (this._pending) return;
    if (this.getBlockingInvalidManualProducts(ctx.rb).length) return;
    if (!this.isIdleCashSufficient(this.calcIdleCashUsageFromDeltas(ctx.rb))) return;
    const edited = ctx.rb.product_deltas.find(d => d.product_code === this._lastEditedCode);
    if (edited && this.isBlockingLimitViolation(this.evaluateProductLimit(edited))) return;

    this._pending = true;
    try {
      const editedCode = this._lastEditedCode;
      const payload = this.buildAdjustPayload(ctx.rb, editedCode);
      const res = await apiPost('/api/allocation/manual_adjust', {
        customer_id: ctx.rb.customer_id,
        product_category: typeof getProductCategory === 'function' ? getProductCategory() : undefined,
        ...payload,
      });
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
      const res = await apiPost('/api/allocation/manual_adjust', {
        customer_id: ctx.rb.customer_id,
        product_category: typeof getProductCategory === 'function' ? getProductCategory() : undefined,
        product_targets: baseline,
        baseline_product_targets: baseline,
      });
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

  updateValidationNotes(rb) {
    const el = document.getElementById('validationNotes');
    if (!el) return;
    const text = this.renderValidationNotes(rb.validation_notes);
    el.textContent = text;
    if (el.classList.contains('validation-notes-main')) {
      el.style.display = text ? 'block' : 'none';
    }
  },
};
