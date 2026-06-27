/** 财富旅程页 — 首屏前恢复顾问侧栏布局，减少整页刷新时的闪烁 */
(function () {
  const OPEN_KEY = 'advisorChatOpen';
  const PREFIX = 'advisorChatSession:';
  const DOCK_PAGES = [
    'wealth_inventory.html',
    'asset_diagnosis.html',
    'smart_allocation_setup.html',
    'smart_allocation.html',
  ];

  const path = location.pathname.split('/').pop() || '';
  if (!DOCK_PAGES.includes(path)) return;

  try {
    const params = new URLSearchParams(location.search);
    const hub = path === 'wealth_inventory.html';
    const cid = params.get('customer_id')
      || (hub ? '_none' : sessionStorage.getItem('selectedCustomerId'))
      || '_none';
    let open = sessionStorage.getItem(OPEN_KEY) !== '0';
    const raw = sessionStorage.getItem(`${PREFIX}${cid}`);
    if (raw) {
      const data = JSON.parse(raw);
      if (data.open === false) open = false;
      else if (data.open === true) open = true;
    }
    if (open) {
      document.documentElement.classList.add('advisor-chat-pending-open');
      try {
        document.documentElement.style.setProperty('--advisor-panel-width', '380px');
      } catch (e) { /* ignore */ }
    }
  } catch (e) {
    /* ignore */
  }
})();
