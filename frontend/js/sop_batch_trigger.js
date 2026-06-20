/** 运营管理 · 批量任务 · 触发管理 */

const SopBatchTrigger = (() => {
  let triggerRow = null;

  function esc(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function statusBadge(enabled) {
    return enabled
      ? '<span class="status status-active">启用</span>'
      : '<span class="status status-inactive">停用</span>';
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

    const close = () => backdrop.remove();
    backdrop.querySelectorAll('[data-close]').forEach((el) => { el.onclick = close; });
    backdrop.addEventListener('click', (e) => { if (e.target === backdrop) close(); });
    backdrop.querySelector('[data-save]').onclick = async () => {
      const btn = backdrop.querySelector('[data-save]');
      btn.disabled = true;
      try {
        await onSave(backdrop);
        close();
      } catch (e) {
        showToast(e.message || '保存失败');
      } finally {
        btn.disabled = false;
      }
    };
  }

  function renderMeta(status) {
    const el = document.getElementById('triggerMeta');
    if (!el || !status) return;
    const parts = [
      `<span>调度线程：<strong>${status.scheduler_running ? '运行中' : '未启动'}</strong></span>`,
      `<span>时区：<strong>${esc(status.timezone_note || '服务器本地')}</strong></span>`,
    ];
    if (status.last_trigger_time) {
      parts.push(`<span>上次执行：<strong>${esc(status.last_trigger_time)}</strong></span>`);
    }
    if (status.next_run_hint && status.enabled) {
      parts.push(`<span>预计下次：<strong>${esc(status.next_run_hint)}</strong></span>`);
    }
    el.innerHTML = parts.join('');
  }

  function renderTable(row) {
    const panel = document.getElementById('triggerPanel');
    if (!row) {
      panel.innerHTML = '<div class="empty-cell">暂无触发配置</div>';
      return;
    }
    panel.innerHTML =
      '<div class="search-bar">' +
      '<h3>触发列表</h3>' +
      '<a class="btn btn-secondary" href="../sop_agent.html#batch">前往手动跑批</a>' +
      '</div>' +
      '<div class="batch-table-wrapper"><table class="batch-table"><thead><tr>' +
      '<th>任务名称</th><th>触发类型</th><th>Cron / 时间</th><th>关联动作</th><th>描述</th><th>状态</th><th>上次执行</th><th>操作</th>' +
      '</tr></thead><tbody>' +
      '<tr>' +
      '<td>' + esc(row.trigger_name) + '</td>' +
      '<td>' + esc(row.trigger_type) + '</td>' +
      '<td><span class="cron-code">' + esc(row.cron) + '</span><br><span style="font-size:12px;color:var(--fg-3)">' + esc(row.cron_label) + '</span></td>' +
      '<td>' + esc(row.action_label) + '</td>' +
      '<td style="max-width:240px">' + esc(row.description) + '</td>' +
      '<td>' + statusBadge(row.enabled) + '</td>' +
      '<td>' + esc(row.last_trigger_time || '—') + '</td>' +
      '<td><div class="table-actions">' +
      '<button type="button" class="btn-link" id="btnEditTrigger">编辑</button>' +
      '<button type="button" class="btn-link" id="btnRunTrigger">立即执行</button>' +
      '</div></td>' +
      '</tr></tbody></table></div>';

    document.getElementById('btnEditTrigger').onclick = () => showEditDrawer(row);
    document.getElementById('btnRunTrigger').onclick = () => runNow(row);
  }

  function showEditDrawer(row) {
    const pushDisabled = !row.run_agent_after_batch;
    const body =
      '<div class="form-grid">' +
      '<div class="form-field"><label>任务名称</label><input value="' + esc(row.trigger_name) + '" readonly></div>' +
      '<div class="form-field"><label>触发类型</label><input value="CRON（每日）" readonly></div>' +
      '<div class="form-row-2">' +
      '<div class="form-field"><label>执行小时（0-23）</label><input type="number" name="hour" min="0" max="23" value="' + row.hour + '"></div>' +
      '<div class="form-field"><label>执行分钟（0-59）</label><input type="number" name="minute" min="0" max="59" value="' + row.minute + '"></div>' +
      '</div>' +
      '<p class="form-hint">当前等价 Cron：<code>0 ' + row.minute + ' ' + row.hour + ' * * ?</code>（Quartz 风格，每日触发）</p>' +
      '<div class="form-field"><label>启用定时</label>' +
      '<select name="enabled"><option value="true"' + (row.enabled ? ' selected' : '') + '>启用</option>' +
      '<option value="false"' + (!row.enabled ? ' selected' : '') + '>停用</option></select></div>' +
      '<div class="form-field"><label>跑批后自动智能生成（6.2）</label>' +
      '<select name="run_agent_after_batch" id="fldRunAgent"><option value="true"' + (row.run_agent_after_batch ? ' selected' : '') + '>是</option>' +
      '<option value="false"' + (!row.run_agent_after_batch ? ' selected' : '') + '>否（仅 6.1 写事件库）</option></select></div>' +
      '<div class="form-field" id="fldPushWrap"' + (pushDisabled ? ' style="opacity:0.55"' : '') + '>' +
      '<label>智能生成后自动推送飞书（6.2.5）</label>' +
      '<select name="push_feishu_after_agent" id="fldPushFeishu"' + (pushDisabled ? ' disabled' : '') + '>' +
      '<option value="true"' + (row.push_feishu_after_agent && row.run_agent_after_batch ? ' selected' : '') + '>是</option>' +
      '<option value="false"' + (!row.push_feishu_after_agent || !row.run_agent_after_batch ? ' selected' : '') + '>否</option></select>' +
      '<p class="form-hint" id="fldPushHint">' + (pushDisabled ? '需先启用「跑批后自动智能生成」才可配置自动推送。' : '启用后：跑批 → 智能生成 → 飞书推送给客户经理。') + '</p></div>' +
      '<div class="form-field"><label>说明</label><textarea readonly>' + esc(row.description) + '</textarea></div>' +
      '</div>';

    openDrawer('编辑触发配置 · ' + row.trigger_name, body, async (backdrop) => {
      const runAgent = backdrop.querySelector('[name="run_agent_after_batch"]').value === 'true';
      const pushEl = backdrop.querySelector('[name="push_feishu_after_agent"]');
      const payload = {
        enabled: backdrop.querySelector('[name="enabled"]').value === 'true',
        hour: Number(backdrop.querySelector('[name="hour"]').value),
        minute: Number(backdrop.querySelector('[name="minute"]').value),
        run_agent_after_batch: runAgent,
        push_feishu_after_agent: runAgent && pushEl && !pushEl.disabled
          ? pushEl.value === 'true'
          : false,
      };
      if (Number.isNaN(payload.hour) || Number.isNaN(payload.minute)) {
        throw new Error('请填写有效的执行时间');
      }
      await apiPut('/api/sop/agent/schedule/config', payload);
      showToast('定时配置已保存');
      await load();
    });

    const runAgentEl = document.querySelector('#fldRunAgent');
    const pushWrap = document.querySelector('#fldPushWrap');
    const pushFeishuEl = document.querySelector('#fldPushFeishu');
    const pushHint = document.querySelector('#fldPushHint');
    if (runAgentEl && pushFeishuEl) {
      runAgentEl.addEventListener('change', () => {
        const on = runAgentEl.value === 'true';
        pushFeishuEl.disabled = !on;
        if (pushWrap) pushWrap.style.opacity = on ? '1' : '0.55';
        if (!on) pushFeishuEl.value = 'false';
        if (pushHint) {
          pushHint.textContent = on
            ? '启用后：跑批 → 智能生成 → 飞书推送给客户经理。'
            : '需先启用「跑批后自动智能生成」才可配置自动推送。';
        }
      });
    }
  }

  async function runNow(row) {
    if (!confirm('立即执行「' + row.trigger_name + '」？\n\n将按定时任务逻辑跑批（今日已跑过则跳过，除非强制）。')) return;
    try {
      const res = await apiPost('/api/sop/events/scheduled-batch?force=false');
      const d = res.data || {};
      if (d.skipped) {
        showToast('今日已跑批：' + (d.reason || '已跳过'));
      } else {
        const batch = d.batch || {};
        showToast('执行完成：新增事件 ' + (batch.composite_events || 0) + ' 条');
      }
      await load();
    } catch (e) {
      showToast(e.message || '执行失败');
    }
  }

  async function load() {
    const [triggersRes, statusRes] = await Promise.all([
      apiGet('/api/sop/agent/schedule/triggers'),
      apiGet('/api/sop/agent/schedule/status'),
    ]);
    triggerRow = ((triggersRes.data || {}).triggers || [])[0] || null;
    renderMeta(statusRes.data);
    renderTable(triggerRow);
  }

  return {
    init() {
      load().catch((e) => {
        document.getElementById('triggerPanel').innerHTML =
          '<div class="empty-cell">' + esc(e.message) + '</div>';
      });
    },
  };
})();
