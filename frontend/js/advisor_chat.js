/** AI 顾问对话 — 招行小招式气泡交互 */

const AdvisorChat = {
  _open: false,
  _history: [],
  _status: null,
  _sending: false,
  _welcomed: false,

  QUICK_SERVICES: [
    {
      icon: '💚',
      title: '健康度解读',
      desc: '财富健康分析',
      prompt: '请解读该客户财富健康度，先给结论，再用 3~4 条要点说明优先处理建议',
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

  async init() {
    await this.refreshStatus();
    this.bindUI();
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
    } else {
      if (label) label.textContent = '规则兜底模式';
      el.className = 'advisor-chat-status offline';
    }
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

    if (toggle) toggle.onclick = () => this.setOpen(!this._open);
    if (close) close.onclick = () => this.setOpen(false);
    if (clear) clear.onclick = () => this.clearHistory();
    if (send) send.onclick = () => this.send();
    if (backdrop) backdrop.onclick = () => this.setOpen(false);

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
        if (input) input.value = text;
        this._syncSendBtn();
        this.send();
      });
    }

    if (panel) panel.addEventListener('click', (e) => e.stopPropagation());
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this._open) this.setOpen(false);
    });
  },

  _syncSendBtn() {
    const input = document.getElementById('advisorChatInput');
    const send = document.getElementById('advisorChatSend');
    if (!send) return;
    send.disabled = !((input && input.value.trim()) && !this._sending);
  },

  setOpen(open) {
    this._open = open;
    const panel = document.getElementById('advisorChatPanel');
    const backdrop = document.getElementById('advisorChatBackdrop');
    const fab = document.getElementById('advisorChatToggle');
    if (panel) panel.classList.toggle('open', open);
    if (backdrop) backdrop.classList.toggle('open', open);
    if (fab) fab.classList.toggle('hidden', open);
    document.body.classList.toggle('advisor-chat-open', open);
    if (open) {
      if (!this._welcomed) this.showWelcome();
      const input = document.getElementById('advisorChatInput');
      if (input) setTimeout(() => input.focus(), 320);
    }
  },

  _nowLabel() {
    const d = new Date();
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  },

  _serviceGridHtml() {
    return this.QUICK_SERVICES.map(s => `
      <button type="button" class="advisor-service-item" data-chat-prompt="${this._escapeAttr(s.prompt)}">
        <span class="advisor-service-icon">${s.icon}</span>
        <span class="advisor-service-title">${s.title}</span>
        <span class="advisor-service-desc">${s.desc}</span>
      </button>`).join('');
  },

  showWelcome() {
    const box = document.getElementById('advisorChatMessages');
    if (!box || this._welcomed) return;
    this._welcomed = true;
    const time = this._nowLabel();
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
          <p>您好，我是您的<strong>智能投顾顾问</strong>。我已读取当前客户的资产检视与配置方案，可为您解答健康度、调仓逻辑与合规替代思路等问题。</p>
        </div>
        <div class="advisor-chat-time">${time}</div>
      </div>`;
    box.appendChild(wrap);
    this._scrollToBottom();
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

  appendMessage(role, content, meta = {}) {
    const box = document.getElementById('advisorChatMessages');
    if (!box) return;
    const isUser = role === 'user';
    const time = this._nowLabel();
    const row = document.createElement('div');
    row.className = `advisor-chat-row advisor-chat-row-${isUser ? 'user' : 'assistant'}`;

    const sourceBadge = !isUser && meta.source
      ? `<span class="advisor-chat-source ${meta.source}">${meta.source === 'llm' ? 'AI 生成' : '规则兜底'}</span>`
      : '';

    const reasoningHtml = !isUser && meta.reasoning
      ? `<details class="advisor-chat-reasoning" open>
          <summary>思考过程</summary>
          <div class="advisor-chat-reasoning-body">${this._formatContent(meta.reasoning)}</div>
        </details>`
      : '';

    row.innerHTML = isUser
      ? `<div class="advisor-chat-bubble advisor-chat-bubble-user">${this._formatContent(content)}</div>`
      : `<div class="advisor-chat-bubble advisor-chat-bubble-assistant">
          ${reasoningHtml}
          ${this._formatContent(content)}
          ${sourceBadge}
        </div>
        <div class="advisor-chat-time">${time}</div>`;
    box.appendChild(row);
    this._scrollToBottom();
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
    const overview = typeof overviewData !== 'undefined' ? overviewData : null;
    const plan = typeof planData !== 'undefined' ? planData : null;
    return { overview, plan };
  },

  async send() {
    if (this._sending) return;
    const input = document.getElementById('advisorChatInput');
    const message = (input && input.value || '').trim();
    if (!message) return;

    const cid = getCustomerId();
    if (!cid) {
      showToast('请先选择客户');
      return;
    }

    this._sending = true;
    this._syncSendBtn();
    this.appendMessage('user', message);
    if (input) input.value = '';
    this.setOpen(true);
    this.showTyping();

    const { overview, plan } = this.getContextPayload();
    try {
      const streamed = await this._sendStream(message, cid, overview, plan);
      if (!streamed) {
        await this._sendFallback(message, cid, overview, plan);
      }
    } catch (e) {
      this.hideTyping();
      this.appendMessage(
        'assistant',
        '请求失败：' + e.message + '。推理模型可能需要 30–60 秒，请确认服务未超时。',
        { source: 'fallback' }
      );
    } finally {
      this._sending = false;
      this._syncSendBtn();
    }
  },

  async _sendStream(message, cid, overview, plan) {
    const res = await fetch('/api/ai/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        customer_id: cid,
        message,
        history: this._history,
        overview,
        plan,
      }),
    });
    if (!res.ok || !res.body) return false;

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
          this._updateLiveReasoning(reasoning);
        } else if (payload.type === 'content' && payload.delta) {
          content += payload.delta;
          this._updateLiveReply(content);
        } else if (payload.type === 'done') {
          donePayload = payload;
        } else if (payload.type === 'error') {
          throw new Error(payload.message || '流式请求失败');
        }
      }
    }

    this.hideTyping();
    if (!donePayload) return false;

    const reply = donePayload.reply || content || '';
    const finalReasoning = (donePayload.reasoning || reasoning || '').trim();
    this._history.push({ role: 'user', content: message });
    this._history.push({ role: 'assistant', content: reply });
    if (this._history.length > 12) this._history = this._history.slice(-12);

    if (!reply.trim()) {
      this.appendMessage(
        'assistant',
        '大模型返回为空，请稍后重试或检查 config/llm_config.yaml 中的 model 配置。',
        { source: 'fallback' }
      );
      return true;
    }

    this.appendMessage('assistant', reply, {
      source: donePayload.source,
      reasoning: finalReasoning,
    });
    return true;
  },

  async _sendFallback(message, cid, overview, plan) {
    const res = await apiPost('/api/ai/chat', {
      customer_id: cid,
      message,
      history: this._history,
      overview,
      plan,
    });
    this.hideTyping();
    const data = res.data;
    const reply = data.reply || '';
    this._history.push({ role: 'user', content: message });
    this._history.push({ role: 'assistant', content: reply });
    if (this._history.length > 12) this._history = this._history.slice(-12);
    if (!reply.trim()) {
      this.appendMessage(
        'assistant',
        '大模型返回为空，请稍后重试或检查 config/llm_config.yaml 中的 model 配置。',
        { source: 'fallback' }
      );
    } else {
      this.appendMessage('assistant', reply, {
        source: data.source,
        reasoning: data.reasoning || '',
      });
    }
  },

  clearHistory() {
    this._history = [];
    this._welcomed = false;
    const box = document.getElementById('advisorChatMessages');
    if (box) box.innerHTML = '';
    this.showWelcome();
    showToast('对话已清空');
  },
};
