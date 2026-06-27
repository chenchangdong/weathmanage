/** 资产诊断 — 页面逻辑（支持软导航换页） */
window.AssetDiagnosisPage = {
  async boot() {
    this.bindActions();
    await this.loadDiagnosis();
  },

  bindActions() {
    const cid = () => getCustomerId();
    const linkSmartAllocStep = document.getElementById('linkSmartAllocStep');
    if (linkSmartAllocStep) {
      linkSmartAllocStep.onclick = (e) => {
        e.preventDefault();
        if (!cid()) {
          showToast('请先选择客户');
          return;
        }
        sessionStorage.setItem(PRODUCT_CATEGORY_KEY, '投资规划');
        navigateWithCustomer('smart_allocation_setup.html', cid());
      };
    }
    const btnSmart = document.getElementById('btnSmartAllocation');
    if (btnSmart) {
      btnSmart.onclick = () => {
        if (!cid()) {
          showToast('请先选择客户');
          return;
        }
        sessionStorage.setItem(PRODUCT_CATEGORY_KEY, '投资规划');
        navigateWithCustomer('smart_allocation_setup.html', cid());
      };
    }
  },

  async loadDiagnosis() {
    const customerId = getCustomerId();
    const loading = document.getElementById('loading');
    const empty = document.getElementById('emptyState');
    const content = document.getElementById('content');
    if (!customerId) {
      if (loading) loading.style.display = 'none';
      if (empty) empty.style.display = 'block';
      if (content) content.style.display = 'none';
      return;
    }
    if (empty) empty.style.display = 'none';
    try {
      const res = await apiGet(`/api/wealth/diagnosis?customer_id=${encodeURIComponent(customerId)}`);
      this.renderDiagnosis(res.data);
      if (loading) loading.style.display = 'none';
      if (content) content.style.display = 'block';
    } catch (e) {
      if (loading) loading.textContent = '加载失败: ' + e.message;
    }
  },

  renderDiagnosis(d) {
    window.diagnosisData = d;
    const sub = document.getElementById('diagnosisSubtitle');
    if (sub) sub.textContent = `${d.name} · ${d.risk_profile_name} · 投资规划`;
    const nameEl = document.getElementById('customerName');
    if (nameEl) nameEl.textContent = d.name;
    const meta = document.getElementById('customerMeta');
    if (meta) meta.textContent = `${d.risk_profile_name} · 客户编号 ${d.customer_id}`;
    const total = document.getElementById('metricTotal');
    if (total) total.textContent = `${WealthJourney.formatWan(d.total_assets)} 万`;
    const date = document.getElementById('metricDate');
    if (date) date.textContent = `数据日期 ${d.diagnosis_date}`;

    const flagsEl = document.getElementById('metricFlags');
    if (flagsEl) {
      if (d.flags && d.flags.length) {
        flagsEl.innerHTML = WealthJourney.renderFlags(d.flags, { interactive: true });
        WealthJourney.bindFlagTooltips(flagsEl);
      } else {
        flagsEl.innerHTML = '<span class="diagnosis-flags-empty">暂无标志</span>';
      }
    }

    const p = d.performance;
    const m = d.model_benchmark;
    const annEl = document.getElementById('metricAnnual');
    if (annEl) {
      annEl.textContent = `${WealthJourney.formatSignedPct(p.annual_return_pct)} · ${formatMoney(p.annual_return_amount || 0)}`;
      annEl.className = WealthJourney.pctClass(p.annual_return_pct);
    }
    const monEl = document.getElementById('metricMonth');
    if (monEl) {
      monEl.textContent = `${WealthJourney.formatSignedPct(p.month_return_pct)} · ${formatMoney(p.month_return_amount || 0)}`;
      monEl.className = WealthJourney.pctClass(p.month_return_pct);
    }
    const expectRet = document.getElementById('metricExpectRet');
    if (expectRet) expectRet.textContent = `${m.expect_annual_return_pct}%`;
    const lossEl = document.getElementById('metricLoss');
    if (lossEl) {
      lossEl.textContent = `${p.principal_loss_pct.toFixed(2)}%`;
      lossEl.className = p.principal_loss_pct < -d.loss_threshold_pct ? 'metric-down' : '';
    }
    const vol = document.getElementById('metricVol');
    if (vol) vol.textContent = `${p.volatility_pct}%`;
    const expectRisk = document.getElementById('metricExpectRisk');
    if (expectRisk) {
      expectRisk.textContent = `波动 ${m.expect_volatility_pct}% · 损失阈值 ${d.loss_threshold_pct}%`;
    }
    const scoreBadge = document.getElementById('compositeScore');
    if (scoreBadge) {
      scoreBadge.textContent = `${d.composite_score} 分`;
      const level = (d.score_context && d.score_context.health_level) || 'healthy';
      scoreBadge.className = `diagnosis-score-badge diagnosis-score-badge--${level}`;
    }
    const beat = document.getElementById('beatInvestors');
    if (beat) {
      beat.textContent = `综合评分 ${d.composite_score} 分，跑赢约 ${d.beat_investors_pct}% 的同风险投资者`;
    }
    const conclusion = document.getElementById('diagnosisConclusion');
    if (conclusion) conclusion.textContent = d.conclusions[0] || '暂无异常，建议定期复盘。';
    const radar = document.getElementById('radarWrap');
    if (radar) radar.innerHTML = WealthJourney.renderRadar(d.dimensions);
    const compare = document.getElementById('fourMoneyCompare');
    if (compare) compare.innerHTML = WealthJourney.renderCompareBars(d.four_money);
    const list = document.getElementById('conclusionList');
    if (list) list.innerHTML = d.conclusions.map(t => `<li>${t}</li>`).join('');
  },
};
