/** 财富旅程状态 — sessionStorage，供顾问 Agent 跨页共享 */
const JourneyState = {
  KEY_PREFIX: 'wealthJourney:v1:',

  STEPS: [
    { id: 'inventory', label: '财富盘点', href: 'wealth_inventory.html' },
    { id: 'diagnosis', label: '资产诊断', href: 'asset_diagnosis.html' },
    { id: 'allocation_setup', label: '智能资配', href: 'smart_allocation_setup.html' },
    { id: 'allocation_work', label: '配仓方案', href: 'smart_allocation.html' },
    { id: 'plan_review', label: '方案落地', href: 'smart_allocation.html' },
    { id: 'post_investment', label: '投后SOP', href: 'sop_agent.html' },
  ],

  _key(customerId) {
    return `${this.KEY_PREFIX}${customerId || '_none'}`;
  },

  get(customerId) {
    try {
      const raw = sessionStorage.getItem(this._key(customerId));
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  },

  save(customerId, state) {
    if (!customerId) return;
    try {
      sessionStorage.setItem(this._key(customerId), JSON.stringify(state || {}));
    } catch (e) {
      /* ignore */
    }
  },

  merge(customerId, patch) {
    const prev = this.get(customerId) || {};
    const next = { ...prev, ...patch, customer_id: customerId };
    this.save(customerId, next);
    return next;
  },

  markStep(customerId, stepId) {
    const prev = this.get(customerId) || { completed_steps: [] };
    const done = new Set(prev.completed_steps || []);
    done.add(stepId);
    return this.merge(customerId, {
      stage: stepId,
      completed_steps: Array.from(done),
    });
  },

  inferStageFromPage() {
    const name = (location.pathname.split('/').pop() || '').toLowerCase();
    const hit = this.STEPS.find(s => s.href === name);
    if (hit) return hit.id;
    if (name.startsWith('admin/') || name.includes('sop_batch')) return 'post_investment';
    return 'inventory';
  },

  buildPayload(customerId, extras = {}) {
    const stored = this.get(customerId) || {};
    const pageStage = this.inferStageFromPage();
    return {
      customer_id: customerId,
      stage: stored.stage || pageStage,
      completed_steps: stored.completed_steps || [],
      ...extras,
    };
  },
};
