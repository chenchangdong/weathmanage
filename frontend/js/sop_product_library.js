/**
 * SOP 产品信息库
 */
(function () {
  'use strict';

  let activeTab = 'products';
  let libraryConfig = { category_options: [], managers: [] };
  let productPage = 1;
  let managerPage = 1;
  const PAGE_SIZE = 15;

  const MANAGER_TYPES = ['证券公司', '公募基金', '私募基金', '私募', '信托', '其他'];

  async function apiFetch(url, opts) {
    const res = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...(opts && opts.headers) },
      ...opts,
    });
    if (!res.ok) {
      let msg = res.statusText;
      try {
        const err = await res.json();
        msg = err.detail || err.message || msg;
      } catch (_) { /* ignore */ }
      throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    }
    if (res.status === 204) return null;
    const text = await res.text();
    return text ? JSON.parse(text) : null;
  }

  function unwrap(resp) {
    if (resp && Object.prototype.hasOwnProperty.call(resp, 'data')) return resp.data;
    return resp;
  }

  function esc(s) {
    return String(s ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function toast(msg) {
    const el = document.getElementById('toast');
    if (!el) return;
    el.textContent = msg;
    el.classList.add('show');
    setTimeout(() => el.classList.remove('show'), 2500);
  }

  function statusBadge(status) {
    const on = Number(status) === 1;
    return `<span class="status ${on ? 'status-active' : 'status-inactive'}">${on ? '启用' : '禁用'}</span>`;
  }

  function categoryLabel(code) {
    const hit = (libraryConfig.category_options || []).find((c) => c.code === code);
    return hit ? hit.label : (code || '—');
  }

  function assetTypeLabel(code) {
    if (!code) return '—';
    const hit = (libraryConfig.asset_type_options || []).find((c) => c.code === code);
    return hit ? hit.label : code;
  }

  function assetTypeOptions(selected) {
    let html = '<option value="">未设置</option>';
    (libraryConfig.asset_type_options || []).forEach((c) => {
      html += `<option value="${esc(c.code)}"${c.code === selected ? ' selected' : ''}>${esc(c.label)}</option>`;
    });
    return html;
  }

  function managerOptions(selected, includeEmpty) {
    let html = includeEmpty ? '<option value="">请选择管理人</option>' : '';
    (libraryConfig.managers || []).forEach((m) => {
      html += `<option value="${esc(m.id)}"${m.id === selected ? ' selected' : ''}>${esc(m.name)} (${esc(m.id)})</option>`;
    });
    return html;
  }

  function riskLevelOptions(selected) {
    let html = '<option value="">未设置</option>';
    for (let i = 1; i <= 5; i += 1) {
      html += `<option value="${i}"${Number(selected) === i ? ' selected' : ''}>${i} 级</option>`;
    }
    return html;
  }

  function isAllocationRow(r) {
    return r.rebalance_priority !== undefined && r.rebalance_priority !== null && r.rebalance_priority !== '';
  }

  function categoryOptions(selected) {
    let html = '<option value="">请选择类型</option>';
    (libraryConfig.category_options || []).forEach((c) => {
      html += `<option value="${esc(c.code)}"${c.code === selected ? ' selected' : ''}>${esc(c.label)}</option>`;
    });
    return html;
  }

  function openDrawer(title, bodyHtml, onSave) {
    const backdrop = document.createElement('div');
    backdrop.className = 'drawer-backdrop';
    backdrop.innerHTML =
      '<div class="drawer" role="dialog">' +
      '<div class="drawer-header"><h3 style="margin:0;font-size:16px">' + esc(title) + '</h3>' +
      '<button type="button" class="btn-link" data-close>✕</button></div>' +
      '<div class="drawer-body">' + bodyHtml + '</div>' +
      '<div class="drawer-footer">' +
      '<button type="button" class="btn" data-close>取消</button>' +
      '<button type="button" class="btn btn-primary" data-save>保存</button>' +
      '</div></div>';
    document.body.appendChild(backdrop);

    function close() {
      backdrop.remove();
    }
    backdrop.querySelectorAll('[data-close]').forEach((btn) => btn.addEventListener('click', close));
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) close();
    });
    backdrop.querySelector('[data-save]').addEventListener('click', async () => {
      try {
        await onSave(backdrop);
        close();
      } catch (e) {
        toast(e.message || '保存失败');
      }
    });
    return backdrop;
  }

  function readForm(backdrop, fields) {
    const data = {};
    fields.forEach((f) => {
      const el = backdrop.querySelector('[name="' + f + '"]');
      if (!el) return;
      if (el.type === 'checkbox') data[f] = el.checked ? 1 : 0;
      else if (el.type === 'number') data[f] = el.value === '' ? null : Number(el.value);
      else data[f] = el.value;
    });
    return data;
  }

  function paginationHtml(page, totalPages, total, prefix) {
    if (totalPages <= 1) return `<div class="pagination">共 ${total} 条</div>`;
    return (
      '<div class="pagination">' +
      `<span>共 ${total} 条</span>` +
      `<button type="button" class="btn btn-sm" data-page="${prefix}-prev" ${page <= 1 ? 'disabled' : ''}>上一页</button>` +
      `<span>${page} / ${totalPages}</span>` +
      `<button type="button" class="btn btn-sm" data-page="${prefix}-next" ${page >= totalPages ? 'disabled' : ''}>下一页</button>` +
      '</div>'
    );
  }

  async function loadConfig() {
    const resp = await apiFetch('/api/sop/product-library/config');
    libraryConfig = unwrap(resp) || {};
  }

  function bindMainTabs() {
    document.querySelectorAll('#mainTabs .tab-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        activeTab = btn.dataset.tab;
        document.querySelectorAll('#mainTabs .tab-btn').forEach((b) => b.classList.toggle('active', b === btn));
        renderActiveTab();
      });
    });
  }

  async function renderActiveTab() {
    const root = document.getElementById('tabContent');
    if (!root) return;
    root.innerHTML = '<div class="card batch-table-wrapper"><div class="empty-cell">加载中…</div></div>';
    try {
      await loadConfig();
      if (activeTab === 'products') await renderProductsTab(root);
      else await renderManagersTab(root);
    } catch (e) {
      root.innerHTML = '<div class="card"><div class="empty-cell">加载失败：' + esc(e.message) + '</div></div>';
    }
  }

  // ── 产品信息 ────────────────────────────────────────────────

  async function renderProductsTab(root) {
    const resp = await apiFetch(`/api/sop/info-products/?page=${productPage}&page_size=${PAGE_SIZE}`);
    const payload = unwrap(resp) || {};
    const rows = payload.data || [];
    const total = payload.total || 0;
    const totalPages = payload.total_pages || 1;

    let tableRows = rows.map((r) => (
      '<tr>' +
      `<td>${esc(r.product_id)}</td>` +
      `<td>${esc(r.product_name)}</td>` +
      `<td>${esc(r.product_code)}</td>` +
      `<td>${esc(r.manager_name || r.manager_id)}</td>` +
      `<td>${esc(categoryLabel(r.category))}</td>` +
      `<td>${esc(r.risk_level != null && r.risk_level !== '' ? r.risk_level + '级' : '—')}</td>` +
      `<td>${esc(assetTypeLabel(r.asset_type))}</td>` +
      `<td>${esc(r.rating || '—')}</td>` +
      `<td>${statusBadge(r.status)}</td>` +
      '<td class="table-actions">' +
      `<button type="button" class="btn-link" data-edit-product="${esc(r.product_id)}">编辑</button>` +
      `<button type="button" class="btn-link danger" data-del-product="${esc(r.product_id)}">删除</button>` +
      '</td></tr>'
    )).join('');

    if (!tableRows) tableRows = '<tr><td colspan="10" class="empty-cell">暂无产品</td></tr>';

    root.innerHTML =
      '<div class="card">' +
      '<div class="filter-bar">' +
      '<button type="button" class="btn btn-primary" id="btnAddProduct">新增产品</button>' +
      '</div>' +
      '<div class="dict-table-scroll">' +
      '<table class="batch-table"><thead><tr>' +
      '<th>产品代码</th><th>产品名称</th><th>产品编码</th><th>管理人</th><th>风险属性</th><th>风险等级</th><th>资产类型</th><th>评级</th><th>状态</th><th>操作</th>' +
      '</tr></thead><tbody>' + tableRows + '</tbody></table></div>' +
      paginationHtml(productPage, totalPages, total, 'product') +
      '</div>';

    root.querySelector('#btnAddProduct').addEventListener('click', () => openProductDrawer(null));
    root.querySelectorAll('[data-edit-product]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const id = btn.dataset.editProduct;
        const resp2 = await apiFetch('/api/sop/info-products/' + encodeURIComponent(id));
        openProductDrawer(unwrap(resp2));
      });
    });
    root.querySelectorAll('[data-del-product]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const id = btn.dataset.delProduct;
        if (!confirm('确定删除产品 ' + id + '？')) return;
        try {
          await apiFetch('/api/sop/info-products/' + encodeURIComponent(id), { method: 'DELETE' });
          toast('已删除');
          renderActiveTab();
        } catch (e) {
          toast(e.message);
        }
      });
    });
    const prev = root.querySelector('[data-page="product-prev"]');
    const next = root.querySelector('[data-page="product-next"]');
    if (prev) prev.addEventListener('click', () => { productPage -= 1; renderActiveTab(); });
    if (next) next.addEventListener('click', () => { productPage += 1; renderActiveTab(); });
  }

  function openProductDrawer(row) {
    const isNew = !row;
    const r = row || {};
    const alloc = isAllocationRow(r);
    const showAllocFields = alloc || isNew || !!(r.asset_type || '').trim();
    const body =
      '<div class="form-grid">' +
      field('产品代码', 'product_id', r.product_id, isNew ? '' : 'readonly') +
      field('产品名称', 'product_name', r.product_name) +
      field('产品编码', 'product_code', r.product_code || r.product_id) +
      '<div class="form-field"><label>风险属性</label><select name="category">' + categoryOptions(r.category) + '</select></div>' +
      '<div class="form-field"><label>风险等级</label><select name="risk_level">' + riskLevelOptions(r.risk_level) + '</select></div>' +
      '<div class="form-field"><label>资产类型</label><select name="asset_type">' + assetTypeOptions(r.asset_type) + '</select></div>' +
      '<div class="form-field"><label>管理人</label><select name="manager_id" id="productManagerSelect">' +
      managerOptions(r.manager_id, true) + '</select></div>' +
      field('策略类型', 'strategy_type', r.strategy_type) +
      field('评级', 'rating', r.rating) +
      field('成立日期', 'setup_date', r.setup_date, 'type="date"') +
      field('初始净值', 'init_nav', r.init_nav != null ? r.init_nav : 1, 'type="number" step="0.0001"') +
      field('评分', 'score', r.score != null ? r.score : '', 'type="number" step="0.01" min="0" max="1"') +
      textarea('结论', 'conclusion', r.conclusion) +
      textarea('风险说明', 'risk', r.risk) +
      (showAllocFields ? (
        '<p style="margin:4px 0 0;font-size:12px;color:var(--fg-3)">资配约束（调仓优先级请在 YAML 中维护）</p>' +
        field('产品子类型', 'product_subtype', r.product_subtype) +
        field('最低金额', 'min_amount', r.min_amount != null ? r.min_amount : '', 'type="number" min="0"') +
        field('最高金额', 'max_amount', r.max_amount != null ? r.max_amount : '', 'type="number" min="0"') +
        field('流动性天数', 'liquidity_days', r.liquidity_days != null ? r.liquidity_days : '', 'type="number"')
      ) : '') +
      '<div class="form-field"><label>状态</label><select name="status">' +
      `<option value="1"${Number(r.status) !== 0 ? ' selected' : ''}>启用</option>` +
      `<option value="0"${Number(r.status) === 0 ? ' selected' : ''}>禁用</option></select></div>` +
      '</div>';

    openDrawer(isNew ? '新增产品' : '编辑产品', body, async (backdrop) => {
      const data = readForm(backdrop, [
        'product_id', 'product_name', 'product_code', 'manager_id', 'category', 'risk_level', 'asset_type',
        'strategy_type', 'rating', 'setup_date', 'init_nav', 'score', 'conclusion', 'risk', 'status',
        'product_subtype', 'min_amount', 'max_amount', 'liquidity_days',
      ]);
      if (!data.product_id) throw new Error('产品代码不能为空');
      const mgr = (libraryConfig.managers || []).find((m) => m.id === data.manager_id);
      data.manager_name = mgr ? mgr.name : '';
      const url = isNew
        ? '/api/sop/info-products/'
        : '/api/sop/info-products/' + encodeURIComponent(data.product_id);
      await apiFetch(url, {
        method: isNew ? 'POST' : 'PUT',
        body: JSON.stringify(data),
      });
      toast(isNew ? '产品创建成功' : '产品更新成功');
      await renderActiveTab();
    });
  }

  function field(label, name, value, extra) {
    const attrs = extra || '';
    const ro = attrs.includes('readonly') ? ' readonly' : '';
    return (
      '<div class="form-field"><label>' + esc(label) + '</label>' +
      `<input name="${name}" value="${esc(value ?? '')}"${ro} ${attrs.replace('readonly', '')}></div>`
    );
  }

  function textarea(label, name, value) {
    return (
      '<div class="form-field"><label>' + esc(label) + '</label>' +
      `<textarea name="${name}">${esc(value ?? '')}</textarea></div>`
    );
  }

  // ── 管理人维护 ──────────────────────────────────────────────

  async function renderManagersTab(root) {
    const resp = await apiFetch(`/api/sop/managers/list?page=${managerPage}&page_size=${PAGE_SIZE}`);
    const payload = unwrap(resp) || {};
    const rows = payload.data || [];
    const total = payload.total || 0;
    const totalPages = payload.total_pages || 1;

    let tableRows = rows.map((r) => (
      '<tr>' +
      `<td>${esc(r.id)}</td>` +
      `<td>${esc(r.name)}</td>` +
      `<td>${esc(r.full_name || '—')}</td>` +
      `<td>${esc(r.type || '—')}</td>` +
      `<td>${esc(r.product_count != null ? r.product_count : 0)}</td>` +
      `<td>${statusBadge(r.status)}</td>` +
      '<td class="table-actions">' +
      `<button type="button" class="btn-link" data-edit-manager="${esc(r.id)}">编辑</button>` +
      `<button type="button" class="btn-link danger" data-del-manager="${esc(r.id)}">删除</button>` +
      '</td></tr>'
    )).join('');

    if (!tableRows) tableRows = '<tr><td colspan="7" class="empty-cell">暂无管理人</td></tr>';

    root.innerHTML =
      '<div class="card">' +
      '<div class="filter-bar">' +
      '<button type="button" class="btn btn-primary" id="btnAddManager">新增管理人</button>' +
      '</div>' +
      '<div class="dict-table-scroll">' +
      '<table class="batch-table"><thead><tr>' +
      '<th>管理人ID</th><th>简称</th><th>全称</th><th>类型</th><th>关联产品数</th><th>状态</th><th>操作</th>' +
      '</tr></thead><tbody>' + tableRows + '</tbody></table></div>' +
      paginationHtml(managerPage, totalPages, total, 'manager') +
      '</div>';

    root.querySelector('#btnAddManager').addEventListener('click', () => openManagerDrawer(null));
    root.querySelectorAll('[data-edit-manager]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const id = btn.dataset.editManager;
        const resp2 = await apiFetch('/api/sop/managers/' + encodeURIComponent(id));
        openManagerDrawer(unwrap(resp2));
      });
    });
    root.querySelectorAll('[data-del-manager]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const id = btn.dataset.delManager;
        if (!confirm('确定删除管理人 ' + id + '？')) return;
        try {
          await apiFetch('/api/sop/managers/' + encodeURIComponent(id), { method: 'DELETE' });
          toast('已删除');
          renderActiveTab();
        } catch (e) {
          toast(e.message);
        }
      });
    });
    const prev = root.querySelector('[data-page="manager-prev"]');
    const next = root.querySelector('[data-page="manager-next"]');
    if (prev) prev.addEventListener('click', () => { managerPage -= 1; renderActiveTab(); });
    if (next) next.addEventListener('click', () => { managerPage += 1; renderActiveTab(); });
  }

  function openManagerDrawer(row) {
    const isNew = !row;
    const r = row || {};
    const typeOpts = MANAGER_TYPES.map((t) =>
      `<option value="${esc(t)}"${t === r.type ? ' selected' : ''}>${esc(t)}</option>`
    ).join('');

    const body =
      '<div class="form-grid">' +
      field('管理人ID', 'id', r.id, isNew ? '' : 'readonly') +
      field('简称', 'name', r.name) +
      field('全称', 'full_name', r.full_name) +
      '<div class="form-field"><label>类型</label><select name="type">' +
      '<option value="">请选择</option>' + typeOpts + '</select></div>' +
      textarea('备注', 'remark', r.remark) +
      '<div class="form-field"><label>状态</label><select name="status">' +
      `<option value="1"${Number(r.status) !== 0 ? ' selected' : ''}>启用</option>` +
      `<option value="0"${Number(r.status) === 0 ? ' selected' : ''}>禁用</option></select></div>` +
      '</div>';

    openDrawer(isNew ? '新增管理人' : '编辑管理人', body, async (backdrop) => {
      const data = readForm(backdrop, ['id', 'name', 'full_name', 'type', 'remark', 'status']);
      if (!data.id) throw new Error('管理人ID不能为空');
      const url = isNew
        ? '/api/sop/managers/'
        : '/api/sop/managers/' + encodeURIComponent(data.id);
      await apiFetch(url, {
        method: isNew ? 'POST' : 'PUT',
        body: JSON.stringify(data),
      });
      toast(isNew ? '管理人创建成功' : '管理人更新成功');
      await renderActiveTab();
    });
  }

  function init() {
    bindMainTabs();
    renderActiveTab();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
