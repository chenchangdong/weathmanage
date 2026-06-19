/**
 * SOP 投后 — 旅程导航（工作流 + 配置条，与资配旅程区分）
 */
(function () {
  'use strict';

  const WORKFLOW = [
    { id: 'batch', label: '① 跑批触发' },
    { id: 'query', label: '② 查询事件' },
    { id: 'generate', label: '③ 批量生成' },
  ];

  const CONFIG = [
    { id: 'rule_strategy', label: '规则策略', page: 'rule_strategy', href: 'admin/rule_strategy.html', adminHref: 'rule_strategy.html' },
    { id: 'sop_product_library', label: '产品信息库', page: 'sop_product_library', href: 'admin/sop_product_library.html', adminHref: 'sop_product_library.html' },
  ];

  function isAdminPath() {
    return /\/admin\//.test(window.location.pathname);
  }

  function agentHref() {
    return isAdminPath() ? '../sop_agent.html' : 'sop_agent.html';
  }

  function stepHref(stepId) {
    if (stepId === 'batch') return agentHref() + '#batch';
    if (stepId === 'generate') return agentHref() + '#generate';
    return agentHref();
  }

  function configHref(item) {
    return isAdminPath() ? item.adminHref : item.href;
  }

  function renderWorkflowBar(activeId, mode) {
    const parts = [];
    const isConfig = mode === 'config';
    const isWorkspace = mode === 'workspace';
    WORKFLOW.forEach((step, i) => {
      if (i > 0) parts.push('<span class="journey-step-arrow">→</span>');
      if (!isConfig && step.id === activeId) {
        parts.push(`<span class="journey-step active">${step.label}</span>`);
      } else if (isWorkspace) {
        parts.push(
          `<button type="button" class="journey-step link" data-sop-step="${step.id}">${step.label}</button>`
        );
      } else {
        const cls = isConfig ? 'journey-step link muted-step' : 'journey-step link';
        parts.push(`<a href="${stepHref(step.id)}" class="${cls}">${step.label}</a>`);
      }
    });
    return `<div class="journey-step-bar sop-workflow-bar" aria-label="SOP 工作流">${parts.join('')}</div>`;
  }

  function renderConfigBar(activePage) {
    const links = CONFIG.map((item) => {
      const cls = item.page === activePage ? ' sop-config-link active' : ' sop-config-link';
      return `<a href="${configHref(item)}" class="${cls.trim()}">${item.label}</a>`;
    }).join('<span class="sop-config-sep">·</span>');
    const home = activePage === 'sop_agent'
      ? '<span class="sop-config-link active">智能体工作台</span>'
      : `<a href="${agentHref()}" class="sop-config-link">智能体工作台</a>`;
    return (
      '<div class="sop-config-bar" aria-label="SOP 配置">' +
      '<span class="sop-config-label">SOP 投后</span>' +
      home +
      '<span class="sop-config-sep">·</span>' +
      links +
      '</div>'
    );
  }

  function mount(options) {
    const opts = options || {};
    const mountEl = typeof opts.mount === 'string' ? document.querySelector(opts.mount) : opts.mount;
    if (!mountEl) return;

    const activeWorkflow = opts.activeWorkflow || 'query';
    const activePage = opts.activePage || 'sop_agent';
    const workflowMode = opts.workflowMode || (activePage === 'sop_agent' ? 'workspace' : 'config');

    mountEl.innerHTML =
      '<div class="sop-journey-wrap">' +
      (opts.showWorkflow !== false ? renderWorkflowBar(activeWorkflow, workflowMode) : '') +
      renderConfigBar(activePage) +
      '</div>';

    mountEl.querySelectorAll('[data-sop-step]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const step = btn.dataset.sopStep;
        if (typeof opts.onStepChange === 'function') opts.onStepChange(step);
      });
    });
  }

  function parseStepFromHash() {
    const hash = (window.location.hash || '').replace('#', '');
    if (hash === 'batch' || hash === 'generate' || hash === 'query') return hash;
    return 'query';
  }

  window.SopJourney = { mount, parseStepFromHash, agentHref, stepHref, WORKFLOW };
})();
