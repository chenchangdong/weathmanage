/** AI 顾问对话 — 招行小招式气泡交互 */

const AdvisorChat = {
  OPEN_STORAGE_KEY: 'advisorChatOpen',
  SESSION_KEY_PREFIX: 'advisorChatSession:',
  INFLIGHT_KEY_PREFIX: 'advisorChatInflight:',
  _open: false,
  _history: [],
  _uiMessages: [],
  _status: null,
  _sending: false,
  _welcomed: false,
  _inflight: null,
  _inflightPartialReasoning: '',
  _inflightPartialContent: '',
  _abortController: null,
  _preloaded: null,
  _mounted: false,
  _pageDockOptions: null,
  _lastPageCustomerId: null,
  NUDGE_KEY_PREFIX: 'advisorNudgeShown:v1:',

  QUICK_SERVICES: [
    {
      icon: '🚀',
      title: '全流程服务',
      desc: '盘点→诊断→配仓',
      promptKey: 'full_service',
      agent: true,
    },
    {
      icon: '🧭',
      title: '下一步建议',
      desc: '旅程进度指引',
      prompt: '我接下来该做什么？',
      agent: true,
    },
    {
      icon: '📡',
      title: '投后跟进',
      desc: 'SOP事件与话术',
      prompt: '该客户有哪些投后事件需要处理？',
      agent: true,
    },
    {
      icon: '💚',
      title: '健康度解读',
      desc: '资配健康分析',
      prompt: '请解读该客户财富健康度，先给结论，再用 3~4 条要点说明优先处理建议',
    },
    {
      icon: '📋',
      title: '资产诊断解读',
      desc: '结构化诊断分析',
      prompt: '请基于 grounding 中 asset_diagnosis 的结构化诊断结果，解读综合评分、五维雷达、四笔钱配置与财富健康标志，先给结论，再用 3~4 条要点说明优先处理建议',
    },
    {
      icon: '📊',
      title: '方案解读',
      desc: '调仓逻辑说明',
      prompt: '请说明当前配置方案的关键调仓逻辑，如有次优解一并简述',
    },
    {
      icon: '🔄',
      title: '替代思路',
      desc: '合规调仓建议',
      prompt: '若客户不愿减持某类产品，请给出 2~3 条合规替代思路',
    },
    {
      icon: '💬',
      title: '客户话术',
      desc: '沟通要点提炼',
      prompt: '请生成一段约 200 字的客户沟通话术，语气专业亲和',
    },
  ],

  mountShell() {
    const existingPanel = document.getElementById('advisorChatPanel');
    if (existingPanel) {
      this._moveShellToBody();
      return;
    }
    const wrap = document.createElement('div');
    wrap.innerHTML = `
      <div id="advisorChatBackdrop" class="advisor-chat-backdrop" aria-hidden="true"></div>
      <div id="advisorChatPanel" class="advisor-chat-panel" role="dialog" aria-label="智能投顾顾问">
        <header class="advisor-chat-header">
          <button type="button" class="advisor-chat-back" id="advisorChatClose" aria-label="返回">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 18l-6-6 6-6"/></svg>
          </button>
          <div class="advisor-chat-header-center">
            <div class="advisor-chat-orb" aria-hidden="true"></div>
            <div id="advisorChatStatus" class="advisor-chat-status offline">
              <span class="advisor-chat-status-label">连接状态检测中…</span>
            </div>
          </div>
          <button type="button" class="advisor-chat-clear" id="advisorChatClear" title="清空对话" aria-label="清空对话">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/></svg>
          </button>
        </header>
        <div id="advisorChatJourney" class="advisor-chat-journey" aria-label="服务进度"></div>
        <div id="advisorChatMessages" class="advisor-chat-messages"></div>
        <footer class="advisor-chat-footer">
          <div class="advisor-chat-input-wrap">
            <button type="button" class="advisor-chat-input-icon" tabindex="-1" aria-hidden="true">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5-3c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/></svg>
            </button>
            <input type="text" id="advisorChatInput" placeholder="欢迎向智能顾问提问~" autocomplete="off" maxlength="500" />
            <button type="button" class="advisor-chat-send" id="advisorChatSend" disabled aria-label="发送">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
            </button>
          </div>
          <p class="advisor-chat-disclaimer">以上内容由 AI 生成，仅供参考，不构成投资建议</p>
        </footer>
      </div>
      <button type="button" id="advisorChatToggle" class="advisor-chat-fab" title="智能投顾顾问">
        <span class="advisor-chat-fab-icon" aria-hidden="true">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.17L4 17.17V4h16v12z"/><path d="M7 9h10v2H7zm0-3h10v2H7zm0 6h7v2H7z"/></svg>
        </span>
        <span class="advisor-chat-fab-label">智能顾问</span>
      </button>`;
    while (wrap.firstChild) {
      document.body.appendChild(wrap.firstChild);
    }
    this._applyPendingOpenShell();
  },

  _moveShellToBody() {
    ['advisorChatBackdrop', 'advisorChatPanel', 'advisorChatToggle'].forEach((id) => {
      const el = document.getElementById(id);
      if (el && el.parentElement !== document.body) {
        document.body.appendChild(el);
      }
    });
  },

  _rerenderUiMessages() {
    const box = document.getElementById('advisorChatMessages');
    if (!box) return;
    box.innerHTML = '';
    this._uiMessages.forEach((m) => {
      if (m.kind === 'welcome') {
        this.showWelcome({ skipPersist: true, time: m.time });
      } else {
        this.appendMessage(m.role, m.content, m.meta || {}, {
          skipPersist: true,
          time: m.time,
        });
      }
    });
  },

  _ensureShellOnBody() {
    if (document.getElementById('advisorChatPanel')) {
      this._moveShellToBody();
      return false;
    }
    const wasOpen = this._open;
    this.mountShell();
    this.bindUI();
    this._rerenderUiMessages();
    if (wasOpen) {
      this.setOpen(true, { skipPersist: true, skipFocus: true, skipAnimation: true });
    }
    return true;
  },

  _applyPendingOpenShell() {
    const pending = document.documentElement.classList.contains('advisor-chat-pending-open');
    if (!pending) return;
    this._open = true;
    const panel = document.getElementById('advisorChatPanel');
    const fab = document.getElementById('advisorChatToggle');
    if (panel) {
      panel.classList.add('open', 'advisor-chat-instant');
    }
    if (fab) fab.classList.add('hidden');
    if (this._isDockedLayout()) {
      document.body.classList.add('advisor-chat-docked-open');
    }
  },

  PAGE_DOCK_CONTAINERS:
    '.container-smart-allocation, .container-wealth, .container-diagnosis, .container-sop, .container',

  async init(options = {}) {
    if (this._mounted && this._isDockedLayout()) {
      return this.onPageEnter({ ...this._pageDockOptions, ...options, dock: true });
    }
    this._pageDockOptions = { ...options };
    this.mountShell();
    this.setupPageDock(options.dock);
    if (typeof syncCustomerContextFromUrl === 'function') {
      syncCustomerContextFromUrl();
    }
    const initCid = typeof getCustomerId === 'function' ? getCustomerId() : '';
    if (initCid && typeof loadCustomerList === 'function') {
      try {
        await loadCustomerList();
      } catch (e) {
        /* fallback CUSTOMERS */
      }
    }
    if (this._isDockedLayout()) {
      document.body.classList.add('advisor-chat-instant-layout');
    }
    this.bindUI();
    this._restoreSessionState();
    await this._resumeInflightIfNeeded();
    this.bindPageLinkedActions(options);
    await this.refreshStatus();
    await this.preloadContext();
    this.renderJourneyProgress(this._lastJourney || this._journeyFromPreload());
    if (this._isDockedLayout()) {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          document.body.classList.remove('advisor-chat-instant-layout');
        });
      });
    }
    this._mounted = true;
    this._lastPageCustomerId = (typeof getCustomerId === 'function' ? getCustomerId() : '') || '_none';
  },

  /** 软导航换页：不重建侧栏，只更新上下文与页面联动 */
  async onPageEnter(options = {}) {
    if (!this._mounted) return this.init(options);
    this._pageDockOptions = { ...(this._pageDockOptions || {}), ...options };
    this._ensureShellOnBody();
    this.setupPageDock(true);
    if (typeof syncCustomerContextFromUrl === 'function') {
      syncCustomerContextFromUrl();
    }
    const prevCid = this._lastPageCustomerId;
    const cid = typeof getCustomerId === 'function' ? getCustomerId() : '';
    const cidKey = cid || '_none';
    if (prevCid && cidKey && prevCid !== cidKey && prevCid !== '_none' && cidKey !== '_none') {
      await this.reloadForCustomer();
    } else if (prevCid !== cidKey) {
      await this.switchCustomerSession();
    }
    this._lastPageCustomerId = cidKey;
    this.bindPageLinkedActions(this._pageDockOptions);
    await this.refreshStatus();
    await this.preloadContext();
    this.renderJourneyProgress(this._lastJourney || this._journeyFromPreload());
    if (this._open) {
      this.setOpen(true, { skipPersist: true, skipFocus: true, skipAnimation: true });
    }
    this._persistSession();
  },

  /** 盘点 hub ↔ 客户页切换：换会话但不关闭侧栏 */
  async switchCustomerSession() {
    if (this._abortController) this._abortController.abort();
    this._clearInflight();
    this._history = [];
    this._uiMessages = [];
    this._welcomed = false;
    this._sending = false;
    const box = document.getElementById('advisorChatMessages');
    if (box) box.innerHTML = '';
    this.hideTyping();
    this._restoreSessionState();
    if (typeof JourneyState !== 'undefined') {
      const activeCid = typeof getCustomerId === 'function' ? getCustomerId() : '';
      if (activeCid) this.renderJourneyProgress(JourneyState.get(activeCid));
    }
    await this._resumeInflightIfNeeded();
    this._syncSendBtn();
  },

  _journeyFromPreload() {
    if (this._preloaded && this._preloaded.journey) return this._preloaded.journey;
    const cid = typeof getCustomerId === 'function' ? getCustomerId() : '';
    return (typeof JourneyState !== 'undefined' && cid) ? JourneyState.get(cid) : null;
  },

  _nudgeStorageKey() {
    const page = location.pathname.split('/').pop() || '';
    const onHub = typeof isCustomerHubPage === 'function' && isCustomerHubPage();
    if (onHub) {
      return `${this.NUDGE_KEY_PREFIX}hub:_none`;
    }
    const cid = typeof getCustomerId === 'function' ? getCustomerId() : '';
    // 同一客户旅程内只提示一次，换页不重复弹
    return `${this.NUDGE_KEY_PREFIX}customer:${cid || '_none'}`;
  },

  async preloadContext() {
    if (!this._useAgentMode()) return null;
    const page = location.pathname.split('/').pop() || '';
    const cid = typeof getCustomerId === 'function' ? getCustomerId() : '';
    const hubOrSop = page === 'sop_agent.html' || page === 'wealth_inventory.html';
    if (!cid && !hubOrSop) return null;
    try {
      const q = new URLSearchParams();
      if (cid) q.set('customer_id', cid);
      q.set('page', page);
      const res = await apiGet(`/api/ai/context?${q.toString()}`);
      this._preloaded = res.data;
      if (res.data.diagnosis && typeof diagnosisData !== 'undefined') {
        diagnosisData = res.data.diagnosis;
      }
      if (res.data.overview && typeof overviewData !== 'undefined') {
        overviewData = res.data.overview;
      }
      if (res.data.journey) this._applyJourney(res.data.journey);
      return res.data;
    } catch (e) {
      return null;
    }
  },

  async maybeShowProactiveNudge() {
    if (!this._useAgentMode() || !this._open) return;
    const hasConversation = this._uiMessages.some(
      m => m.role === 'user' || (m.role === 'assistant' && !(m.meta && m.meta.nudge))
    );
    if (hasConversation) return;
    if (this._uiMessages.some(m => m.meta && m.meta.nudge)) return;
    try {
      if (sessionStorage.getItem(this._nudgeStorageKey())) return;
    } catch (e) {
      return;
    }
    const page = location.pathname.split('/').pop() || '';
    const onHub = typeof isCustomerHubPage === 'function' && isCustomerHubPage();
    const cid = onHub ? '' : (typeof getCustomerId === 'function' ? getCustomerId() : '');
    try {
      const q = new URLSearchParams({ page });
      if (cid) q.set('customer_id', cid);
      const res = await apiGet(`/api/ai/nudge?${q.toString()}`);
      const nudge = res.data && res.data.nudge;
      if (!nudge || !nudge.message) return;
      sessionStorage.setItem(this._nudgeStorageKey(), '1');
      this.appendMessage('assistant', nudge.message, {
        source: 'agent',
        actions: nudge.actions || [],
        nudge: true,
      });
    } catch (e) {
      /* ignore nudge errors */
    }
  },

  _defaultOpenOnDock() {
    return this._isDockedLayout() && sessionStorage.getItem(this.OPEN_STORAGE_KEY) !== '0';
  },

  _sessionKey() {
    const cid = typeof getCustomerId === 'function' ? getCustomerId() : '';
    return `${this.SESSION_KEY_PREFIX}${cid || '_none'}`;
  },

  _inflightKey() {
    const cid = typeof getCustomerId === 'function' ? getCustomerId() : '';
    return `${this.INFLIGHT_KEY_PREFIX}${cid || '_none'}`;
  },

  _beginInflight({ message, userLabel, historyBefore, linkedParams, useLlm }) {
    this._inflight = {
      message,
      userLabel,
      historyBefore: Array.isArray(historyBefore) ? historyBefore : [],
      linkedParams: linkedParams || {},
      useLlm: !!useLlm,
    };
    this._inflightPartialReasoning = '';
    this._inflightPartialContent = '';
    this._persistInflight();
  },

  _persistInflight(extra = {}) {
    if (!this._inflight) return;
    try {
      const payload = {
        customerId: typeof getCustomerId === 'function' ? getCustomerId() : '',
        message: this._inflight.message,
        userLabel: this._inflight.userLabel,
        historyBefore: this._inflight.historyBefore,
        linkedParams: this._inflight.linkedParams,
        partialReasoning: this._inflightPartialReasoning || '',
        partialContent: this._inflightPartialContent || '',
        interrupted: !!extra.interrupted,
      };
      sessionStorage.setItem(this._inflightKey(), JSON.stringify(payload));
    } catch (e) {
      /* sessionStorage unavailable */
    }
  },

  _schedulePersistInflight() {
    if (this._inflightPersistTimer) clearTimeout(this._inflightPersistTimer);
    this._inflightPersistTimer = setTimeout(() => {
      if (this._sending && this._inflight) this._persistInflight();
    }, 250);
  },

  _clearInflight() {
    this._inflight = null;
    this._inflightPartialReasoning = '';
    this._inflightPartialContent = '';
    if (this._inflightPersistTimer) {
      clearTimeout(this._inflightPersistTimer);
      this._inflightPersistTimer = null;
    }
    try {
      sessionStorage.removeItem(this._inflightKey());
    } catch (e) {
      /* ignore */
    }
  },

  _createStreamHooks() {
    return {
      linkedParams: (this._inflight && this._inflight.linkedParams) || {},
      onReasoning: (t) => {
        this._inflightPartialReasoning = t;
        this._updateLiveReasoning(t);
        this._schedulePersistInflight();
      },
      onContent: (t) => {
        this._inflightPartialContent = t;
        this._updateLiveReply(t);
        this._schedulePersistInflight();
      },
    };
  },

  async _completeInflightTurn(options = {}) {
    const inflight = this._inflight;
    if (!inflight) return null;

    const { message, historyBefore, linkedParams } = inflight;
    const cid = getCustomerId();
    const { overview, plan, diagnosis: ctxDiagnosis } = this.getContextPayload();
    let diagnosis = ctxDiagnosis;
    if (this._useAgentMode() && cid && !diagnosis) {
      diagnosis = (this._preloaded && this._preloaded.diagnosis)
        || await this._preloadDiagnosis(cid)
        || ctxDiagnosis;
    }
    const hooks = this._createStreamHooks();

    let result = null;
    const useLlm = !!(inflight.useLlm || (linkedParams && linkedParams.useLlm));
    try {
      if (this._useAgentMode() && !useLlm) {
        result = await this._fetchAgent(
          message,
          cid,
          overview,
          plan,
          diagnosis,
          historyBefore || [],
        );
      } else {
        result = await this._fetchStream(
          message,
          cid,
          overview,
          plan,
          diagnosis,
          historyBefore || [],
          hooks
        );
        if (!result) {
          result = await this._fetchFallback(
            message,
            cid,
            overview,
            plan,
            diagnosis,
            historyBefore || [],
            linkedParams || {}
          );
        }
      }
      this.hideTyping();
      if (result && result.agent) {
        this._appendAssistantFromAgentResult(message, result);
      } else {
        this._appendAssistantFromResult(message, result);
      }
      if (options.onComplete) options.onComplete(result);
      return result;
    } catch (e) {
      if (e.name === 'AbortError') return null;
      this.hideTyping();
      this.appendMessage(
        'assistant',
        '请求失败：' + e.message + '。推理模型可能需要 30–60 秒，请确认服务未超时。',
        { source: 'fallback' }
      );
      return null;
    } finally {
      this._abortController = null;
      this._clearInflight();
      this._sending = false;
      this._syncSendBtn();
    }
  },

  async _resumeInflightIfNeeded() {
    try {
      const raw = sessionStorage.getItem(this._inflightKey());
      if (!raw) return;
      const data = JSON.parse(raw);
      const cid = typeof getCustomerId === 'function' ? getCustomerId() : '';
      if (!cid || data.customerId !== cid || !data.message) return;

      this._inflight = {
        message: data.message,
        userLabel: data.userLabel || data.message,
        historyBefore: Array.isArray(data.historyBefore) ? data.historyBefore : [],
        linkedParams: data.linkedParams || {},
      };
      this._inflightPartialReasoning = data.partialReasoning || '';
      this._inflightPartialContent = data.partialContent || '';
      this._sending = true;
      this._syncSendBtn();
      this.setOpen(true, { skipFocus: true, skipAnimation: true, skipPersist: true });

      this.showTyping();
      if (this._inflightPartialReasoning) {
        this._updateLiveReasoning(this._inflightPartialReasoning);
      }
      if (this._inflightPartialContent) {
        this._updateLiveReply(this._inflightPartialContent);
      }

      await this._waitForPageContext();
      await this._completeInflightTurn();
    } catch (e) {
      this._clearInflight();
      this._sending = false;
      this._syncSendBtn();
    }
  },

  /** 跳转后续传前等待当前页业务数据就绪，以便 grounding 完整 */
  async _waitForPageContext(maxMs = 5000) {
    const path = location.pathname.split('/').pop() || '';
    const start = Date.now();
    while (Date.now() - start < maxMs) {
      if (path === 'asset_diagnosis.html') {
        if (typeof diagnosisData === 'undefined') break;
        if (diagnosisData !== null) break;
      } else if (path === 'smart_allocation.html' || path === 'smart_allocation_setup.html') {
        if (typeof overviewData === 'undefined') break;
        if (overviewData !== null) break;
      } else {
        break;
      }
      await new Promise((r) => setTimeout(r, 80));
    }
  },

  _persistSession() {
    try {
      const box = document.getElementById('advisorChatMessages');
      const payload = {
        open: this._open,
        welcomed: this._welcomed,
        history: this._history,
        messages: this._uiMessages,
        scrollTop: box ? box.scrollTop : 0,
      };
      sessionStorage.setItem(this._sessionKey(), JSON.stringify(payload));
      sessionStorage.setItem(this.OPEN_STORAGE_KEY, this._open ? '1' : '0');
    } catch (e) {
      /* sessionStorage unavailable */
    }
  },

  _schedulePersistScroll() {
    if (this._scrollPersistTimer) clearTimeout(this._scrollPersistTimer);
    this._scrollPersistTimer = setTimeout(() => this._persistSession(), 120);
  },

  _restoreSessionState() {
    try {
      const raw = sessionStorage.getItem(this._sessionKey());
      if (!raw) {
        if (this._defaultOpenOnDock()) {
          this.setOpen(true, { skipPersist: true, skipFocus: true, skipAnimation: true });
        } else if (sessionStorage.getItem(this.OPEN_STORAGE_KEY) === '1') {
          this.setOpen(true, { skipPersist: true, skipFocus: true, skipAnimation: true });
        } else if (document.documentElement.classList.contains('advisor-chat-pending-open')) {
          this._clearPendingOpen();
        }
        return;
      }

      const data = JSON.parse(raw);
      this._history = Array.isArray(data.history) ? data.history : [];
      this._uiMessages = Array.isArray(data.messages) ? data.messages : [];
      this._welcomed = false;

      const box = document.getElementById('advisorChatMessages');
      if (box) box.innerHTML = '';

      this._uiMessages.forEach((m) => {
        if (m.kind === 'welcome') {
          this.showWelcome({ skipPersist: true, time: m.time });
        } else {
          this.appendMessage(m.role, m.content, m.meta || {}, {
            skipPersist: true,
            time: m.time,
          });
        }
      });

      if (data.welcomed && !this._uiMessages.some(m => m.kind === 'welcome')) {
        this.showWelcome({ skipPersist: true });
      }

      if (data.open === false) {
        this.setOpen(false, { skipPersist: true, skipFocus: true, skipAnimation: true });
      } else if (data.open || this._defaultOpenOnDock()) {
        this.setOpen(true, { skipPersist: true, skipFocus: true, skipAnimation: true });
      }

      if (box && typeof data.scrollTop === 'number') {
        requestAnimationFrame(() => {
          box.scrollTop = data.scrollTop;
        });
      }
    } catch (e) {
      /* ignore corrupt session */
    } finally {
      this._clearPendingOpen();
    }
  },

  _clearPendingOpen() {
    document.documentElement.classList.remove('advisor-chat-pending-open');
    const panel = document.getElementById('advisorChatPanel');
    if (panel) {
      requestAnimationFrame(() => panel.classList.remove('advisor-chat-instant'));
    }
  },

  /** 切换客户时恢复该客户的历史会话（无记录则空白） */
  async reloadForCustomer() {
    if (this._abortController) this._abortController.abort();
    this._clearInflight();
    this._history = [];
    this._uiMessages = [];
    this._welcomed = false;
    this._open = false;
    this._sending = false;
    const box = document.getElementById('advisorChatMessages');
    if (box) box.innerHTML = '';
    document.body.classList.remove('advisor-chat-docked-open', 'advisor-chat-open');
    const panel = document.getElementById('advisorChatPanel');
    const fab = document.getElementById('advisorChatToggle');
    if (panel) panel.classList.remove('open');
    if (fab) fab.classList.remove('hidden');
    this.hideTyping();
    this._restoreSessionState();
    if (typeof JourneyState !== 'undefined') {
      const cid = typeof getCustomerId === 'function' ? getCustomerId() : '';
      if (cid) this.renderJourneyProgress(JourneyState.get(cid));
    }
    await this._resumeInflightIfNeeded();
    this._syncSendBtn();
  },

  _useAgentMode() {
    return this._isDockedLayout();
  },

  _resolveQuickPrompt(svc) {
    if (!svc) return '';
    if (svc.promptKey === 'full_service') {
      const cid = typeof getCustomerId === 'function' ? getCustomerId() : '';
      if (!cid) return '';
      const name = typeof getCustomerShortName === 'function'
        ? getCustomerShortName(cid)
        : '当前客户';
      return `帮我完整服务${name}`;
    }
    return svc.prompt || '';
  },

  _welcomeHintHtml() {
    if (typeof isCustomerHubPage === 'function' && isCustomerHubPage()) {
      return '您好，我是您的<strong>智能投顾顾问</strong>。请从左侧客户清单点选客户开始服务；我会根据清单给出优先关注建议。';
    }
    const cid = typeof getCustomerId === 'function' ? getCustomerId() : '';
    let name = typeof getCustomerShortName === 'function' ? getCustomerShortName(cid) : '';
    if ((!name || name === cid) && typeof diagnosisData !== 'undefined' && diagnosisData && diagnosisData.name) {
      name = String(diagnosisData.name).split('（')[0].trim();
    }
    if (cid && name && name !== '未选择客户' && name !== cid) {
      return `您好，我将继续为<strong>${this._escapeHtml(name)}</strong>服务。可说「帮我完整服务${this._escapeHtml(name)}」串联诊断→配仓，或点击下方快捷服务。`;
    }
    return '您好，我是您的<strong>智能投顾顾问</strong>。请从财富盘点选择客户后，我将同步为该客户提供服务。';
  },

  renderJourneyProgress(journey) {
    const el = document.getElementById('advisorChatJourney');
    if (!el) return;
    const steps = (typeof JourneyState !== 'undefined' && JourneyState.STEPS) || [];
    if (!journey || !steps.length) {
      el.innerHTML = '';
      el.style.display = 'none';
      return;
    }
    el.style.display = '';
    const stage = journey.stage || 'inventory';
    const done = new Set(journey.completed_steps || []);
    el.innerHTML = steps.map((s, i) => {
      const active = s.id === stage;
      const completed = done.has(s.id) || steps.findIndex(x => x.id === stage) > i;
      const cls = completed ? 'done' : (active ? 'active' : '');
      const arrow = i < steps.length - 1 ? '<span class="journey-pip-arrow">→</span>' : '';
      return `<span class="journey-pip ${cls}" data-journey-href="${s.href}" title="${s.label}">${s.label}</span>${arrow}`;
    }).join('');
    el.querySelectorAll('[data-journey-href]').forEach(node => {
      node.onclick = () => {
        const href = node.getAttribute('data-journey-href');
        if (href) this._navigateTo(href);
      };
    });
  },

  _applyJourney(journey) {
    if (!journey) return;
    this._lastJourney = journey;
    const cid = journey.customer_id || (typeof getCustomerId === 'function' ? getCustomerId() : '');
    if (cid && typeof JourneyState !== 'undefined') {
      JourneyState.save(cid, journey);
    }
    this.renderJourneyProgress(journey);
  },

  _navigateTo(href, options = {}) {
    if (!href) return;
    const base = href.split('?')[0];
    const file = base.split('/').pop() || base;
    const cid = typeof getCustomerId === 'function' ? getCustomerId() : '';
    if (cid && typeof setSelectedCustomerId === 'function') {
      setSelectedCustomerId(cid);
    }
    const openPlan = options.openPlan
      || (file === 'smart_allocation.html' && this._hasCachedPlan());
    if (file === 'smart_allocation.html' && openPlan) {
      try {
        sessionStorage.setItem('smartAllocOpenPlan', '1');
      } catch (e) { /* ignore */ }
    }
    if (typeof navigateWithCustomer === 'function' && cid) {
      navigateWithCustomer(base, cid);
      return;
    }
    window.location.href = cid
      ? `${base}?customer_id=${encodeURIComponent(cid)}`
      : base;
  },

  _hasCachedPlan() {
    try {
      if (typeof loadResult !== 'function') return false;
      const plan = loadResult();
      return !!(plan && plan.rebalance);
    } catch (e) {
      return false;
    }
  },

  async _preloadDiagnosis(cid) {
    if (typeof diagnosisData !== 'undefined' && diagnosisData) return diagnosisData;
    try {
      const res = await apiGet(`/api/wealth/diagnosis?customer_id=${encodeURIComponent(cid)}`);
      if (typeof diagnosisData !== 'undefined') {
        diagnosisData = res.data;
      }
      return res.data;
    } catch (e) {
      return null;
    }
  },

  getAgentPayload() {
    const cid = typeof getCustomerId === 'function' ? getCustomerId() : '';
    const { overview, plan, diagnosis } = this.getContextPayload();
    const journey = (typeof JourneyState !== 'undefined' && cid)
      ? JourneyState.buildPayload(cid)
      : null;
    return {
      overview,
      plan,
      diagnosis,
      journey,
      page: location.pathname.split('/').pop() || '',
    };
  },

  /** 侧栏停靠页统一初始化（点击外部不关闭、主内容自适应） */
  initDockPage(options = {}) {
    return this.init({ dock: true, ...options });
  },

  /**
   * 启用顾问侧栏停靠：主内容区自适应右移，点击页面其他区域不关闭顾问。
   * 页面在 body 上加 data-advisor-dock，或 init 时传 dock: true。
   */
  setupPageDock(dock) {
    if (dock === false) return;
    const viaAttr = document.body.hasAttribute('data-advisor-dock');
    if (!dock && !viaAttr) return;
    if (!viaAttr) {
      document.body.setAttribute('data-advisor-dock', '');
    }

    let selector = null;
    if (typeof dock === 'string') selector = dock;
    else if (dock && typeof dock === 'object' && dock.container) selector = dock.container;

    let containers = selector
      ? document.querySelectorAll(selector)
      : document.querySelectorAll('.container-advisor-dock');
    if (!containers.length) {
      const fallback = document.querySelector(this.PAGE_DOCK_CONTAINERS);
      if (fallback) containers = [fallback];
    }
    containers.forEach((el) => {
      el.classList.add('container-advisor-dock');
    });
  },

  getQuickService(title) {
    return this.QUICK_SERVICES.find(s => s.title === title);
  },

  /**
   * 页面按钮 → 智能顾问联动：复用 QUICK_SERVICES 提问词，在顾问面板展示与回复。
   * @param {string} [serviceTitle] QUICK_SERVICES 中的 title
   * @param {{ userLabel?, prompt?, validate?, linkedParams? }} options
   */
  async sendLinkedQuickService(serviceTitle, options = {}) {
    if (options.validate) {
      const msg = options.validate();
      if (msg) {
        showToast(msg);
        return null;
      }
    }
    const svc = serviceTitle ? this.getQuickService(serviceTitle) : null;
    let prompt = options.prompt || (svc && (svc.promptKey ? this._resolveQuickPrompt(svc) : svc.prompt));
    if (!prompt) return null;
    const userLabel = options.userLabel || serviceTitle || prompt || 'AI辅助生成';
    return this.sendPrompt(prompt || userLabel, {
      userLabel,
      linkedParams: options.linkedParams,
      useLlm: options.useLlm,
      onComplete: options.onComplete,
    });
  },

  /**
   * 绑定页面按钮与智能顾问联动（统一入口，避免各页重复实现）。
   * 支持 buttonId 或 selector；动态列表请用 bindLinkedSelector 在渲染后调用。
   */
  bindLinkedAction(config) {
    const {
      buttonId,
      el,
      selector,
      serviceTitle,
      userLabel,
      busyLabel,
      validate,
      prompt,
      getUserLabel,
      getPrompt,
      getLinkedParams,
      onComplete,
      useLlm = false,
    } = config;

    const elements = [];
    if (el) elements.push(el);
    else if (buttonId) {
      const node = document.getElementById(buttonId);
      if (node) elements.push(node);
    } else if (selector) {
      document.querySelectorAll(selector).forEach((node) => elements.push(node));
    }

    elements.forEach((btn) => {
      if (!btn || btn.dataset.advisorLinked) return;
      btn.dataset.advisorLinked = '1';
      btn.onclick = async () => {
        btn.disabled = true;
        const label = btn.textContent;
        if (busyLabel) btn.textContent = busyLabel;
        try {
          const effectiveUserLabel = getUserLabel ? getUserLabel(btn) : userLabel;
          const effectivePrompt = getPrompt ? getPrompt(btn) : prompt;
          const linkedParams = getLinkedParams ? getLinkedParams(btn) : undefined;
          const result = await this.sendLinkedQuickService(serviceTitle, {
            userLabel: effectiveUserLabel,
            validate,
            prompt: effectivePrompt,
            linkedParams,
            useLlm,
          });
          if (onComplete && result) onComplete(result, btn);
        } finally {
          btn.disabled = false;
          btn.textContent = label;
        }
      };
    });
  },

  /** 动态渲染的按钮在插入 DOM 后调用 */
  bindLinkedSelector(selector, config) {
    this.bindLinkedAction({ ...config, selector });
  },

  bindPageLinkedActions(options = {}) {
    const {
      linkedActions = [],
      bindHealthDiagnose = true,
      bindPlanExplain = true,
      bindAssetDiagnose = false,
      planExplainEmptyMessage = '请先生成配置方案',
      assetDiagnoseEmptyMessage = '请先加载诊断数据',
    } = options;

    if (bindHealthDiagnose) {
      this.bindLinkedAction({
        buttonId: 'btnAiHealthDiagnose',
        serviceTitle: '健康度解读',
        userLabel: 'AI资配解读',
        busyLabel: '解读中…',
        useLlm: true,
      });
    }
    if (bindAssetDiagnose && document.getElementById('btnAiAssetDiagnose')) {
      this.bindLinkedAction({
        buttonId: 'btnAiAssetDiagnose',
        serviceTitle: '资产诊断解读',
        userLabel: 'AI资产诊断',
        busyLabel: '诊断中…',
        useLlm: true,
        validate: () => {
          if (typeof diagnosisData === 'undefined') return null;
          if (!diagnosisData) return assetDiagnoseEmptyMessage;
          return null;
        },
      });
    }
    if (bindPlanExplain && document.getElementById('btnAiPlanExplain')) {
      this.bindLinkedAction({
        buttonId: 'btnAiPlanExplain',
        serviceTitle: '方案解读',
        userLabel: 'AI深度解读',
        busyLabel: '解读中…',
        useLlm: true,
        validate: () => {
          if (typeof planData === 'undefined') return null;
          if (!planData) return planExplainEmptyMessage;
          return null;
        },
      });
    }
    linkedActions.forEach((cfg) => this.bindLinkedAction(cfg));
  },

  async refreshStatus() {
    try {
      const res = await apiGet('/api/ai/status');
      this._status = res.data;
      this.updateStatusBadge();
    } catch (e) {
      this._status = { configured: false, chat_enabled: true };
      this.updateStatusBadge();
    }
  },

  updateStatusBadge() {
    const el = document.getElementById('advisorChatStatus');
    if (!el || !this._status) return;
    const label = el.querySelector('.advisor-chat-status-label');
    if (this._status.configured) {
      if (label) label.textContent = `在线 · ${this._status.model || 'AI'}`;
      el.className = 'advisor-chat-status online';
      el.title = `${this._status.provider || 'LLM'} · ${this._status.base_url || ''}`;
    } else {
      if (label) label.textContent = '规则兜底 · 未配置 Key';
      el.className = 'advisor-chat-status offline';
      el.title = '请在 .env 中设置 LLM_API_KEY 后重启服务，即可启用大模型解读';
    }
  },

  _isDockedLayout() {
    return document.body.hasAttribute('data-advisor-dock');
  },

  bindUI() {
    const toggle = document.getElementById('advisorChatToggle');
    const close = document.getElementById('advisorChatClose');
    const clear = document.getElementById('advisorChatClear');
    const send = document.getElementById('advisorChatSend');
    const input = document.getElementById('advisorChatInput');
    const backdrop = document.getElementById('advisorChatBackdrop');
    const panel = document.getElementById('advisorChatPanel');
    const messages = document.getElementById('advisorChatMessages');
    const docked = this._isDockedLayout();

    if (toggle) toggle.onclick = () => this.setOpen(!this._open);
    if (close) close.onclick = () => this.setOpen(false);
    if (clear) clear.onclick = () => this.clearHistory();
    if (send) send.onclick = () => this.send();
    if (backdrop && !docked) backdrop.onclick = () => this.setOpen(false);

    if (input) {
      input.addEventListener('input', () => this._syncSendBtn());
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          this.send();
        }
      });
    }

    if (messages) {
      messages.addEventListener('click', (e) => {
        const item = e.target.closest('[data-chat-prompt]');
        if (!item) return;
        const text = item.dataset.chatPrompt || '';
        const serviceTitle = item.dataset.serviceTitle || '';
        const promptKey = item.dataset.promptKey || '';
        if (promptKey === 'full_service' || serviceTitle === '全流程服务') {
          const cid = typeof getCustomerId === 'function' ? getCustomerId() : '';
          if (!cid) {
            showToast('请先从左侧客户清单选择客户');
            return;
          }
          this.sendLinkedQuickService('全流程服务', {
            userLabel: `全流程服务·${typeof getCustomerShortName === 'function' ? getCustomerShortName(getCustomerId()) : '当前客户'}`,
            prompt: this._resolveQuickPrompt(this.getQuickService('全流程服务')),
          });
        } else if (serviceTitle) {
          this.sendLinkedQuickService(serviceTitle, { userLabel: serviceTitle, prompt: text });
        } else {
          this.sendPrompt(text);
        }
      });
      messages.addEventListener('scroll', () => this._schedulePersistScroll());
    }

    if (!this._pageLifecycleBound) {
      this._pageLifecycleBound = true;
      window.addEventListener('pagehide', () => {
        if (this._sending && this._inflight) {
          this._persistInflight({ interrupted: true });
        }
        this._persistSession();
      });
    }

    if (panel) panel.addEventListener('click', (e) => e.stopPropagation());
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this._open && !this._isDockedLayout()) this.setOpen(false);
    });
  },

  _syncSendBtn() {
    const input = document.getElementById('advisorChatInput');
    const send = document.getElementById('advisorChatSend');
    if (!send) return;
    send.disabled = !((input && input.value.trim()) && !this._sending);
  },

  setOpen(open, options = {}) {
    this._open = open;
    const panel = document.getElementById('advisorChatPanel');
    const backdrop = document.getElementById('advisorChatBackdrop');
    const fab = document.getElementById('advisorChatToggle');
    const docked = this._isDockedLayout();
    if (options.skipAnimation && panel) panel.classList.add('advisor-chat-instant');
    if (panel) panel.classList.toggle('open', open);
    if (fab) fab.classList.toggle('hidden', open);
    if (docked) {
      document.body.classList.toggle('advisor-chat-docked-open', open);
      document.body.classList.remove('advisor-chat-open');
      if (backdrop) backdrop.classList.remove('open');
    } else {
      document.body.classList.toggle('advisor-chat-open', open);
      document.body.classList.remove('advisor-chat-docked-open');
      if (backdrop) backdrop.classList.toggle('open', open);
    }
    if (!options.skipPersist) this._persistSession();
    if (open) {
      if (window.AppShell && typeof window.AppShell.collapseForAdvisor === 'function') {
        window.AppShell.collapseForAdvisor();
      }
      if (!this._welcomed) this.showWelcome();
      if (this._useAgentMode()) {
        this.maybeShowProactiveNudge();
      }
      if (!options.skipFocus) {
        const input = document.getElementById('advisorChatInput');
        if (input) setTimeout(() => input.focus(), 320);
      }
    }
    if (options.skipAnimation && panel) {
      requestAnimationFrame(() => panel.classList.remove('advisor-chat-instant'));
    }
    if (!open && window.AppShell && typeof window.AppShell.restoreAfterAdvisor === 'function') {
      window.AppShell.restoreAfterAdvisor();
    }
  },

  _nowLabel() {
    const d = new Date();
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  },

  _serviceGridHtml() {
    return this.QUICK_SERVICES.map(s => {
      const prompt = this._resolveQuickPrompt(s) || s.prompt || '';
      return `
      <button type="button" class="advisor-service-item" data-chat-prompt="${this._escapeAttr(prompt)}" data-service-title="${this._escapeAttr(s.title)}" data-prompt-key="${this._escapeAttr(s.promptKey || '')}">
        <span class="advisor-service-icon">${s.icon}</span>
        <span class="advisor-service-title">${s.title}</span>
        <span class="advisor-service-desc">${s.desc}</span>
      </button>`;
    }).join('');
  },

  showWelcome(options = {}) {
    const box = document.getElementById('advisorChatMessages');
    if (!box || this._welcomed) return;
    this._welcomed = true;
    const time = options.time || this._nowLabel();
    const wrap = document.createElement('div');
    wrap.className = 'advisor-chat-welcome';
    wrap.innerHTML = `
      <div class="advisor-chat-row advisor-chat-row-assistant">
        <div class="advisor-chat-bubble advisor-chat-bubble-assistant advisor-chat-bubble-card">
          <div class="advisor-service-card">
            <div class="advisor-service-card-head">
              <span class="advisor-service-card-brand">投顾慧选</span>
              <span class="advisor-service-card-sub">智能资配服务</span>
            </div>
            <div class="advisor-service-grid">${this._serviceGridHtml()}</div>
          </div>
        </div>
      </div>
      <div class="advisor-chat-row advisor-chat-row-assistant">
        <div class="advisor-chat-bubble advisor-chat-bubble-assistant">
          <p>${this._welcomeHintHtml()}</p>
        </div>
        <div class="advisor-chat-time">${time}</div>
      </div>`;
    box.appendChild(wrap);
    this._scrollToBottom();
    if (!options.skipPersist) {
      this._uiMessages.push({ kind: 'welcome', time });
      this._persistSession();
    }
  },

  showTyping() {
    this.hideTyping();
    const box = document.getElementById('advisorChatMessages');
    if (!box) return;
    const row = document.createElement('div');
    row.className = 'advisor-chat-row advisor-chat-row-assistant advisor-chat-typing-row';
    row.id = 'advisorChatTyping';
    row.innerHTML = `
      <div class="advisor-chat-bubble advisor-chat-bubble-assistant advisor-chat-bubble-typing">
        <div class="advisor-chat-live-thinking">
          <div class="advisor-chat-live-thinking-label">思考过程</div>
          <div class="advisor-chat-live-thinking-body" id="advisorChatLiveReasoning">
            <span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>
          </div>
        </div>
        <div class="advisor-chat-live-reply" id="advisorChatLiveReply"></div>
      </div>`;
    box.appendChild(row);
    this._scrollToBottom();
  },

  _updateLiveReasoning(text) {
    const el = document.getElementById('advisorChatLiveReasoning');
    if (!el) return;
    if (text && text.trim()) {
      el.className = 'advisor-chat-live-thinking-body has-content';
      el.innerHTML = this._formatContent(text);
    }
    this._scrollLiveToLatest();
  },

  _updateLiveReply(text) {
    const el = document.getElementById('advisorChatLiveReply');
    if (!el || !text) return;
    el.className = 'advisor-chat-live-reply has-content';
    el.innerHTML = this._formatContent(text);
    this._scrollLiveToLatest();
  },

  hideTyping() {
    const el = document.getElementById('advisorChatTyping');
    if (el) el.remove();
  },

  appendMessage(role, content, meta = {}, options = {}) {
    const box = document.getElementById('advisorChatMessages');
    if (!box) return;
    const isUser = role === 'user';
    const time = options.time || this._nowLabel();
    const row = document.createElement('div');
    row.className = `advisor-chat-row advisor-chat-row-${isUser ? 'user' : 'assistant'}`;
    if (meta.nudge) row.classList.add('advisor-chat-nudge-row');

    const sourceBadge = !isUser && meta.source
      ? `<span class="advisor-chat-source ${meta.source}">${meta.source === 'llm' ? 'AI 生成' : meta.source === 'agent' ? 'Agent 编排' : '规则兜底'}</span>`
      : '';

    const reasoningHtml = !isUser && meta.reasoning
      ? `<details class="advisor-chat-reasoning" open>
          <summary>思考过程</summary>
          <div class="advisor-chat-reasoning-body">${this._formatContent(meta.reasoning)}</div>
        </details>`
      : '';

    const actionsHtml = !isUser && meta.actions && meta.actions.length
      ? `<div class="advisor-chat-actions">${meta.actions.map((a, i) =>
          `<button type="button" class="advisor-action-btn" data-action-index="${i}">${this._escapeHtml(a.label || '执行')}</button>`
        ).join('')}</div>`
      : '';

    row.innerHTML = isUser
      ? `<div class="advisor-chat-bubble advisor-chat-bubble-user">${this._formatContent(content)}</div>`
      : `<div class="advisor-chat-bubble advisor-chat-bubble-assistant">
          ${reasoningHtml}
          ${this._formatRichContent(content)}
          ${actionsHtml}
          ${sourceBadge}
        </div>
        <div class="advisor-chat-time">${time}</div>`;

    if (!isUser && meta.actions && meta.actions.length) {
      row.querySelectorAll('[data-action-index]').forEach(btn => {
        btn.onclick = () => {
          const idx = Number(btn.getAttribute('data-action-index'));
          this._handleAction(meta.actions[idx], btn);
        };
      });
    }
    box.appendChild(row);
    if (!options.skipPersist) this._scrollToBottom();
    else if (typeof options.scrollTop === 'number') {
      box.scrollTop = options.scrollTop;
    }
    if (!options.skipPersist) {
      this._uiMessages.push({
        role,
        content,
        time,
        meta: {
          source: meta.source || '',
          reasoning: meta.reasoning || '',
          actions: meta.actions || [],
        },
      });
      this._persistSession();
    }
  },

  _formatContent(text) {
    const escaped = this._escapeHtml(text);
    return escaped
      .replace(/\n{2,}/g, '</p><p>')
      .replace(/\n/g, '<br>')
      .replace(/^/, '<p>')
      .replace(/$/, '</p>')
      .replace(/<p><\/p>/g, '');
  },

  _formatRichContent(text) {
    const allowed = this._escapeHtml(text)
      .replace(/&lt;strong&gt;/g, '<strong>')
      .replace(/&lt;\/strong&gt;/g, '</strong>');
    return allowed
      .replace(/\n{2,}/g, '</p><p>')
      .replace(/\n/g, '<br>')
      .replace(/^/, '<p>')
      .replace(/$/, '</p>')
      .replace(/<p><\/p>/g, '');
  },

  _scrollElementToBottom(el) {
    if (!el) return;
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  },

  _scrollToBottom() {
    const box = document.getElementById('advisorChatMessages');
    this._scrollElementToBottom(box);
  },

  _scrollLiveToLatest() {
    const reasoning = document.getElementById('advisorChatLiveReasoning');
    const reply = document.getElementById('advisorChatLiveReply');
    this._scrollElementToBottom(reasoning);
    this._scrollElementToBottom(reply);
    this._scrollToBottom();
  },

  _escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
  },

  _escapeAttr(text) {
    return this._escapeHtml(text).replace(/"/g, '&quot;');
  },

  getContextPayload() {
    let overview = typeof overviewData !== 'undefined' ? overviewData : null;
    let plan = typeof planData !== 'undefined' ? planData : null;
    let diagnosis = typeof diagnosisData !== 'undefined' ? diagnosisData : null;
    if (this._preloaded) {
      if (!diagnosis && this._preloaded.diagnosis) diagnosis = this._preloaded.diagnosis;
      if (!overview && this._preloaded.overview) overview = this._preloaded.overview;
    }
    if (!plan && typeof loadResult === 'function') {
      plan = loadResult();
    }
    return { overview, plan, diagnosis };
  },

  async sendPrompt(message, options = {}) {
    if (this._sending) return null;
    const linkedParams = options.linkedParams || {};
    const text = (message || '').trim();
    if (!text) return null;

    const cid = getCustomerId();
    if (!cid) {
      const hub = typeof isCustomerHubPage === 'function' && isCustomerHubPage();
      showToast(hub ? '请先从左侧客户清单选择客户' : '请先选择客户');
      return null;
    }

    const userLabel = options.userLabel || text || 'AI辅助生成';
    const historyText = text || userLabel;
    const historyBefore = [...this._history];

    this._sending = true;
    this._syncSendBtn();
    this._beginInflight({ message: historyText, userLabel, historyBefore, linkedParams, useLlm: options.useLlm });

    const input = document.getElementById('advisorChatInput');
    if (input) input.value = '';
    this.setOpen(true);
    this.appendMessage('user', userLabel);
    this.showTyping();

    return this._completeInflightTurn({ onComplete: options.onComplete });
  },

  async send() {
    const input = document.getElementById('advisorChatInput');
    const message = (input && input.value || '').trim();
    if (!message) return;
    await this.sendPrompt(message);
  },

  _appendAssistantFromAgentResult(message, result) {
    const reply = (result && result.reply) || '';
    const reasoning = ((result && result.reasoning) || '').trim();
    this._history.push({ role: 'user', content: message });
    this._history.push({ role: 'assistant', content: reply });
    if (this._history.length > 12) this._history = this._history.slice(-12);

    if (result.customer_id && typeof setSelectedCustomerId === 'function') {
      setSelectedCustomerId(result.customer_id);
    }
    if (result.journey) this._applyJourney(result.journey);
    if (result.tool_results) {
      const dx = result.tool_results.find(t => t.diagnosis);
      if (dx && dx.diagnosis && typeof diagnosisData !== 'undefined') {
        diagnosisData = dx.diagnosis;
      }
    }

    if (!reply.trim()) {
      this.appendMessage('assistant', '顾问未返回内容，请重试。', { source: 'agent' });
      return;
    }
    this.appendMessage('assistant', reply, {
      source: result.source || 'agent',
      reasoning,
      actions: result.actions || [],
    });
  },

  async _handleAction(action, btn) {
    if (!action) return;
    const label = btn && btn.textContent;
    if (btn) {
      btn.disabled = true;
      if (action.confirm !== false) btn.textContent = '处理中…';
    }
    try {
      if (action.type === 'navigate') {
        if (action.step && typeof JourneyState !== 'undefined') {
          const cid = getCustomerId();
          if (cid) JourneyState.markStep(cid, action.step);
        }
        if (action.plan) {
          this._applyPlanToSession(action.plan);
        }
        this._navigateTo(action.href, {
          openPlan: /smart_allocation\.html/.test(action.href || ''),
        });
        return;
      }
      if (action.type === 'set_customer') {
        if (action.customer_id && typeof navigateWithCustomer === 'function') {
          navigateWithCustomer('asset_diagnosis.html', action.customer_id);
          return;
        }
        if (typeof setSelectedCustomerId === 'function') {
          setSelectedCustomerId(action.customer_id);
        }
        await this.reloadForCustomer();
        return;
      }
      if (action.type === 'tool') {
        if (action.confirm) {
          const ok = window.confirm(action.confirm_text || `确认执行：${action.label}？`);
          if (!ok) return;
        }
        await this._executeToolAction(action);
        return;
      }
      if (action.type === 'agent_prompt') {
        if (action.customer_id && typeof setSelectedCustomerId === 'function') {
          setSelectedCustomerId(action.customer_id);
          if (typeof syncCustomerSelectTo === 'function') syncCustomerSelectTo(action.customer_id);
        }
        await this.sendPrompt(action.prompt || action.label, {
          userLabel: action.label || action.prompt,
        });
        return;
      }
      if (action.type === 'copy') {
        const text = action.text || '';
        if (text && navigator.clipboard) {
          await navigator.clipboard.writeText(text);
          showToast('已复制到剪贴板');
        }
        return;
      }
      if (action.type === 'view_plan' || action.type === 'apply_plan') {
        if (action.plan) this._applyPlanToSession(action.plan);
        showToast('已打开智能资配工作台');
        this._navigateTo('smart_allocation.html', { openPlan: true });
        return;
      }
    } finally {
      if (btn) {
        btn.disabled = false;
        if (label) btn.textContent = label;
      }
    }
  },

  _isCompletePlanPayload(payload) {
    const rb = payload?.rebalance || payload;
    if (!rb?.category_summary?.length) return false;
    const deltas = rb.product_deltas || [];
    if (!deltas.length) return false;
    if (typeof PlanEditor !== 'undefined' && typeof PlanEditor.isCompletePlanCache === 'function') {
      return PlanEditor.isCompletePlanCache({ rebalance: rb });
    }
    return deltas.some((d) => d.category != null && d.current_amount != null);
  },

  _applyPlanToSession(plan) {
    if (!plan) return;
    const payload = {
      rebalance: plan.rebalance || plan,
      explanation: plan.explanation || {},
    };
    const existing = typeof loadResult === 'function' ? loadResult() : null;
    if (
      existing?.rebalance
      && this._isCompletePlanPayload(existing)
      && !this._isCompletePlanPayload(payload)
    ) {
      return;
    }
    if (typeof saveResult === 'function') {
      saveResult(payload);
    } else {
      sessionStorage.setItem('rebalanceResult', JSON.stringify(payload));
    }
    if (typeof planData !== 'undefined') {
      planData = payload;
    }
  },

  async _executeToolAction(action) {
    const cid = getCustomerId();
    if (!cid) {
      showToast('请先选择客户');
      return;
    }
    this.showTyping();
    try {
      const res = await apiPost('/api/ai/agent/tool', {
        customer_id: cid,
        tool: action.tool,
        params: action.params || {},
      });
      const data = res.data || {};
      const tr = data.tool_result || {};
      this.hideTyping();
      if (!tr.ok) {
        this.appendMessage('assistant', `执行失败：${tr.error || '未知错误'}`, { source: 'agent' });
        return;
      }
      let summary = '';
      if (action.tool === 'generate_sop_content' && tr.ok) {
        if (tr.batch) {
          summary = (
            `批量生成完成：成功 ${tr.processed || 0} 条，失败 ${tr.failed || 0} 条。` +
            (tr.remaining_pending ? ` 仍有 ${tr.remaining_pending} 条待处理。` : '')
          );
        } else {
          const out = tr.output || {};
          const script = out.client_script || '';
          summary = `话术包已生成（${out.source || 'rule_template'}）。\n\n${(script || out.event_description || '').slice(0, 280)}`;
          if (script) {
            data.actions = (data.actions || []).concat([{
              type: 'copy',
              label: '复制对客话术',
              text: script,
            }]);
          }
        }
      } else if (action.tool === 'run_rebalance' && tr.ok) {
        const mode = (action.params && action.params.mode) || tr.mode || 'smart_one_click';
        const full = await apiPost('/api/allocation/auto_rebalance', {
          customer_id: cid,
          mode,
          product_category: '投资规划',
        });
        this._applyPlanToSession(full.data);
        const rb = full.data.rebalance || {};
        summary = (
          `配仓方案已生成（${tr.mode_label || mode}）。\n\n` +
          `总资产 ${Number(rb.total_assets || 0).toLocaleString()} 元。\n` +
          (rb.validation_notes || []).slice(0, 3).map(n => `· ${n}`).join('\n')
        );
        const cid2 = getCustomerId();
        if (cid2 && typeof JourneyState !== 'undefined') {
          JourneyState.markStep(cid2, 'allocation_work');
          this.renderJourneyProgress(JourneyState.get(cid2));
        }

        const currentPage = location.pathname.split('/').pop() || '';
        if (currentPage === 'smart_allocation.html') {
          if (typeof refreshPlanView === 'function') {
            refreshPlanView(full.data);
            const planSection = document.getElementById('planSection');
            const globalActions = document.getElementById('globalActions');
            if (planSection) planSection.style.display = 'block';
            if (globalActions) globalActions.style.display = 'none';
          } else if (typeof planData !== 'undefined') {
            planData = full.data;
            location.reload();
          }
        }
      } else {
        summary = `工具 ${action.tool} 执行完成。`;
      }
      this.appendMessage('assistant', summary, {
        source: 'agent',
        actions: data.actions || [],
      });
    } catch (e) {
      this.hideTyping();
      this.appendMessage('assistant', '工具执行失败：' + e.message, { source: 'agent' });
    }
  },

  async _fetchAgent(message, cid, overview, plan, diagnosis, history) {
    const agentPayload = this.getAgentPayload();
    const res = await apiPost('/api/ai/agent', {
      customer_id: cid,
      message,
      history,
      overview: overview || agentPayload.overview,
      plan: plan || agentPayload.plan,
      diagnosis: diagnosis || agentPayload.diagnosis,
      journey: agentPayload.journey,
      page: agentPayload.page,
    });
    const data = res.data || {};
    return {
      agent: true,
      reply: data.reply || '',
      reasoning: data.reasoning || '',
      source: data.source || 'agent',
      actions: data.actions || [],
      journey: data.journey,
      customer_id: data.customer_id,
      tool_results: data.tool_results,
    };
  },

  _appendAssistantFromResult(message, result) {
    const reply = (result && result.reply) || '';
    const reasoning = ((result && result.reasoning) || '').trim();
    this._history.push({ role: 'user', content: message });
    this._history.push({ role: 'assistant', content: reply });
    if (this._history.length > 12) this._history = this._history.slice(-12);

    if (!reply.trim()) {
      this.appendMessage(
        'assistant',
        '大模型返回为空，请稍后重试或检查 config/llm_config.yaml 中的 model 配置。',
        { source: 'fallback' }
      );
      return;
    }
    this.appendMessage('assistant', reply, {
      source: result.source,
      reasoning,
    });
  },

  async _fetchStream(message, cid, overview, plan, diagnosis, history, hooks = {}) {
    this._abortController = new AbortController();

    const res = await fetch('/api/ai/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: this._abortController ? this._abortController.signal : undefined,
      body: JSON.stringify({
        customer_id: cid,
        message,
        history,
        overview,
        plan,
        diagnosis,
      }),
    });
    if (!res.ok || !res.body) return null;

    let reasoning = '';
    let content = '';
    let donePayload = null;

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        let payload;
        try {
          payload = JSON.parse(line.slice(6));
        } catch (err) {
          continue;
        }
        if (payload.type === 'reasoning' && payload.delta) {
          reasoning += payload.delta;
          if (hooks.onReasoning) hooks.onReasoning(reasoning);
        } else if (payload.type === 'content' && payload.delta) {
          content += payload.delta;
          if (hooks.onContent) hooks.onContent(content);
        } else if (payload.type === 'done') {
          donePayload = payload;
        } else if (payload.type === 'error') {
          throw new Error(payload.message || '流式请求失败');
        }
      }
    }

    if (!donePayload) return null;

    return {
      reply: donePayload.reply || content || '',
      reasoning: (donePayload.reasoning || reasoning || '').trim(),
      source: donePayload.source,
      model: donePayload.model,
      usage: donePayload.usage,
    };
  },

  async _fetchFallback(message, cid, overview, plan, diagnosis, history, linkedParams = {}) {
    const res = await apiPost('/api/ai/chat', {
      customer_id: cid,
      message,
      history,
      overview,
      plan,
      diagnosis,
    });
    const data = res.data;
    return {
      reply: data.reply || '',
      reasoning: (data.reasoning || '').trim(),
      source: data.source,
    };
  },

  clearHistory() {
    if (this._abortController) this._abortController.abort();
    this._clearInflight();
    this._sending = false;
    this._history = [];
    this._uiMessages = [];
    this._welcomed = false;
    const box = document.getElementById('advisorChatMessages');
    if (box) box.innerHTML = '';
    this.hideTyping();
    this._persistSession();
    this.showWelcome();
    this._syncSendBtn();
    showToast('对话已清空');
  },
};
