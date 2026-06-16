/** 智能资配 — 追加持仓（配置页录入，配仓页从 session 读取） */

const ADDON_WAN_FACTOR = 10000;

function addonStorageKey() {
  return `smartAllocation_addon_${getCustomerId()}_${getProductCategory()}`;
}

function addonEnabledStorageKey() {
  return `smartAllocation_addon_enabled_${getCustomerId()}_${getProductCategory()}`;
}

function yuanToWan(yuan) {
  const wan = Number(yuan) / ADDON_WAN_FACTOR;
  if (!Number.isFinite(wan)) return '0';
  return String(parseFloat(wan.toFixed(4)));
}

/** 差额（元）→ 输入框默认值（万，两位小数，向上取整至 0.01 万以免一次追加不足） */
function yuanToWanInputDefault(yuan) {
  const y = Math.max(0, Number(yuan) || 0);
  if (y < 0.01) return '0';
  const wanCeil = Math.ceil(y / 100) / 100;
  return wanCeil.toFixed(2);
}

function parseAddonInput(raw) {
  const trimmed = String(raw ?? '').trim();
  if (trimmed === '') return { ok: true, value: 0 };
  if (!/^-?\d+(\.\d+)?$/.test(trimmed)) return { ok: false, value: null };
  const wan = parseFloat(trimmed);
  if (!Number.isFinite(wan)) return { ok: false, value: null };
  return { ok: true, value: wan * ADDON_WAN_FACTOR };
}

function isAddonEnabled() {
  const toggle = document.getElementById('addonHoldingSwitch');
  if (toggle) return toggle.checked;
  return sessionStorage.getItem(addonEnabledStorageKey()) === '1';
}

function getCommittedAddonIdleCash() {
  if (!isAddonEnabled()) return 0;
  const stored = sessionStorage.getItem(addonStorageKey());
  if (stored == null || stored === '') return 0;
  const yuan = parseFloat(stored);
  return Number.isFinite(yuan) ? yuan : 0;
}

function setAddonInputError(show) {
  const input = document.getElementById('addonHoldingInput');
  const err = document.getElementById('addonHoldingError');
  if (input) input.classList.toggle('invalid', show);
  if (err) err.style.display = show ? 'inline' : 'none';
}

function setAddonInputVisible(visible) {
  const wrap = document.getElementById('addonHoldingInputWrap');
  if (wrap) {
    wrap.hidden = !visible;
    wrap.style.display = visible ? 'inline-flex' : 'none';
  }
  if (!visible) setAddonInputError(false);
}

function saveAddonToStorage(value) {
  sessionStorage.setItem(addonStorageKey(), String(value));
}

/** 方案页追加追加持仓后写入 session（与配置页口径一致） */
function commitAddonIdleCash(yuan) {
  const amount = Math.max(0, Number(yuan) || 0);
  saveAddonEnabledToStorage(amount > 0.01);
  saveAddonToStorage(amount);
  return amount;
}

function saveAddonEnabledToStorage(enabled) {
  sessionStorage.setItem(addonEnabledStorageKey(), enabled ? '1' : '0');
}

function loadAddonFromStorage() {
  let enabled = sessionStorage.getItem(addonEnabledStorageKey()) === '1';
  const stored = sessionStorage.getItem(addonStorageKey());
  let value = 0;
  if (stored != null && stored !== '') {
    const yuan = parseFloat(stored);
    value = Number.isFinite(yuan) ? yuan : 0;
  }
  if (!enabled && Math.abs(value) > 0.01) enabled = true;

  const toggle = document.getElementById('addonHoldingSwitch');
  if (toggle) toggle.checked = enabled;
  setAddonInputVisible(enabled);

  const input = document.getElementById('addonHoldingInput');
  if (input) input.value = yuanToWan(value);
  setAddonInputError(false);
  return enabled ? value : 0;
}

function applyAddonHoldingInput() {
  if (!document.getElementById('addonHoldingInput')) return true;
  if (!isAddonEnabled()) {
    saveAddonToStorage(getCommittedAddonIdleCash());
    return true;
  }
  const input = document.getElementById('addonHoldingInput');
  const parsed = parseAddonInput(input.value);
  if (!parsed.ok) {
    setAddonInputError(true);
    showToast('追加持仓请输入有效数值（单位：万，可为 0 或负数）');
    input.value = yuanToWan(getCommittedAddonIdleCash());
    return false;
  }
  setAddonInputError(false);
  input.value = yuanToWan(parsed.value);
  saveAddonToStorage(parsed.value);
  return true;
}

function onAddonToggleChange() {
  const enabled = isAddonEnabled();
  saveAddonEnabledToStorage(enabled);
  setAddonInputVisible(enabled);
  if (!enabled) return;
  applyAddonHoldingInput();
}

function bindAddonHoldingInput() {
  const toggle = document.getElementById('addonHoldingSwitch');
  if (toggle && !toggle.dataset.bound) {
    toggle.dataset.bound = '1';
    toggle.addEventListener('change', onAddonToggleChange);
  }
  const input = document.getElementById('addonHoldingInput');
  if (!input || input.dataset.bound) return;
  input.dataset.bound = '1';
  input.addEventListener('change', () => { applyAddonHoldingInput(); });
  input.addEventListener('blur', () => { applyAddonHoldingInput(); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      input.blur();
    }
  });
}
