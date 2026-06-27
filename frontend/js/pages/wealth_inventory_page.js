/** 财富盘点 — 页面逻辑（支持软导航换页） */
window.WealthInventoryPage = {
  async boot() {
    await this.loadInventory();
  },

  async loadInventory() {
    const loading = document.getElementById('loading');
    const content = document.getElementById('content');
    if (!loading || !content) return;
    loading.style.display = 'block';
    content.style.display = 'none';
    try {
      const res = await apiGet('/api/wealth/inventory');
      this.renderTable(res.data.customers || []);
      loading.style.display = 'none';
      content.style.display = 'block';
    } catch (e) {
      loading.textContent = '加载失败: ' + e.message;
    }
  },

  renderTable(customers) {
    const needCare = customers.filter(c => c.flag_count > 0).length;
    const summary = document.getElementById('inventorySummary');
    if (summary) {
      summary.textContent = `共 ${customers.length} 位客户 · ${needCare} 位建议介入`;
    }

    const tbody = document.getElementById('inventoryBody');
    if (!tbody) return;
    tbody.innerHTML = customers.map(c => {
      const p = c.performance;
      const annCls = WealthJourney.pctClass(p.annual_return_pct);
      const monCls = WealthJourney.pctClass(p.month_return_pct);
      const lossExceeded = p.principal_loss_pct < -c.loss_threshold_pct;
      const lossCls = lossExceeded ? 'metric-down' : (p.principal_loss_pct < -0.05 ? 'metric-flat' : '');
      return `
          <tr class="inventory-row" data-customer-id="${c.customer_id}" tabindex="0">
            <td><strong>${c.name}</strong></td>
            <td>${c.risk_profile_name}</td>
            <td>${formatMoney(c.total_assets)}</td>
            <td class="${annCls}">${WealthJourney.formatSignedPct(p.annual_return_pct)}</td>
            <td class="${monCls}">${WealthJourney.formatSignedPct(p.month_return_pct)}<span class="cell-sub">${formatMoney(p.month_return_amount)}</span></td>
            <td>${p.volatility_pct.toFixed(1)}%</td>
            <td class="${lossCls}">${p.principal_loss_pct.toFixed(2)}%</td>
            <td class="inventory-flags">${WealthJourney.renderFlags(c.flags)}</td>
          </tr>`;
    }).join('');

    tbody.querySelectorAll('.inventory-row').forEach(row => {
      const go = () => navigateWithCustomer('asset_diagnosis.html', row.dataset.customerId);
      row.addEventListener('click', go);
      row.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); }
      });
    });
    WealthJourney.bindFlagTooltips(tbody);
  },
};
