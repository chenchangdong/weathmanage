/** 财富旅程页 — 首屏前恢复顾问侧栏开合，避免跳转后闪烁/重动画 */
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
    const cid = params.get('customer_id')
      || sessionStorage.getItem('selectedCustomerId')
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
    }
  } catch (e) {
    /* ignore */
  }
})();
