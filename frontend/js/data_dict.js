/**
 * 数据字典 — 左侧分类树 + 右侧表格/表单
 */
(function () {
  'use strict';

  const FALLBACK_LABELS = {
    benchmark: '模型基准 (benchmark)',
    band_midpoint: '区间中点 (band_midpoint)',
    band_low: '区间下限 (band_low)',
    band_high: '区间上限 (band_high)',
  };

  let _tree = [];
  let _expanded = new Set();
  let _selected = null;
  let _module = null;
  let _rows = [];
  let _values = {};

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
    const json = await res.json();
    return json.data !== undefined ? json.data : json;
  }

  function openDrawer(title, bodyHtml, onSave) {
    const backdrop = document.createElement('div');
    backdrop.className = 'drawer-backdrop';
    backdrop.innerHTML =
      '<div class="drawer dict-drawer" role="dialog">' +
      '<div class="drawer-header"><h3 style="margin:0;font-size:16px;font-weight:600">' + esc(title) + '</h3>' +
      '<button type="button" class="btn-link" data-close aria-label="关闭">✕</button></div>' +
      '<div class="drawer-body">' + bodyHtml + '</div>' +
      '<div class="drawer-footer">' +
      '<button type="button" class="btn" data-close>取消</button>' +
      '<button type="button" class="btn btn-primary" data-save>确定</button>' +
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
        toast(e.message || '操作失败');
      }
    });
    return backdrop;
  }

  function renderTree() {
    const el = document.getElementById('dictTree');
    if (!el) return;
    if (!_tree.length) {
      el.innerHTML = '<div class="dict-empty" style="padding:24px;font-size:13px">暂无分类</div>';
      return;
    }

    let html = '';
    _tree.forEach((group) => {
      const expanded = _expanded.has(group.id);
      html += '<div class="dict-tree-group">';
      html += '<div class="dict-tree-group-head" data-toggle="' + esc(group.id) + '">';
      html += '<span class="dict-tree-toggle">' + (expanded ? '▾' : '▸') + '</span>';
      html += '<span>' + esc(group.name) + '</span>';
      html += '</div>';
      if (expanded) {
        (group.children || []).forEach((leaf) => {
          const active = _selected && _selected.id === leaf.id ? ' active' : '';
          html += '<div class="dict-tree-item' + active + '" data-module="' + esc(leaf.id) + '">';
          html += '<span>' + esc(leaf.name) + '</span>';
          html += '</div>';
        });
      }
      html += '</div>';
    });
    el.innerHTML = html;

    el.querySelectorAll('[data-toggle]').forEach((node) => {
      node.addEventListener('click', () => {
        const id = node.getAttribute('data-toggle');
        if (_expanded.has(id)) _expanded.delete(id);
        else _expanded.add(id);
        renderTree();
      });
    });

    el.querySelectorAll('[data-module]').forEach((node) => {
      node.addEventListener('click', () => selectModule(node.getAttribute('data-module')));
    });
  }

  async function selectModule(moduleId) {
    let leaf = null;
    let group = null;
    _tree.forEach((g) => {
      (g.children || []).forEach((c) => {
        if (c.id === moduleId) {
          leaf = c;
          group = g;
        }
      });
    });
    if (!leaf) return;
    _selected = { ...leaf, groupName: group ? group.name : '' };
    _expanded.add(group.id);
    renderTree();
    await loadModule(moduleId);
  }

  async function loadModule(moduleId) {
    renderHeader(true);
    document.getElementById('dictBody').innerHTML = '<div class="dict-loading">加载中…</div>';
    try {
      _module = await apiFetch('/api/config-dict/module/' + encodeURIComponent(moduleId));
      if (_module.view_type === 'table') {
        _rows = (_module.rows || []).map((r) => ({ ...r }));
        _values = {};
      } else {
        _values = { ...(_module.values || {}) };
        _rows = [];
      }
      renderHeader(false);
      renderBody();
    } catch (e) {
      document.getElementById('dictBody').innerHTML =
        '<div class="dict-empty"><p>' + esc(e.message) + '</p></div>';
      renderHeader(false);
    }
  }

  function renderHeaderActions() {
    const box = document.getElementById('dictHeaderActions');
    if (!box) return;
    if (!_selected || !_module) {
      box.innerHTML = '';
      return;
    }
    if (_module.view_type === 'table') {
      box.innerHTML =
        '<button type="button" class="btn btn-primary" id="btnAddRow">+ 新增</button>' +
        '<button type="button" class="btn" id="btnSaveModule">保存配置</button>';
    } else {
      box.innerHTML = '<button type="button" class="btn btn-primary" id="btnSaveModule">保存配置</button>';
    }
    document.getElementById('btnSaveModule')?.addEventListener('click', () => {
      if (_module.view_type === 'form') collectFormValues();
      saveModule();
    });
    document.getElementById('btnAddRow')?.addEventListener('click', () => {
      const empty = {};
      (_module.columns || []).forEach((c) => {
        empty[c.key] = c.type === 'number' ? 0 : '';
      });
      openRowDrawer('新增字典项', empty, true);
    });
  }

  function renderHeader(loading) {
    const titleEl = document.getElementById('moduleTitle');
    const fileEl = document.getElementById('moduleFile');
    const descEl = document.getElementById('moduleDesc');
    if (!_selected || loading) {
      if (!_selected) {
        titleEl.textContent = '请选择配置项';
        fileEl.hidden = true;
        descEl.textContent = '在左侧选择适合可视化维护的配置模块';
      }
      document.getElementById('dictHeaderActions').innerHTML = '';
      return;
    }
    titleEl.textContent = _selected.name;
    if (_module) {
      fileEl.textContent = _module.file;
      fileEl.hidden = false;
      descEl.textContent = _module.desc || '';
    }
    renderHeaderActions();
  }

  function renderBody() {
    const body = document.getElementById('dictBody');
    if (!_module) return;
    body.innerHTML = _module.view_type === 'table' ? renderTablePanel() : renderFormPanel();
    if (_module.view_type === 'table') bindTableEvents();
  }

  function renderTablePanel() {
    const cols = _module.columns || [];
    let html = '<div class="dict-panel-card">';
    html += '<div class="dict-panel-toolbar">';
    const scrollHint = cols.length >= 4 ? ' · 可左右滚动查看全部列' : '';
    html += '<span class="toolbar-meta">共 ' + _rows.length + ' 条' + scrollHint + ' · 修改后请点击右上角「保存配置」</span>';
    html += '</div>';
    html += '<div class="dict-table-scroll' + (cols.length >= 5 ? ' dict-table-scroll--wide' : '') + '">';
    html += '<div class="batch-table-wrapper"><table class="batch-table"><thead><tr>';
    cols.forEach((c) => {
      html += '<th>' + esc(c.label) + '</th>';
    });
    html += '<th class="col-actions">操作</th></tr></thead><tbody>';
    if (!_rows.length) {
      html += '<tr><td colspan="' + (cols.length + 1) + '" class="empty-state" style="text-align:center;padding:32px;color:var(--fg-4)">暂无数据，点击「新增」添加</td></tr>';
    } else {
      _rows.forEach((row, idx) => {
        html += '<tr data-idx="' + idx + '">';
        cols.forEach((c) => {
          const val = row[c.key];
          const isCode = c.key === 'code' || c.key.endsWith('_key') || c.key === 'profile_name' || c.key === 'key';
          const wrapCls = c.type === 'textarea' || c.key === 'card_keys' || c.key === 'asset_types' || c.key === 'description' ? ' cell-wrap' : '';
          html += '<td class="' + wrapCls.trim() + '">' + (isCode ? '<code>' + esc(val) + '</code>' : esc(val)) + '</td>';
        });
        html += '<td class="col-actions"><div class="dict-row-actions">';
        html += '<button type="button" class="btn-link btn-edit" data-idx="' + idx + '">编辑</button>';
        html += '<button type="button" class="btn-link btn-del" data-idx="' + idx + '" style="color:#ff4d4f">删除</button>';
        html += '</div></td></tr>';
      });
    }
    html += '</tbody></table></div></div></div>';
    return html;
  }

  function fieldInput(col, value, readonly) {
    const ro = readonly || col.readonly ? ' readonly' : '';
    const v = esc(value ?? '');
    if (col.type === 'textarea') {
      return '<textarea name="' + esc(col.key) + '"' + ro + ' rows="3">' + v + '</textarea>';
    }
    if (col.type === 'select' && col.options) {
      let s = '<select name="' + esc(col.key) + '"' + (readonly ? ' disabled' : '') + '>';
      col.options.forEach((opt) => {
        s += '<option value="' + esc(opt) + '"' + (String(value) === String(opt) ? ' selected' : '') + '>' + esc(opt) + '</option>';
      });
      s += '</select>';
      return s;
    }
    if (col.type === 'number') {
      return '<input type="number" name="' + esc(col.key) + '" value="' + v + '"' + ro + '>';
    }
    if (col.type === 'boolean') {
      const checked = value ? ' checked' : '';
      return '<label class="dict-switch"><input type="checkbox" name="' + esc(col.key) + '"' + checked + (readonly ? ' disabled' : '') + '><span class="dict-switch-track"></span><span class="dict-switch-label">' + (value ? '开启' : '关闭') + '</span></label>';
    }
    return '<input type="text" name="' + esc(col.key) + '" value="' + v + '"' + ro + '>';
  }

  function openRowDrawer(title, row, isNew) {
    const cols = _module.columns || [];
    const idKey = _module.id_key || 'code';
    let fields = '';
    cols.forEach((col) => {
      const readonly = !isNew && col.readonly_on_edit;
      fields += '<div class="form-field"><label>' + esc(col.label) + (col.required ? ' *' : '') + '</label>';
      fields += fieldInput(col, row[col.key], readonly);
      fields += '</div>';
    });

    openDrawer(title, '<div class="form-grid">' + fields + '</div>', (backdrop) => {
      const data = { ...row };
      cols.forEach((col) => {
        const el = backdrop.querySelector('[name="' + col.key + '"]');
        if (!el) return;
        if (col.type === 'boolean') data[col.key] = el.checked;
        else if (col.type === 'number') data[col.key] = el.value === '' ? '' : Number(el.value);
        else data[col.key] = el.value.trim ? el.value.trim() : el.value;
      });
      if (!data[idKey]) throw new Error('请填写必填编码');
      if (isNew && _rows.some((r) => String(r[idKey]) === String(data[idKey]))) {
        throw new Error('编码已存在');
      }
      if (isNew) _rows.push(data);
      else {
        const idx = _rows.findIndex((r) => String(r[idKey]) === String(row[idKey]));
        if (idx >= 0) _rows[idx] = data;
      }
      renderBody();
      renderHeader(false);
      toast('已更新，记得保存配置');
    });
  }

  function bindTableEvents() {
    document.querySelectorAll('.btn-edit').forEach((btn) => {
      btn.addEventListener('click', () => {
        const idx = Number(btn.getAttribute('data-idx'));
        openRowDrawer('编辑字典项', { ..._rows[idx] }, false);
      });
    });
    document.querySelectorAll('.btn-del').forEach((btn) => {
      btn.addEventListener('click', () => {
        const idx = Number(btn.getAttribute('data-idx'));
        const idKey = _module.id_key || 'code';
        const label = _rows[idx][idKey] || '该项';
        if (!confirm('确定删除「' + label + '」吗？')) return;
        _rows.splice(idx, 1);
        renderBody();
        renderHeader(false);
        toast('已删除，记得保存配置');
      });
    });
  }

  function formatDefault(field) {
    if (field.default === undefined || field.default === null) return '';
    if (typeof field.default === 'boolean') return field.default ? 'true' : 'false';
    return String(field.default);
  }

  function formFieldInput(field, value) {
    const ro = field.readonly ? ' readonly' : '';
    const v = esc(value ?? '');
    if (field.type === 'boolean') {
      const checked = value ? ' checked' : '';
      return (
        '<label class="dict-switch">' +
        '<input type="checkbox" data-path-input="' + esc(field.key) + '"' + checked + ro + '>' +
        '<span class="dict-switch-track"></span>' +
        '<span class="dict-switch-label">' + (value ? '已开启' : '已关闭') + '</span></label>'
      );
    }
    if (field.type === 'textarea') {
      return '<textarea data-path-input="' + esc(field.key) + '"' + ro + ' rows="3">' + v + '</textarea>';
    }
    if (field.type === 'select' && field.options) {
      let s = '<select data-path-input="' + esc(field.key) + '"' + ro + '>';
      field.options.forEach((opt) => {
        const label = FALLBACK_LABELS[opt] || opt;
        s += '<option value="' + esc(opt) + '"' + (String(value) === String(opt) ? ' selected' : '') + '>' + esc(label) + '</option>';
      });
      s += '</select>';
      return s;
    }
    if (field.type === 'number') {
      const def = formatDefault(field);
      const ph = def ? ' placeholder="默认: ' + esc(def) + '"' : '';
      return '<input type="number" step="any" data-path-input="' + esc(field.key) + '" value="' + v + '"' + ph + ro + '>';
    }
    const def = formatDefault(field);
    const ph = def ? ' placeholder="默认: ' + esc(def) + '"' : '';
    return '<input type="text" data-path-input="' + esc(field.key) + '" value="' + v + '"' + ph + ro + '>';
  }

  function renderFormPanel() {
    let html = '<div class="dict-panel-card">';
    (_module.sections || []).forEach((section) => {
      html += '<div class="dict-form-section">';
      html += '<div class="dict-form-section-title">' + esc(section.title) + '</div>';
      html += '<div class="dict-form-grid">';
      const prefix = section.prefix ? section.prefix + '.' : '';
      (section.fields || []).forEach((field) => {
        const path = prefix + field.key;
        const val = _values[path];
        html += '<div class="dict-form-field" data-path="' + esc(path) + '">';
        html += '<label>' + esc(field.label) + '</label>';
        html += formFieldInput(field, val);
        if (field.hint) {
          html += '<div class="field-hint">' + esc(field.hint) + '</div>';
        }
        if (field.default !== undefined && field.type !== 'boolean') {
          html += '<div class="field-default">推荐默认：' + esc(formatDefault(field)) + '</div>';
        }
        html += '</div>';
      });
      html += '</div></div>';
    });
    html += '</div>';
    return html;
  }

  function collectFormValues() {
    document.querySelectorAll('.dict-form-field').forEach((wrap) => {
      const path = wrap.getAttribute('data-path');
      const input = wrap.querySelector('[data-path-input], textarea, input, select');
      if (!input || !path) return;
      if (input.type === 'checkbox') {
        _values[path] = input.checked;
        const label = wrap.querySelector('.dict-switch-label');
        if (label) label.textContent = input.checked ? '已开启' : '已关闭';
      } else if (input.type === 'number') {
        _values[path] = input.value === '' ? '' : Number(input.value);
      } else {
        _values[path] = input.value;
      }
    });
  }

  async function saveModule() {
    if (!_module || !_selected) return;
    if (_module.view_type === 'form') collectFormValues();
    const body = _module.view_type === 'table' ? { rows: _rows } : { values: _values };
    try {
      _module = await apiFetch('/api/config-dict/module/' + encodeURIComponent(_module.module_id), {
        method: 'PUT',
        body: JSON.stringify(body),
      });
      if (_module.view_type === 'table') _rows = (_module.rows || []).map((r) => ({ ...r }));
      else _values = { ...(_module.values || {}) };
      toast('保存成功');
      renderHeader(false);
      renderBody();
    } catch (e) {
      toast(e.message || '保存失败');
    }
  }

  async function init() {
    try {
      _tree = await apiFetch('/api/config-dict/tree');
      _tree.forEach((g) => _expanded.add(g.id));
      renderTree();
    } catch (e) {
      toast('加载分类失败: ' + e.message);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
