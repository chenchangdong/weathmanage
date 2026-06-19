/**
 * 规则策略 — 对齐 wealthlive OperationRule（7 标签页）
 */
(function () {
  'use strict';

  let _globalBizTypeCache = [];
  let activeTab = 'config';
  let logSubTab = 'overview';
  let ioSubTab = 'trigger';
  let logPage = 1;
  let detailPage = 1;
  const PAGE_SIZE = 15;
  const _rowCache = {};

  const TABS = [
    { id: 'config', label: '规则配置' },
    { id: 'metrics', label: '指标管理' },
    { id: 'groups', label: '规则分组' },
    { id: 'logs', label: '事件日志' },
    { id: 'test', label: '规则测试' },
    { id: 'io', label: '出入配置' },
    { id: 'help', label: '规则说明' },
  ];

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

  function getBizTypeLabel(code) {
    const hit = _globalBizTypeCache.find((b) => b.code === code);
    return hit ? hit.name : code || '—';
  }

  async function loadBizTypes(includeDisabled) {
    const q = includeDisabled ? '?include_disabled=true' : '';
    _globalBizTypeCache = await apiFetch('/api/rule/biz-type/list' + q) || [];
    return _globalBizTypeCache;
  }

  function bizTypeOptions(selected, includeAll) {
    let html = includeAll ? '<option value="">全部业务类型</option>' : '';
    _globalBizTypeCache.forEach((b) => {
      html += `<option value="${esc(b.code)}"${b.code === selected ? ' selected' : ''}>${esc(b.name)} (${esc(b.code)})</option>`;
    });
    return html;
  }

  function statusBadge(status) {
    const on = Number(status) === 1;
    return `<span class="status ${on ? 'status-active' : 'status-inactive'}">${on ? '启用' : '禁用'}</span>`;
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
      else if (el.dataset.json) {
        try {
          data[f] = JSON.parse(el.value || '{}');
        } catch (_) {
          throw new Error(f + ' 不是合法 JSON');
        }
      } else data[f] = el.value;
    });
    return data;
  }

  // ── Tab switching ──────────────────────────────────────────

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
    const root = document.getElementById('ruleTabContent');
    if (!root) return;
    root.innerHTML = '<div class="batch-table-wrapper"><div class="empty-cell">加载中…</div></div>';
    try {
      if (activeTab !== 'help') await loadBizTypes(activeTab === 'groups');
      switch (activeTab) {
        case 'config': await renderConfigTab(root); break;
        case 'metrics': await renderMetricsTab(root); break;
        case 'groups': await renderGroupsTab(root); break;
        case 'logs': await renderLogsTab(root); break;
        case 'test': renderTestTab(root); break;
        case 'io': await renderIoTab(root); break;
        case 'help': renderHelpTab(root); break;
        default: root.innerHTML = '';
      }
    } catch (e) {
      root.innerHTML = '<div class="batch-table-wrapper"><div class="empty-cell">' + esc(e.message) + '</div></div>';
    }
  }

  // ── a) 规则配置 ────────────────────────────────────────────

  async function renderConfigTab(root) {
    const rules = await apiFetch('/api/rule/config/list') || [];
    root.innerHTML =
      '<div class="search-bar">' +
      '<h3>规则列表</h3>' +
      '<div style="display:flex;gap:10px;align-items:center">' +
      '<input type="search" id="ruleSearch" class="search-input" placeholder="搜索规则名称或编码…">' +
      '<button type="button" class="btn btn-primary" id="btnAddRule">新增规则</button>' +
      '</div></div>' +
      '<div class="batch-table-wrapper"><table class="batch-table"><thead><tr>' +
      '<th>规则编码</th><th>规则名称</th><th>业务类型</th><th>规则表达式</th><th>状态</th><th>操作</th>' +
      '</tr></thead><tbody id="rulesBody"></tbody></table></div>';

    function paint(filter) {
      const kw = (filter || '').trim().toLowerCase();
      const rows = rules.filter((r) => {
        if (!kw) return true;
        return (r.rule_code + r.rule_name + r.rule_expr).toLowerCase().includes(kw);
      });
      const body = document.getElementById('rulesBody');
      if (!rows.length) {
        body.innerHTML = '<tr><td colspan="6" class="empty-cell">暂无规则</td></tr>';
        return;
      }
      body.innerHTML = rows.map((r) => {
        const on = Number(r.status) === 1;
        return '<tr>' +
          '<td>' + esc(r.rule_code) + '</td>' +
          '<td>' + esc(r.rule_name) + '</td>' +
          '<td>' + esc(getBizTypeLabel(r.biz_type)) + '</td>' +
          '<td class="expr-cell"><code>' + esc(r.rule_expr) + '</code></td>' +
          '<td>' + statusBadge(r.status) + '</td>' +
          '<td><div class="table-actions">' +
          '<button type="button" class="btn-link" data-edit="' + r.id + '">编辑</button>' +
          '<button type="button" class="btn-link" data-toggle="' + r.id + '" data-on="' + (on ? '1' : '0') + '">' + (on ? '禁用' : '启用') + '</button>' +
          '<button type="button" class="btn-link danger" data-del="' + r.id + '">删除</button>' +
          '</div></td></tr>';
      }).join('');
    }

    paint('');
    document.getElementById('ruleSearch').addEventListener('input', (e) => paint(e.target.value));

    document.getElementById('btnAddRule').addEventListener('click', () => showRuleDrawer(null));
    document.getElementById('rulesBody').addEventListener('click', async (e) => {
      const edit = e.target.closest('[data-edit]');
      const toggle = e.target.closest('[data-toggle]');
      const del = e.target.closest('[data-del]');
      if (edit) {
        const row = rules.find((r) => r.id === Number(edit.dataset.edit));
        if (row) showRuleDrawer(row);
      } else if (toggle) {
        const id = toggle.dataset.toggle;
        const on = toggle.dataset.on === '1';
        await apiFetch('/api/rule/config/' + id + '/' + (on ? 'disable' : 'enable'), { method: 'POST' });
        toast(on ? '已禁用' : '已启用');
        renderActiveTab();
      } else if (del) {
        if (!confirm('确认删除该规则？')) return;
        await apiFetch('/api/rule/config/' + del.dataset.del, { method: 'DELETE' });
        toast('已删除');
        renderActiveTab();
      }
    });
  }

  function showRuleDrawer(row) {
    const isEdit = !!row;
    const body =
      '<div class="form-grid">' +
      field('rule_code', '规则编码', row && row.rule_code, !isEdit) +
      field('rule_name', '规则名称', row && row.rule_name) +
      '<div class="form-field"><label>业务类型</label><select name="biz_type">' + bizTypeOptions(row && row.biz_type) + '</select></div>' +
      '<div class="form-field"><label>规则表达式</label><textarea name="rule_expr" class="code-input">' + esc(row && row.rule_expr || 'max_drawdown > 5') + '</textarea></div>' +
      '<div class="form-field"><label>状态</label><select name="status"><option value="1"' + (!row || row.status === 1 ? ' selected' : '') + '>启用</option><option value="0"' + (row && row.status === 0 ? ' selected' : '') + '>禁用</option></select></div>' +
      '<div class="form-field"><label>短路执行</label><select name="short_circuit"><option value="1"' + (!row || row.short_circuit !== 0 ? ' selected' : '') + '>是</option><option value="0"' + (row && row.short_circuit === 0 ? ' selected' : '') + '>否</option></select></div>' +
      field('remark', '备注', row && row.remark, false, true) +
      '</div>';

    openDrawer(isEdit ? '编辑规则' : '新增规则', body, async (backdrop) => {
      const data = readForm(backdrop, ['rule_code', 'rule_name', 'biz_type', 'rule_expr', 'status', 'short_circuit', 'remark']);
      data.status = Number(data.status);
      data.short_circuit = Number(data.short_circuit);
      if (isEdit) {
        await apiFetch('/api/rule/config/' + row.id, { method: 'PUT', body: JSON.stringify(data) });
      } else {
        await apiFetch('/api/rule/config/add', { method: 'POST', body: JSON.stringify(data) });
      }
      toast('保存成功');
      renderActiveTab();
    });
  }

  function field(name, label, value, readonly, textarea) {
    const ro = readonly ? ' readonly' : '';
    if (textarea) {
      return '<div class="form-field"><label>' + label + '</label><textarea name="' + name + '"' + ro + '>' + esc(value || '') + '</textarea></div>';
    }
    return '<div class="form-field"><label>' + label + '</label><input name="' + name + '" value="' + esc(value || '') + '"' + ro + '></div>';
  }

  // ── b) 指标管理 ────────────────────────────────────────────

  async function renderMetricsTab(root) {
    const metrics = await apiFetch('/api/rule/metric/list') || [];
    root.innerHTML =
      '<div class="search-bar"><h3>指标列表</h3>' +
      '<button type="button" class="btn btn-primary" id="btnAddMetric">新增指标</button></div>' +
      '<div class="batch-table-wrapper"><table class="batch-table"><thead><tr>' +
      '<th>指标编码</th><th>指标名称</th><th>业务类型</th><th>取值字段</th><th>备注</th><th>操作</th>' +
      '</tr></thead><tbody id="metricsBody"></tbody></table></div>';

    const body = document.getElementById('metricsBody');
    if (!metrics.length) {
      body.innerHTML = '<tr><td colspan="6" class="empty-cell">暂无指标</td></tr>';
    } else {
      body.innerHTML = metrics.map((m) =>
        '<tr><td>' + esc(m.metric_code) + '</td><td>' + esc(m.metric_name) + '</td>' +
        '<td>' + esc(getBizTypeLabel(m.biz_type)) + '</td><td><code>' + esc(m.value_field) + '</code></td>' +
        '<td>' + esc(m.remark) + '</td>' +
        '<td><button type="button" class="btn-link danger" data-del="' + m.id + '">删除</button></td></tr>'
      ).join('');
    }

    document.getElementById('btnAddMetric').addEventListener('click', () => {
      const form =
        '<div class="form-grid">' +
        field('metric_code', '指标编码', '') +
        field('metric_name', '指标名称', '') +
        '<div class="form-field"><label>业务类型</label><select name="biz_type">' + bizTypeOptions('product_drawdown') + '</select></div>' +
        field('value_field', '取值字段', 'max_drawdown') +
        field('remark', '备注', '', false, true) +
        '</div>';
      openDrawer('新增指标', form, async (backdrop) => {
        const data = readForm(backdrop, ['metric_code', 'metric_name', 'biz_type', 'value_field', 'remark']);
        await apiFetch('/api/rule/metric/add', { method: 'POST', body: JSON.stringify(data) });
        toast('已添加');
        renderActiveTab();
      });
    });

    body.addEventListener('click', async (e) => {
      const del = e.target.closest('[data-del]');
      if (!del) return;
      if (!confirm('确认删除该指标？')) return;
      await apiFetch('/api/rule/metric/' + del.dataset.del, { method: 'DELETE' });
      toast('已删除');
      renderActiveTab();
    });
  }

  // ── c) 规则分组 ────────────────────────────────────────────

  async function renderGroupsTab(root) {
    const groups = _globalBizTypeCache.slice().sort((a, b) => (a.sort || 0) - (b.sort || 0));
    root.innerHTML =
      '<div class="search-bar"><h3>规则分组</h3>' +
      '<button type="button" class="btn btn-primary" id="btnAddGroup">新增分组</button></div>' +
      '<div class="batch-table-wrapper"><table class="batch-table"><thead><tr>' +
      '<th>排序</th><th>分组编码</th><th>分组名称</th><th>备注</th><th>状态</th><th>操作</th>' +
      '</tr></thead><tbody id="groupsBody"></tbody></table></div>';

    const body = document.getElementById('groupsBody');
    if (!groups.length) {
      body.innerHTML = '<tr><td colspan="6" class="empty-cell">暂无分组</td></tr>';
    } else {
      body.innerHTML = groups.map((g) =>
        '<tr><td>' + esc(g.sort) + '</td><td>' + esc(g.code) + '</td><td>' + esc(g.name) + '</td>' +
        '<td>' + esc(g.remark) + '</td><td>' + statusBadge(g.status) + '</td>' +
        '<td><div class="table-actions">' +
        '<button type="button" class="btn-link" data-edit="' + g.id + '">编辑</button>' +
        '<button type="button" class="btn-link danger" data-del="' + g.id + '">删除</button>' +
        '</div></td></tr>'
      ).join('');
    }

    document.getElementById('btnAddGroup').addEventListener('click', () => showGroupDrawer(null));
    body.addEventListener('click', async (e) => {
      const edit = e.target.closest('[data-edit]');
      const del = e.target.closest('[data-del]');
      if (edit) {
        const row = groups.find((g) => g.id === Number(edit.dataset.edit));
        if (row) showGroupDrawer(row);
      } else if (del) {
        if (!confirm('确认删除该分组？')) return;
        await apiFetch('/api/rule/biz-type/' + del.dataset.del, { method: 'DELETE' });
        toast('已删除');
        renderActiveTab();
      }
    });
  }

  function showGroupDrawer(row) {
    const isEdit = !!row;
    const body =
      '<div class="form-grid">' +
      field('code', '分组编码', row && row.code, isEdit) +
      field('name', '分组名称', row && row.name) +
      field('sort', '排序', row ? row.sort : 0) +
      field('remark', '备注', row && row.remark, false, true) +
      '<div class="form-field"><label>状态</label><select name="status"><option value="1"' + (!row || row.status === 1 ? ' selected' : '') + '>启用</option><option value="0"' + (row && row.status === 0 ? ' selected' : '') + '>禁用</option></select></div>' +
      '<div class="form-field"><label>短路执行</label><select name="short_circuit"><option value="1"' + (!row || row.short_circuit !== 0 ? ' selected' : '') + '>是</option><option value="0"' + (row && row.short_circuit === 0 ? ' selected' : '') + '>否</option></select></div>' +
      '</div>';

    openDrawer(isEdit ? '编辑分组' : '新增分组', body, async (backdrop) => {
      const data = readForm(backdrop, ['code', 'name', 'sort', 'remark', 'status', 'short_circuit']);
      data.sort = Number(data.sort || 0);
      data.status = Number(data.status);
      data.short_circuit = Number(data.short_circuit);
      if (isEdit) {
        await apiFetch('/api/rule/biz-type/' + row.id, { method: 'PUT', body: JSON.stringify(data) });
      } else {
        await apiFetch('/api/rule/biz-type/add', { method: 'POST', body: JSON.stringify(data) });
      }
      toast('保存成功');
      renderActiveTab();
    });
  }

  // ── d) 事件日志 ────────────────────────────────────────────

  async function renderLogsTab(root) {
    root.innerHTML =
      '<div class="sub-tab-row" id="logSubTabs">' +
      '<button type="button" class="sub-tab-btn' + (logSubTab === 'overview' ? ' active' : '') + '" data-sub="overview">事件总览</button>' +
      '<button type="button" class="sub-tab-btn' + (logSubTab === 'group' ? ' active' : '') + '" data-sub="group">分组查询</button>' +
      '<button type="button" class="sub-tab-btn' + (logSubTab === 'detail' ? ' active' : '') + '" data-sub="detail">明细查询</button>' +
      '</div><div id="logPanel"></div>';

    document.getElementById('logSubTabs').addEventListener('click', (e) => {
      const btn = e.target.closest('[data-sub]');
      if (!btn) return;
      logSubTab = btn.dataset.sub;
      logPage = 1;
      detailPage = 1;
      renderLogsTab(root);
    });

    const panel = document.getElementById('logPanel');
    if (logSubTab === 'detail') await renderDetailLogPanel(panel);
    else await renderEventLogPanel(panel, logSubTab === 'group');
  }

  async function renderEventLogPanel(panel, groupMode) {
    const bizType = groupMode ? (panel.dataset.bizType || '') : '';
    panel.innerHTML =
      '<div class="filter-bar">' +
      '<select id="logBizType">' + bizTypeOptions(bizType, true) + '</select>' +
      '<button type="button" class="btn btn-primary" id="btnLogSearch">查询</button>' +
      '<button type="button" class="btn" id="btnLogRefresh">刷新</button>' +
      '</div>' +
      '<div class="batch-table-wrapper"><table class="batch-table"><thead><tr>' +
      '<th>ID</th><th>规则编码</th><th>业务编号</th><th>业务类型</th><th>触发描述</th><th>触发时间</th><th>操作</th>' +
      '</tr></thead><tbody id="eventLogBody"><tr><td colspan="7" class="empty-cell">加载中…</td></tr></tbody></table></div>' +
      '<div class="pagination" id="eventPagination"></div>';

    async function load(page) {
      logPage = page;
      const bt = document.getElementById('logBizType').value;
      const params = new URLSearchParams({ page: String(logPage), page_size: String(PAGE_SIZE) });
      if (bt) params.set('biz_type', bt);
      const data = await apiFetch('/api/rule/event/list?' + params.toString());
      const items = data.items || [];
      const body = document.getElementById('eventLogBody');
      if (!items.length) {
        body.innerHTML = '<tr><td colspan="7" class="empty-cell">暂无事件</td></tr>';
      } else {
        body.innerHTML = items.map((r) => {
          _rowCache['evt_' + r.id] = r;
          return '<tr><td>' + esc(r.id) + '</td><td>' + esc(r.rule_code) + '</td><td>' + esc(r.biz_no) + '</td>' +
          '<td>' + esc(getBizTypeLabel(r.biz_type)) + '</td><td>' + esc(r.trigger_msg) + '</td>' +
          '<td>' + esc(r.trigger_time) + '</td>' +
          '<td><button type="button" class="btn-link" data-event-id="' + r.id + '">详情</button></td></tr>';
        }).join('');
      }
      renderPagination('eventPagination', data.page, data.total, data.page_size, load);
    }

    document.getElementById('btnLogSearch').addEventListener('click', () => load(1));
    document.getElementById('btnLogRefresh').addEventListener('click', () => load(logPage));
    document.getElementById('eventLogBody').addEventListener('click', (e) => {
      const btn = e.target.closest('[data-event-id]');
      if (!btn) return;
      const row = _rowCache['evt_' + btn.dataset.eventId];
      if (row) showEventDetail(row);
    });
    await load(logPage);
  }

  async function renderDetailLogPanel(panel) {
    panel.innerHTML =
      '<div class="filter-bar">' +
      '<select id="detailBizType">' + bizTypeOptions('', true) + '</select>' +
      '<select id="detailIsHit"><option value="">全部命中</option><option value="1">命中</option><option value="0">未命中</option></select>' +
      '<input type="text" id="detailRuleCode" placeholder="规则编码">' +
      '<button type="button" class="btn btn-primary" id="btnDetailSearch">查询</button>' +
      '</div>' +
      '<div class="batch-table-wrapper"><table class="batch-table"><thead><tr>' +
      '<th>运行ID</th><th>规则编码</th><th>规则名称</th><th>业务编号</th><th>业务类型</th><th>命中</th><th>触发信息</th><th>时间</th><th>操作</th>' +
      '</tr></thead><tbody id="detailLogBody"><tr><td colspan="9" class="empty-cell">加载中…</td></tr></tbody></table></div>' +
      '<div class="pagination" id="detailPagination"></div>';

    async function load(page) {
      detailPage = page;
      const params = new URLSearchParams({ page: String(detailPage), page_size: String(PAGE_SIZE) });
      const bt = document.getElementById('detailBizType').value;
      const hit = document.getElementById('detailIsHit').value;
      const rc = document.getElementById('detailRuleCode').value.trim();
      if (bt) params.set('biz_type', bt);
      if (hit !== '') params.set('is_hit', hit);
      if (rc) params.set('rule_code', rc);
      const data = await apiFetch('/api/rule/run-detail/list?' + params.toString());
      const items = data.items || [];
      const body = document.getElementById('detailLogBody');
      if (!items.length) {
        body.innerHTML = '<tr><td colspan="9" class="empty-cell">暂无明细</td></tr>';
      } else {
        body.innerHTML = items.map((r) => {
          _rowCache['run_' + r.id] = r;
          return '<tr><td>' + esc(r.run_id) + '</td><td>' + esc(r.rule_code) + '</td><td>' + esc(r.rule_name) + '</td>' +
          '<td>' + esc(r.biz_no) + '</td><td>' + esc(getBizTypeLabel(r.biz_type)) + '</td>' +
          '<td>' + (Number(r.is_hit) === 1 ? '<span class="status status-active">命中</span>' : '<span class="status status-inactive">未命中</span>') + '</td>' +
          '<td>' + esc(r.trigger_msg) + '</td><td>' + esc(r.trigger_time) + '</td>' +
          '<td><button type="button" class="btn-link" data-run-id="' + r.id + '">详情</button></td></tr>';
        }).join('');
      }
      renderPagination('detailPagination', data.page, data.total, data.page_size, load);
    }

    document.getElementById('btnDetailSearch').addEventListener('click', () => load(1));
    document.getElementById('detailLogBody').addEventListener('click', (e) => {
      const btn = e.target.closest('[data-run-id]');
      if (!btn) return;
      const row = _rowCache['run_' + btn.dataset.runId];
      if (row) showRunDetail(row);
    });
    await load(detailPage);
  }

  function renderPagination(id, page, total, pageSize, onPage) {
    const el = document.getElementById(id);
    if (!el) return;
    const pages = Math.max(1, Math.ceil((total || 0) / (pageSize || PAGE_SIZE)));
    el.innerHTML =
      '<span>共 ' + (total || 0) + ' 条</span>' +
      '<button type="button" class="btn" data-p="' + (page - 1) + '"' + (page <= 1 ? ' disabled' : '') + '>上一页</button>' +
      '<span>第 ' + page + ' / ' + pages + ' 页</span>' +
      '<button type="button" class="btn" data-p="' + (page + 1) + '"' + (page >= pages ? ' disabled' : '') + '>下一页</button>';
    el.querySelectorAll('[data-p]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const p = Number(btn.dataset.p);
        if (p >= 1 && p <= pages) onPage(p);
      });
    });
  }

  function showEventDetail(row) {
    openDrawer('事件详情 #' + row.id,
      '<div class="form-grid">' +
      field('rule_code', '规则编码', row.rule_code, true) +
      field('biz_no', '业务编号', row.biz_no, true) +
      field('biz_type', '业务类型', getBizTypeLabel(row.biz_type), true) +
      field('trigger_msg', '触发描述', row.trigger_msg, true, true) +
      field('trigger_time', '触发时间', row.trigger_time, true) +
      '<div class="form-field"><label>触发数据</label><textarea class="code-input" readonly>' + esc(JSON.stringify(row.trigger_data || {}, null, 2)) + '</textarea></div>' +
      '</div>',
      async () => { /* view only */ });
    const saveBtn = document.querySelector('.drawer-footer [data-save]');
    if (saveBtn) saveBtn.style.display = 'none';
  }

  function showRunDetail(row) {
    openDrawer('运行明细 #' + row.id,
      '<div class="form-grid">' +
      field('run_id', '运行ID', row.run_id, true) +
      field('rule_code', '规则编码', row.rule_code, true) +
      field('rule_name', '规则名称', row.rule_name, true) +
      field('rule_expr', '规则表达式', row.rule_expr, true, true) +
      field('biz_no', '业务编号', row.biz_no, true) +
      field('biz_type', '业务类型', getBizTypeLabel(row.biz_type), true) +
      field('trigger_msg', '触发信息', row.trigger_msg, true, true) +
      field('trigger_time', '触发时间', row.trigger_time, true) +
      '</div>',
      async () => { /* view only */ });
    const saveBtn = document.querySelector('.drawer-footer [data-save]');
    if (saveBtn) saveBtn.style.display = 'none';
  }

  // ── e) 规则测试 ────────────────────────────────────────────

  function renderTestTab(root) {
    const sample = JSON.stringify({
      prodCode: 'PROD001',
      statDate: '2025-05-24',
      max_drawdown: 6.2,
      yield_rate: 3.5,
    }, null, 2);

    root.innerHTML =
      '<div class="test-panel">' +
      '<div class="form-grid" style="max-width:720px">' +
      '<div class="form-field"><label>业务类型</label><select id="testBizType">' + bizTypeOptions('product_drawdown') + '</select></div>' +
      fieldHtml('testBizNo', '业务编号', 'PROD001_2025-05-24') +
      '<div class="form-field"><label>测试数据 (JSON)</label><textarea id="testData" class="code-input" data-json="1">' + esc(sample) + '</textarea></div>' +
      '<div class="form-field"><label>规则表达式（仅测试表达式时使用）</label><textarea id="testExpr" class="code-input">max_drawdown > 5</textarea></div>' +
      '<div style="display:flex;gap:10px">' +
      '<button type="button" class="btn btn-primary" id="btnTestRule">测试规则</button>' +
      '<button type="button" class="btn" id="btnTestExpr">测试表达式</button>' +
      '</div></div>' +
      '<div><label style="font-size:12px;color:var(--fg-3)">执行结果</label><pre id="testResult">点击上方按钮执行测试</pre></div>' +
      '</div>';

    function fieldHtml(id, label, value) {
      return '<div class="form-field"><label>' + label + '</label><input id="' + id + '" value="' + esc(value) + '"></div>';
    }

    document.getElementById('btnTestRule').addEventListener('click', async () => {
      try {
        const data = JSON.parse(document.getElementById('testData').value || '{}');
        const body = {
          bizType: document.getElementById('testBizType').value,
          bizNo: document.getElementById('testBizNo').value,
          data,
        };
        const result = await apiFetch('/api/rule/execute', { method: 'POST', body: JSON.stringify(body) });
        document.getElementById('testResult').textContent = JSON.stringify(result, null, 2);
      } catch (e) {
        document.getElementById('testResult').textContent = e.message;
      }
    });

    document.getElementById('btnTestExpr').addEventListener('click', async () => {
      try {
        const test_data = JSON.parse(document.getElementById('testData').value || '{}');
        const body = {
          expr: document.getElementById('testExpr').value,
          test_data,
        };
        const result = await apiFetch('/api/rule/test', { method: 'POST', body: JSON.stringify(body) });
        document.getElementById('testResult').textContent = JSON.stringify(result, null, 2);
      } catch (e) {
        document.getElementById('testResult').textContent = e.message;
      }
    });
  }

  // ── f) 出入配置 ────────────────────────────────────────────

  async function renderIoTab(root) {
    root.innerHTML =
      '<div class="sub-tab-row" id="ioSubTabs">' +
      '<button type="button" class="sub-tab-btn' + (ioSubTab === 'trigger' ? ' active' : '') + '" data-sub="trigger">入访配置</button>' +
      '<button type="button" class="sub-tab-btn' + (ioSubTab === 'action' ? ' active' : '') + '" data-sub="action">出访配置</button>' +
      '</div><div id="ioPanel"></div>';

    document.getElementById('ioSubTabs').addEventListener('click', (e) => {
      const btn = e.target.closest('[data-sub]');
      if (!btn) return;
      ioSubTab = btn.dataset.sub;
      renderIoTab(root);
    });

    if (ioSubTab === 'action') await renderActionPanel(document.getElementById('ioPanel'));
    else await renderTriggerPanel(document.getElementById('ioPanel'));
  }

  async function renderTriggerPanel(panel) {
    const rows = await apiFetch('/api/rules/trigger') || [];
    panel.innerHTML =
      '<div class="search-bar"><h3>入访配置（Trigger）</h3>' +
      '<button type="button" class="btn btn-primary" id="btnAddTrigger">新增入访</button></div>' +
      '<div class="batch-table-wrapper"><table class="batch-table"><thead><tr>' +
      '<th>名称</th><th>来源类型</th><th>来源标识</th><th>数据路径</th><th>描述</th><th>状态</th><th>操作</th>' +
      '</tr></thead><tbody id="triggerBody"></tbody></table></div>';

    const body = document.getElementById('triggerBody');
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="7" class="empty-cell">暂无配置</td></tr>';
    } else {
      body.innerHTML = rows.map((t) => {
        _rowCache['trg_' + t.id] = t;
        return '<tr><td>' + esc(t.trigger_name) + '</td><td>' + esc(t.source_type) + '</td><td><code>' + esc(t.source_id) + '</code></td>' +
        '<td>' + esc(t.data_path) + '</td><td>' + esc(t.description) + '</td>' +
        '<td>' + (t.is_enabled ? statusBadge(1) : statusBadge(0)) + '</td>' +
        '<td><div class="table-actions">' +
        '<button type="button" class="btn-link" data-trg-id="' + t.id + '">编辑</button>' +
        '<button type="button" class="btn-link danger" data-del="' + t.id + '">删除</button></div></td></tr>';
      }).join('');
    }

    document.getElementById('btnAddTrigger').addEventListener('click', () => showTriggerDrawer(null));
    body.addEventListener('click', async (e) => {
      const edit = e.target.closest('[data-trg-id]');
      const del = e.target.closest('[data-del]');
      if (edit) showTriggerDrawer(_rowCache['trg_' + edit.dataset.trgId]);
      else if (del) {
        if (!confirm('确认删除？')) return;
        await apiFetch('/api/rules/trigger/' + del.dataset.del, { method: 'DELETE' });
        toast('已删除');
        renderActiveTab();
      }
    });
  }

  function showTriggerDrawer(row) {
    const isEdit = !!row;
    const body =
      '<div class="form-grid">' +
      field('trigger_name', '名称', row && row.trigger_name) +
      '<div class="form-field"><label>来源类型</label><select name="source_type">' +
      ['API', 'SQL', 'CUSTOM'].map((v) => '<option value="' + v + '"' + (row && row.source_type === v ? ' selected' : '') + '>' + v + '</option>').join('') +
      '</select></div>' +
      field('source_id', '来源标识', row && row.source_id) +
      field('data_path', '数据路径', row && row.data_path) +
      field('description', '描述', row && row.description, false, true) +
      '<div class="form-field"><label>启用</label><select name="is_enabled"><option value="true"' + (!row || row.is_enabled ? ' selected' : '') + '>是</option><option value="false"' + (row && !row.is_enabled ? ' selected' : '') + '>否</option></select></div>' +
      field('sort', '排序', row ? row.sort : 0) +
      '</div>';

    openDrawer(isEdit ? '编辑入访配置' : '新增入访配置', body, async (backdrop) => {
      const data = readForm(backdrop, ['trigger_name', 'source_type', 'source_id', 'data_path', 'description', 'sort']);
      const enabled = backdrop.querySelector('[name="is_enabled"]').value === 'true';
      data.is_enabled = enabled;
      data.sort = Number(data.sort || 0);
      if (isEdit) {
        await apiFetch('/api/rules/trigger/' + row.id, { method: 'PUT', body: JSON.stringify(data) });
      } else {
        await apiFetch('/api/rules/trigger', { method: 'POST', body: JSON.stringify(data) });
      }
      toast('保存成功');
      renderActiveTab();
    });
  }

  async function renderActionPanel(panel) {
    const rows = await apiFetch('/api/rules/action') || [];
    panel.innerHTML =
      '<div class="search-bar"><h3>出访配置（Action）</h3>' +
      '<button type="button" class="btn btn-primary" id="btnAddAction">新增出访</button></div>' +
      '<div class="batch-table-wrapper"><table class="batch-table"><thead><tr>' +
      '<th>名称</th><th>动作类型</th><th>目标标识</th><th>关联入访</th><th>描述</th><th>状态</th><th>操作</th>' +
      '</tr></thead><tbody id="actionBody"></tbody></table></div>';

    const body = document.getElementById('actionBody');
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="7" class="empty-cell">暂无配置</td></tr>';
    } else {
      body.innerHTML = rows.map((a) => {
        _rowCache['act_' + a.id] = a;
        return '<tr><td>' + esc(a.action_name) + '</td><td>' + esc(a.action_type) + '</td><td><code>' + esc(a.target_id) + '</code></td>' +
        '<td>' + esc(a.trigger_id || '—') + '</td><td>' + esc(a.description) + '</td>' +
        '<td>' + (a.is_enabled ? statusBadge(1) : statusBadge(0)) + '</td>' +
        '<td><div class="table-actions">' +
        '<button type="button" class="btn-link" data-act-id="' + a.id + '">编辑</button>' +
        '<button type="button" class="btn-link danger" data-del="' + a.id + '">删除</button></div></td></tr>';
      }).join('');
    }

    document.getElementById('btnAddAction').addEventListener('click', () => showActionDrawer(null));
    body.addEventListener('click', async (e) => {
      const edit = e.target.closest('[data-act-id]');
      const del = e.target.closest('[data-del]');
      if (edit) showActionDrawer(_rowCache['act_' + edit.dataset.actId]);
      else if (del) {
        if (!confirm('确认删除？')) return;
        await apiFetch('/api/rules/action/' + del.dataset.del, { method: 'DELETE' });
        toast('已删除');
        renderActiveTab();
      }
    });
  }

  function showActionDrawer(row) {
    const isEdit = !!row;
    const body =
      '<div class="form-grid">' +
      field('action_name', '名称', row && row.action_name) +
      '<div class="form-field"><label>动作类型</label><select name="action_type">' +
      ['API', 'MSG', 'DB'].map((v) => '<option value="' + v + '"' + (row && row.action_type === v ? ' selected' : '') + '>' + v + '</option>').join('') +
      '</select></div>' +
      field('target_id', '目标标识', row && row.target_id) +
      field('trigger_id', '关联入访 ID', row && row.trigger_id) +
      field('data_mapping', '数据映射 JSON', row && row.data_mapping || '{}') +
      field('description', '描述', row && row.description, false, true) +
      '<div class="form-field"><label>启用</label><select name="is_enabled"><option value="true"' + (!row || row.is_enabled ? ' selected' : '') + '>是</option><option value="false"' + (row && !row.is_enabled ? ' selected' : '') + '>否</option></select></div>' +
      field('sort', '排序', row ? row.sort : 0) +
      '</div>';

    openDrawer(isEdit ? '编辑出访配置' : '新增出访配置', body, async (backdrop) => {
      const data = readForm(backdrop, ['action_name', 'action_type', 'target_id', 'description', 'data_mapping', 'sort']);
      const tid = backdrop.querySelector('[name="trigger_id"]').value;
      data.trigger_id = tid ? Number(tid) : null;
      data.is_enabled = backdrop.querySelector('[name="is_enabled"]').value === 'true';
      data.sort = Number(data.sort || 0);
      if (isEdit) {
        await apiFetch('/api/rules/action/' + row.id, { method: 'PUT', body: JSON.stringify(data) });
      } else {
        await apiFetch('/api/rules/action', { method: 'POST', body: JSON.stringify(data) });
      }
      toast('保存成功');
      renderActiveTab();
    });
  }

  // ── g) 规则说明 ────────────────────────────────────────────

  function renderHelpTab(root) {
    root.innerHTML =
      '<div class="help-panel">' +
      '<h3>核心模块</h3>' +
      '<ul>' +
      '<li><b>规则配置</b>：维护规则编码、表达式与业务分组，支持启用/禁用与短路执行。</li>' +
      '<li><b>指标管理</b>：定义业务指标与数据字段映射，供规则表达式引用。</li>' +
      '<li><b>规则分组</b>：按 biz_type 对规则进行分组管理，控制执行顺序与短路策略。</li>' +
      '<li><b>事件日志</b>：记录规则命中事件与逐条运行明细，支持分页与详情查看。</li>' +
      '<li><b>规则测试</b>：在线调试完整规则链或单条表达式。</li>' +
      '<li><b>出入配置</b>：配置入访触发源与出访动作（API / 消息 / 数据库）。</li>' +
      '</ul>' +

      '<h3>数据要求</h3>' +
      '<p>执行规则时，<code>data</code> 中应包含指标定义的 <code>value_field</code> 字段。示例：</p>' +
      '<pre>{\n  "prodCode": "PROD001",\n  "max_drawdown": 6.2,\n  "yield_rate": 3.5\n}</pre>' +
      '<p>表达式支持比较运算（<code>max_drawdown &gt; 5</code>）与等值匹配（<code>product_id=aaaa</code>）。</p>' +

      '<h3>API 文档</h3>' +
      '<table><thead><tr><th>方法</th><th>路径</th><th>说明</th></tr></thead><tbody>' +
      apiRow('GET', '/api/rule/config/list', '规则列表') +
      apiRow('POST', '/api/rule/config/add', '新增规则') +
      apiRow('PUT', '/api/rule/config/{id}', '更新规则') +
      apiRow('DELETE', '/api/rule/config/{id}', '删除规则') +
      apiRow('POST', '/api/rule/config/{id}/enable|disable', '启用/禁用') +
      apiRow('GET', '/api/rule/metric/list', '指标列表') +
      apiRow('POST', '/api/rule/metric/add', '新增指标') +
      apiRow('GET', '/api/rule/biz-type/list', '规则分组') +
      apiRow('GET', '/api/rule/event/list', '事件总览') +
      apiRow('GET', '/api/rule/run-detail/list', '运行明细') +
      apiRow('POST', '/api/rule/execute', '执行规则链') +
      apiRow('POST', '/api/rule/test', '测试表达式') +
      apiRow('GET/POST', '/api/rules/trigger', '入访配置') +
      apiRow('GET/POST', '/api/rules/action', '出访配置') +
      '</tbody></table>' +

      '<h3>应用场景</h3>' +
      '<h4>产品最大回撤（product_drawdown）</h4>' +
      '<p>当 <code>max_drawdown</code> 超过阈值时触发预警，可配置多级阈值（5% / 10%）。</p>' +
      '<h4>产品收益预警（product_yield）</h4>' +
      '<p>当 <code>yield_rate</code> 低于阈值时触发陪伴提醒。</p>' +
      '<h4>持仓变动预警（position_change）</h4>' +
      '<p>监测仓位或产品标识变动，支持等值匹配类规则。</p>' +

      '<h3>RuleAction（出访动作）</h3>' +
      '<p>规则命中后可联动出访动作：</p>' +
      '<ul>' +
      '<li><b>API</b>：调用外部接口，如 <code>/api/warn/trade</code></li>' +
      '<li><b>MSG</b>：发送消息队列通知，如 <code>topic.rule.hit</code></li>' +
      '<li><b>DB</b>：写入日志表，如 <code>wrtb_warning_log</code></li>' +
      '</ul>' +
      '<p>通过 <code>data_mapping</code> 将命中快照字段映射到动作参数。</p>' +

      '<h3>注意事项</h3>' +
      '<ul>' +
      '<li>同一分组内规则按 ID 顺序执行；<code>short_circuit=1</code> 时首条命中后停止。</li>' +
      '<li>禁用状态（<code>status=0</code>）的规则不参与执行。</li>' +
      '<li>规则测试会写入事件日志与运行明细，请在生产环境谨慎使用。</li>' +
      '<li>入访配置的 <code>data_path</code> 用于从触发源响应中提取指标数据。</li>' +
      '</ul></div>';
  }

  function apiRow(method, path, desc) {
    return '<tr><td><code>' + esc(method) + '</code></td><td><code>' + esc(path) + '</code></td><td>' + esc(desc) + '</td></tr>';
  }

  // ── Init ───────────────────────────────────────────────────

  function initRuleStrategyPage() {
    bindMainTabs();
    renderActiveTab();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initRuleStrategyPage);
  } else {
    initRuleStrategyPage();
  }

  window.getBizTypeLabel = getBizTypeLabel;
  window.initRuleStrategyPage = initRuleStrategyPage;
})();
