/** 财富盘点 / 资产诊断 — 共享渲染 */

const WealthJourney = {
  formatWan(n) {
    const v = Number(n) / 10000;
    return v >= 100 ? v.toFixed(1) : v.toFixed(2);
  },

  formatSignedPct(n, digits = 2) {
    const v = Number(n);
    const sign = v > 0 ? '+' : '';
    return `${sign}${v.toFixed(digits)}%`;
  },

  pctClass(n) {
    const v = Number(n);
    if (v > 0.05) return 'metric-up';
    if (v < -0.05) return 'metric-down';
    return 'metric-flat';
  },

  flagBadgeClass(severity) {
    if (severity === 'danger') return 'flag-danger';
    if (severity === 'warn') return 'flag-warn';
    return 'flag-info';
  },

  renderFlags(flags, { interactive = true } = {}) {
    if (!flags || !flags.length) {
      return '<span class="flag-badge flag-ok">配置健康</span>';
    }
    return flags.map(f => {
      const cls = this.flagBadgeClass(f.severity);
      const tip = this._escapeAttr(f.hint || f.label);
      const attrs = interactive
        ? ` tabindex="0" data-flag-hint="${tip}"`
        : '';
      return `<span class="flag-badge ${cls}"${attrs}>${f.label}</span>`;
    }).join('');
  },

  bindFlagTooltips(root) {
    const tip = document.getElementById('flagTooltip');
    if (!tip || !root) return;
    const show = (text, el) => {
      tip.textContent = text;
      tip.style.display = 'block';
      const r = el.getBoundingClientRect();
      tip.style.left = `${Math.min(window.innerWidth - 320, Math.max(8, r.left))}px`;
      tip.style.top = `${r.bottom + 8 + window.scrollY}px`;
    };
    const hide = () => { tip.style.display = 'none'; };
    root.querySelectorAll('[data-flag-hint]').forEach(el => {
      el.addEventListener('mouseenter', () => show(el.dataset.flagHint, el));
      el.addEventListener('focus', () => show(el.dataset.flagHint, el));
      el.addEventListener('mouseleave', hide);
      el.addEventListener('blur', hide);
    });
  },

  renderCompareBars(items) {
    return items.map(item => {
      const curPct = (item.current_ratio * 100).toFixed(1);
      const tgtPct = (item.target_ratio * 100).toFixed(1);
      const status = item.in_band ? 'in-band' : 'out-band';
      const statusLabel = item.in_band ? '区间内' : (item.current_ratio > item.band[1] ? '超配' : '低配');
      return `
        <div class="fm-compare-row ${status}">
          <div class="fm-compare-head">
            <span class="fm-compare-name">${item.category_name}</span>
            <span class="fm-compare-status">${statusLabel}</span>
          </div>
          <div class="fm-compare-bars">
            <div class="fm-bar-group">
              <span class="fm-bar-label">当前 ${curPct}%</span>
              <div class="fm-bar-track"><div class="fm-bar-fill fm-bar-current" style="width:${Math.min(100, curPct)}%"></div></div>
            </div>
            <div class="fm-bar-group">
              <span class="fm-bar-label">目标 ${tgtPct}%</span>
              <div class="fm-bar-track"><div class="fm-bar-fill fm-bar-target" style="width:${Math.min(100, tgtPct)}%"></div></div>
            </div>
          </div>
          <div class="fm-compare-meta">模型区间 ${(item.band[0] * 100).toFixed(0)}% ~ ${(item.band[1] * 100).toFixed(0)}% · 持仓 ${formatMoney(item.current_amount)}</div>
        </div>`;
    }).join('');
  },

  _overviewBarScaleMax(curRatio, tgtRatio, band) {
    const hi = Array.isArray(band) ? Number(band[1] || 0) : 0;
    // 柱高按总资产占比绝对刻度：100% = 满柱，与柱顶百分比一致
    return Math.max(1, Number(curRatio) || 0, Number(tgtRatio) || 0, hi);
  },

  _overviewBarPctLabel(ratio) {
    return `${(Number(ratio || 0) * 100).toFixed(1)}%`;
  },

  _overviewBarStatus(curRatio, band) {
    if (!Array.isArray(band) || band.length < 2) return null;
    const cur = Number(curRatio) || 0;
    const lo = Number(band[0]) || 0;
    const hi = Number(band[1]) || 0;
    if (cur > hi) return { code: 'over', label: '超配', cls: 'fm-overview-bar-badge--over' };
    if (cur < lo) return { code: 'under', label: '低配', cls: 'fm-overview-bar-badge--under' };
    return null;
  },

  _renderTrendArrow(diffPct, compact) {
    const isFlat = Math.abs(diffPct) < 0.05;
    const isUp = diffPct > 0;
    const dir = isFlat ? 'flat' : (isUp ? 'up' : 'down');
    const tone = isFlat ? 'deviation-flat' : (isUp ? 'deviation-buy' : 'deviation-sell');
    const title = isFlat ? '基本持平' : (isUp ? '建议增配' : '建议减配');
    const compactCls = compact ? ' fm-trend-arrow--compact' : '';
    return `<div class="fm-trend-arrow fm-trend-arrow--${dir} ${tone}${compactCls}" title="${title}" aria-hidden="true">
      <span class="fm-trend-arrow-shaft"></span>
    </div>`;
  },

  renderCategoryOverviewBars(data, options = {}) {
    const targetCaption = options.targetCaption || '智能建议';
    const compact = !!options.compact;
    const curRatio = Number(data.current_ratio) || 0;
    const tgtRatio = Number(options.targetRatio != null ? options.targetRatio : data.target_ratio) || 0;
    const scaleMax = this._overviewBarScaleMax(curRatio, tgtRatio, data.band);
    const shellH = compact ? 75 : 96;
    const toBarH = (ratio) => {
      const h = Math.round(((Number(ratio) || 0) / scaleMax) * shellH);
      return Math.min(shellH, Math.max(ratio > 0 ? 2 : 0, h));
    };
    const curH = toBarH(curRatio);
    const tgtH = toBarH(tgtRatio);
    const diffPct = (tgtRatio - curRatio) * 100;
    const diffLabel = this.formatSignedPct(diffPct, 1);
    const trendArrow = this._renderTrendArrow(diffPct, compact);
    const deviationCls = Math.abs(diffPct) < 0.05
      ? 'deviation-flat'
      : (diffPct >= 0 ? 'deviation-buy' : 'deviation-sell');
    const status = this._overviewBarStatus(curRatio, data.band);
    const bandTip = typeof formatBandTooltip === 'function' ? formatBandTooltip(data.band) : '';

    const badgeHtml = status
      ? `<span class="fm-overview-bar-badge ${status.cls}">${status.label}</span>`
      : '';

    return `
      <div class="fm-overview-bars${data.in_band ? '' : ' fm-overview-bars--warn'}" title="${this._escapeAttr(bandTip)}">
        <div class="fm-overview-bars-chart">
          <div class="fm-overview-bar-col">
            <span class="fm-overview-bar-pct">${this._overviewBarPctLabel(curRatio)}</span>
            <div class="fm-overview-bar-shell fm-overview-bar-shell--current" style="height:${shellH}px">
              ${badgeHtml}
              <div class="fm-overview-bar-fill fm-overview-bar-fill--current" style="height:${curH}px"></div>
            </div>
            <span class="fm-overview-bar-caption">当前实际</span>
          </div>
          <div class="fm-overview-bar-bridge">
            <span class="fm-overview-bar-pct fm-overview-bar-pct--ghost" aria-hidden="true">&#8203;</span>
            <div class="fm-overview-bar-bridge-track" style="height:${shellH}px">
              ${trendArrow}
            </div>
            <div class="fm-overview-bar-deviation">
              <span class="fm-overview-bar-deviation-label">偏离</span>
              <strong class="fm-overview-bar-deviation-value ${deviationCls}">${diffLabel}</strong>
            </div>
          </div>
          <div class="fm-overview-bar-col">
            <span class="fm-overview-bar-pct">${this._overviewBarPctLabel(tgtRatio)}</span>
            <div class="fm-overview-bar-shell fm-overview-bar-shell--target" style="height:${shellH}px">
              <div class="fm-overview-bar-fill fm-overview-bar-fill--target" style="height:${tgtH}px"></div>
            </div>
            <span class="fm-overview-bar-caption">${targetCaption}</span>
          </div>
        </div>
        <div class="fm-overview-bars-meta">
          <span class="fm-overview-meta-item">当前持仓 <strong>${formatMoney(data.current_amount)}</strong></span>
          <span class="fm-overview-meta-item">目标配置额 <strong>${formatMoney(data.target_amount)}</strong></span>
          <span class="fm-overview-meta-item">模型区间 <strong>${typeof formatBandRange === 'function' ? formatBandRange(data.band) : '--'}</strong></span>
        </div>
      </div>`;
  },

  renderRadar(dimensions) {
    const defs = [
      { key: 'assets', label: '资产', cls: 'radar-label-top' },
      { key: 'holdings', label: '持仓', cls: 'radar-label-tr' },
      { key: 'returns', label: '收益', cls: 'radar-label-br' },
      { key: 'risk', label: '风险', cls: 'radar-label-bl' },
      { key: 'behavior', label: '行为', cls: 'radar-label-tl' },
    ];
    const keys = defs.map((d) => d.key);
    const cx = 50;
    const cy = 50;
    const dataR = 36;
    const outerR = 40;

    const pointAt = (i, r) => {
      const angle = (Math.PI * 2 * i) / keys.length - Math.PI / 2;
      return {
        x: cx + Math.cos(angle) * r,
        y: cy + Math.sin(angle) * r,
      };
    };

    const points = keys.map((k, i) => {
      const { x, y } = pointAt(i, (dimensions[k] / 700) * dataR);
      return `${x},${y}`;
    }).join(' ');

    const outerPoints = keys.map((_, i) => {
      const { x, y } = pointAt(i, outerR);
      return `${x},${y}`;
    }).join(' ');

    const innerPoints = keys.map((_, i) => {
      const { x, y } = pointAt(i, outerR * 0.72);
      return `${x},${y}`;
    }).join(' ');

    const axisLines = keys.map((_, i) => {
      const { x, y } = pointAt(i, outerR);
      return `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" class="radar-axis"/>`;
    }).join('');

    const labelsHtml = defs.map((d) => `
      <div class="radar-html-label ${d.cls}">
        <span class="radar-html-name">${d.label}</span>
        <span class="radar-html-score">${dimensions[d.key]}</span>
      </div>`).join('');

    const svg = `
      <svg viewBox="0 0 100 100" class="radar-chart-svg" aria-hidden="true">
        <polygon points="${outerPoints}" class="radar-bg"/>
        <polygon points="${innerPoints}" class="radar-bg inner"/>
        ${axisLines}
        <polygon points="${points}" class="radar-area"/>
      </svg>`;

    return `<div class="radar-chart-outer">${labelsHtml}<div class="radar-chart-inner">${svg}</div></div>`;
  },

  _escapeAttr(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;');
  },

  /** 财富旅程页：侧栏停靠顾问（与智能资配/投后陪伴一致） */
  initAdvisor(options = {}) {
    AdvisorChat.initDockPage({
      bindHealthDiagnose: false,
      bindPlanExplain: false,
      ...options,
    });
  },
};
