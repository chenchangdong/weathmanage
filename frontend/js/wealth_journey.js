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

  renderRadar(dimensions) {
    const labels = {
      assets: '资产',
      holdings: '持仓',
      returns: '收益',
      risk: '风险',
      behavior: '行为',
    };
    const keys = Object.keys(labels);
    const points = keys.map((k, i) => {
      const angle = (Math.PI * 2 * i) / keys.length - Math.PI / 2;
      const r = (dimensions[k] / 700) * 42;
      const x = 50 + Math.cos(angle) * r;
      const y = 50 + Math.sin(angle) * r;
      return `${x},${y}`;
    }).join(' ');
    const axisLines = keys.map((k, i) => {
      const angle = (Math.PI * 2 * i) / keys.length - Math.PI / 2;
      const x = 50 + Math.cos(angle) * 46;
      const y = 50 + Math.sin(angle) * 46;
      return `<line x1="50" y1="50" x2="${x}" y2="${y}" class="radar-axis"/>`;
    }).join('');
    const labelsHtml = keys.map((k, i) => {
      const angle = (Math.PI * 2 * i) / keys.length - Math.PI / 2;
      const x = 50 + Math.cos(angle) * 54;
      const y = 50 + Math.sin(angle) * 54;
      return `<text x="${x}" y="${y}" class="radar-label" text-anchor="middle" dominant-baseline="middle">${labels[k]} ${dimensions[k]}</text>`;
    }).join('');
    return `
      <svg viewBox="0 0 100 100" class="radar-chart" aria-hidden="true">
        <polygon points="50,4 96,38 78,92 22,92 4,38" class="radar-bg"/>
        <polygon points="50,18 82,42 70,78 30,78 18,42" class="radar-bg inner"/>
        ${axisLines}
        <polygon points="${points}" class="radar-area"/>
        ${labelsHtml}
      </svg>`;
  },

  _escapeAttr(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;');
  },
};
