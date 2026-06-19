/**
 * App shell — 智能资配系统（固定皓月白主题 + 可收起侧栏）
 * Usage: initAppShell({ page: 'wealth_inventory', title: '财富盘点', crumb: '财富盘点' })
 */
(function () {
  'use strict';

  const SYSTEM_NAME = '智能资配系统';
  const SIDEBAR_KEY = 'ias-sidebar-collapsed';
  const USER_NAME = 'noodles';

  const NAV_SECTIONS = [
    {
      divider: '核心业务',
      items: [
        { id: 'wealth_inventory', label: '财富盘点', href: 'wealth_inventory.html', leaf: true },
        { id: 'asset_diagnosis', label: '资产诊断', href: 'asset_diagnosis.html', leaf: true },
        { id: 'smart_allocation_setup', label: '智能资配', href: 'smart_allocation_setup.html', leaf: true },
        { id: 'sop_agent', label: 'SOP投后智能体', href: 'sop_agent.html', leaf: true },
      ],
    },
    {
      divider: '平台能力',
      items: [
        {
          id: 'ops',
          label: '运营管理',
          items: [
            { id: 'rule_strategy', label: '规则策略', href: 'admin/rule_strategy.html' },
            { id: 'sop_product_library', label: 'SOP产品信息库', href: 'admin/sop_product_library.html' },
            { id: 'data_dict', label: '数据字典', href: 'admin/data_dict.html' },
            { id: 'model_config', label: '模型建立', href: 'admin/model_config.html' },
            { id: 'portfolio_mapping', label: '模型指派', href: 'admin/portfolio_mapping.html' },
          ],
        },
      ],
    },
  ];

  const SMART_ALLOC_PAGES = new Set(['smart_allocation', 'smart_allocation_setup', 'smart_allocation.html']);

  const PAGE_ALIASES = {
    operation_rule: 'rule_strategy',
    sop_product: 'sop_product_library',
  };

  let _collapsed = false;
  let _collapsedBeforeAdvisor = null;

  function normalizePage(page) {
    return PAGE_ALIASES[page] || page;
  }

  function getAppEl() {
    return document.querySelector('.app.app-shell') || document.querySelector('.app');
  }

  function isCollapsed() {
    return _collapsed;
  }

  function setSidebarCollapsed(collapsed, options) {
    const opts = options || {};
    _collapsed = !!collapsed;
    const app = getAppEl();
    if (app) {
      app.classList.toggle('sidebar-collapsed', _collapsed);
    }
    if (!opts.skipPersist && !opts.temporary) {
      localStorage.setItem(SIDEBAR_KEY, _collapsed ? '1' : '0');
    }
    document.querySelectorAll('.sidebar-collapse-btn').forEach((btn) => {
      btn.setAttribute('aria-expanded', _collapsed ? 'false' : 'true');
      btn.title = _collapsed ? '展开菜单' : '收起菜单';
    });
  }

  function toggleSidebar() {
    setSidebarCollapsed(!_collapsed);
  }

  /** 智能顾问打开时调用：暂存状态并收起侧栏 */
  function collapseForAdvisor() {
    if (_collapsedBeforeAdvisor === null) {
      _collapsedBeforeAdvisor = _collapsed;
    }
    setSidebarCollapsed(true, { temporary: true });
  }

  /** 智能顾问关闭时恢复打开前的侧栏状态 */
  function restoreAfterAdvisor() {
    if (_collapsedBeforeAdvisor === null) return;
    setSidebarCollapsed(_collapsedBeforeAdvisor, { temporary: true });
    localStorage.setItem(SIDEBAR_KEY, _collapsedBeforeAdvisor ? '1' : '0');
    _collapsedBeforeAdvisor = null;
  }

  function resolveHref(href, admin) {
    if (admin) {
      if (href.startsWith('admin/')) return href.slice(6);
      return '../' + href;
    }
    return href;
  }

  function isPageActive(page, itemId, href) {
    if (!page) return false;
    const norm = normalizePage(page);
    if (norm === itemId || page === itemId) return true;
    if (itemId === 'smart_allocation_setup' && SMART_ALLOC_PAGES.has(page)) return true;
    const base = href.replace(/^admin\//, '').replace('.html', '');
    return page === base || page.replace('.html', '') === base;
  }

  function groupHasActive(page, group) {
    return (group.items || []).some((item) => isPageActive(page, item.id, item.href));
  }

  function sectionHasActive(page, section) {
    return section.items.some((item) => item.leaf
      ? isPageActive(page, item.id, item.href)
      : groupHasActive(page, item));
  }

  function buildSidebar(page, admin) {
    const aside = document.createElement('aside');
    aside.className = 'sidebar';

    const brand = document.createElement('div');
    brand.className = 'sidebar-brand';

    brand.innerHTML =
      '<button type="button" class="sidebar-collapse-btn" aria-label="收起菜单" title="收起菜单">&#9776;</button>' +
      '<div class="sidebar-brand-mark"></div>' +
      '<div class="sidebar-brand-copy"><div class="sidebar-brand-title"></div></div>';
    brand.querySelector('.sidebar-brand-title').textContent = SYSTEM_NAME;
    brand.querySelector('.sidebar-collapse-btn').addEventListener('click', (e) => {
      e.stopPropagation();
      toggleSidebar();
    });

    const nav = document.createElement('nav');
    nav.className = 'sidebar-nav';

    NAV_SECTIONS.forEach((section) => {
      const divider = document.createElement('div');
      divider.className = 'nav-divider';
      divider.textContent = section.divider;
      nav.appendChild(divider);

      section.items.forEach((item) => {
        if (item.leaf) {
          nav.appendChild(buildLeaf(item, page, admin));
          return;
        }

        const open = groupHasActive(page, item) || sectionHasActive(page, section);
        const group = document.createElement('div');
        group.className = 'nav-group';

        const label = document.createElement('div');
        label.className = 'nav-group-label' + (open ? ' open' : '') + (groupHasActive(page, item) ? ' is-active' : '');
        label.innerHTML =
          '<span style="display:flex;align-items:center;flex:1;min-width:0">' +
          esc(item.label) +
          '</span><span class="chev">▶</span>';

        const itemsWrap = document.createElement('div');
        itemsWrap.className = 'nav-items';
        if (!open) itemsWrap.hidden = true;

        (item.items || []).forEach((child) => {
          const link = document.createElement('a');
          link.className = 'nav-item' + (isPageActive(page, child.id, child.href) ? ' active' : '');
          link.href = resolveHref(child.href, admin);
          link.textContent = child.label;
          itemsWrap.appendChild(link);
        });

        label.addEventListener('click', () => {
          const isOpen = label.classList.toggle('open');
          itemsWrap.hidden = !isOpen;
        });

        group.appendChild(label);
        group.appendChild(itemsWrap);
        nav.appendChild(group);
      });
    });

    aside.appendChild(brand);
    aside.appendChild(nav);
    return aside;
  }

  function buildSidebarExpandBtn() {
    const expandBtn = document.createElement('button');
    expandBtn.type = 'button';
    expandBtn.className = 'sidebar-expand-btn';
    expandBtn.setAttribute('aria-label', '展开菜单');
    expandBtn.title = '展开菜单';
    expandBtn.innerHTML = '&#9654;';
    expandBtn.addEventListener('click', () => setSidebarCollapsed(false));
    return expandBtn;
  }

  function buildLeaf(item, page, admin) {
    const link = document.createElement('a');
    link.className = 'nav-leaf' + (isPageActive(page, item.id, item.href) ? ' active' : '');
    link.href = resolveHref(item.href, admin);
    link.textContent = item.label;
    return link;
  }

  function buildTopbar(title, crumb) {
    const header = document.createElement('header');
    header.className = 'topbar';

    const left = document.createElement('div');
    left.className = 'topbar-left';
    left.innerHTML =
      '<div class="crumbs">' +
      '<span>首页</span><span class="sep">/</span>' +
      '<span style="color:var(--fg-3)"></span>' +
      '</div>' +
      '<div class="page-title">' +
      esc(title) +
      '<span class="tag">实时</span>' +
      '</div>';
    left.querySelector('.crumbs span:last-child').textContent = crumb || title;

    const right = document.createElement('div');
    right.className = 'topbar-right';

    const searchWrap = document.createElement('div');
    searchWrap.className = 'search-wrap';
    const search = document.createElement('input');
    search.className = 'search-box';
    search.type = 'search';
    search.placeholder = '搜索客户、产品、方案…';
    search.autocomplete = 'off';
    searchWrap.appendChild(search);
    right.appendChild(searchWrap);

    const userChip = document.createElement('div');
    userChip.className = 'user-chip';
    const initial = USER_NAME.charAt(0).toUpperCase();
    userChip.innerHTML = '<span class="user-avatar">' + esc(initial) + '</span><span>' + esc(USER_NAME) + '</span>';
    right.appendChild(userChip);

    header.appendChild(left);
    header.appendChild(right);
    return header;
  }

  function collectBodyContent() {
    const fragment = document.createDocumentFragment();
    const nodes = Array.from(document.body.childNodes);
    nodes.forEach((node) => {
      if (node.nodeType === Node.ELEMENT_NODE && node.tagName === 'SCRIPT') return;
      if (node.nodeType === Node.TEXT_NODE && !node.textContent.trim()) return;
      fragment.appendChild(node);
    });
    return fragment;
  }

  function restoreSidebarState() {
    localStorage.removeItem('ias-theme');
    const saved = localStorage.getItem(SIDEBAR_KEY);
    if (saved === '1') {
      setSidebarCollapsed(true, { skipPersist: true });
    }
  }

  function initAppShell(options) {
    const opts = options || {};
    const page = opts.page || '';
    const title = opts.title || SYSTEM_NAME;
    const crumb = opts.crumb || title;
    const admin = !!opts.admin;

    const mountSidebar = document.getElementById('sidebarMount');
    const mountTopbar = document.getElementById('topbarMount');

    if (mountSidebar && mountTopbar) {
      document.body.classList.add('has-app-shell');
      mountSidebar.replaceWith(buildSidebar(page, admin));
      mountTopbar.replaceWith(buildTopbar(title, crumb));
      const app = document.querySelector('.app.app-shell') || document.querySelector('.app');
      if (app && !app.querySelector('.sidebar-expand-btn')) {
        app.appendChild(buildSidebarExpandBtn());
      }
      restoreSidebarState();
      return;
    }

    if (document.body.classList.contains('has-app-shell')) return;

    document.body.classList.add('has-app-shell');

    const app = document.createElement('div');
    app.className = 'app app-shell';

    const gridBg = document.createElement('div');
    gridBg.className = 'app-grid-bg';
    app.appendChild(gridBg);

    app.appendChild(buildSidebar(page, admin));

    const main = document.createElement('div');
    main.className = 'main';

    main.appendChild(buildTopbar(title, crumb));

    const content = document.createElement('div');
    content.className = 'content';
    content.appendChild(collectBodyContent());
    main.appendChild(content);

    app.appendChild(main);
    app.appendChild(buildSidebarExpandBtn());

    document.body.insertBefore(app, document.body.firstChild);
    restoreSidebarState();
  }

  function esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  window.initAppShell = initAppShell;
  window.AppShell = {
    isCollapsed,
    setSidebarCollapsed,
    toggleSidebar,
    collapseForAdvisor,
    restoreAfterAdvisor,
  };
})();
