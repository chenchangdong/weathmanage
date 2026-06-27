/**
 * 资配旅程软导航 — 换页不刷新，智能顾问 DOM 保持单例。
 */
(function () {
  'use strict';

  const SOFT_PAGES = new Set([
    'wealth_inventory.html',
    'asset_diagnosis.html',
    'smart_allocation_setup.html',
    'smart_allocation.html',
  ]);

  const PAGE_META = {
    'wealth_inventory.html': {
      page: 'wealth_inventory',
      title: '财富盘点',
      crumb: '财富盘点',
      advisor: { bindHealthDiagnose: false, bindPlanExplain: false, bindAssetDiagnose: false },
    },
    'asset_diagnosis.html': {
      page: 'asset_diagnosis',
      title: '资产诊断',
      crumb: '资产诊断',
      advisor: { bindAssetDiagnose: true, bindHealthDiagnose: false, bindPlanExplain: false },
    },
    'smart_allocation_setup.html': {
      page: 'smart_allocation_setup',
      title: '智能资配',
      crumb: '智能资配',
      advisor: {},
    },
    'smart_allocation.html': {
      page: 'smart_allocation',
      title: '智能资配',
      crumb: '智能资配 / 配置方案',
      advisor: {},
    },
  };

  const PAGE_BOOT = {
    'wealth_inventory.html': () => window.WealthInventoryPage && WealthInventoryPage.boot(),
    'asset_diagnosis.html': () => window.AssetDiagnosisPage && AssetDiagnosisPage.boot(),
  };

  const SKIP_SRC = new Set([
    'common.js',
    'app_shell.js',
    'wealth_journey.js',
    'journey_state.js',
    'journey_soft_nav.js',
  ]);

  function shouldSkipScript(src) {
    const norm = (src || '').replace(/^\.?\/?js\//, '').split('?')[0];
    if (SKIP_SRC.has(norm)) return true;
    if (/^advisor_chat\.js/.test(norm)) return true;
    return false;
  }

  function pageName(path) {
    return (path || '').split('/').pop() || '';
  }

  function buildUrl(path, customerId) {
    const base = path.split('?')[0];
    if (pageName(base) === 'wealth_inventory.html') return base;
    if (!customerId) return base;
    return `${base}?customer_id=${encodeURIComponent(customerId)}`;
  }

  function canSoftNav(targetPath) {
    const target = pageName(targetPath);
    const current = pageName(location.pathname);
    return (
      document.body.hasAttribute('data-advisor-dock')
      && SOFT_PAGES.has(target)
      && SOFT_PAGES.has(current)
      && typeof AdvisorChat !== 'undefined'
      && AdvisorChat._mounted
    );
  }

  function collectContentNodes(doc) {
    const nodes = [];
    doc.body.childNodes.forEach((node) => {
      if (node.nodeType === Node.ELEMENT_NODE && node.tagName === 'SCRIPT') return;
      if (node.nodeType === Node.TEXT_NODE && !(node.textContent || '').trim()) return;
      nodes.push(node.cloneNode(true));
    });
    return nodes;
  }

  function runInlineBootFromDoc(doc) {
    doc.body.querySelectorAll('script').forEach((s) => {
      if (s.src) return;
      let code = s.textContent || '';
      if (!code.trim()) return;
      code = code
        .replace(/initAppShell\s*\([^)]*\)\s*;?/g, '')
        .replace(/AdvisorChat\.init(?:DockPage)?\s*\([^)]*\)\s*;?/g, '')
        .replace(/WealthJourney\.initAdvisor\s*\([^)]*\)\s*;?/g, '')
        .replace(/syncCustomerContextFromUrl\s*\(\s*\)\s*;?/g, '');
      try {
        new Function(code)();
      } catch (err) {
        console.warn('[JourneySoftNav] inline boot', err);
      }
    });
  }

  async function loadExternalScripts(doc) {
    const promises = [];
    doc.body.querySelectorAll('script[src]').forEach((s) => {
      const src = s.getAttribute('src') || '';
      if (shouldSkipScript(src)) return;
      const norm = src.replace(/^\.?\/?js\//, '').split('?')[0];
      if (document.querySelector(`script[src="${src}"]`) || document.querySelector(`script[src*="${norm}"]`)) return;
      promises.push(new Promise((resolve, reject) => {
        const el = document.createElement('script');
        el.src = src;
        el.onload = resolve;
        el.onerror = reject;
        document.body.appendChild(el);
      }));
    });
    if (promises.length) await Promise.allSettled(promises);
  }

  function applyBodyClassesFromPage(doc) {
    const preserve = new Set([
      'has-app-shell',
      'advisor-chat-docked-open',
      'advisor-chat-open',
      'advisor-chat-instant-layout',
    ]);
    const next = new Set((doc.body.className || '').split(/\s+/).filter(Boolean));
    preserve.forEach((cls) => {
      if (document.body.classList.contains(cls)) next.add(cls);
    });
    document.body.className = [...next].join(' ');
    if (doc.body.hasAttribute('data-advisor-dock')) {
      document.body.setAttribute('data-advisor-dock', '');
    }
  }

  async function go(path, customerId) {
    const file = pageName(path);
    const meta = PAGE_META[file];
    if (!meta) {
      window.location.href = buildUrl(path, customerId);
      return false;
    }

    if (customerId) setSelectedCustomerId(customerId);

    const url = buildUrl(path, customerId);
    const res = await fetch(url, { credentials: 'same-origin' });
    if (!res.ok) throw new Error(`加载 ${file} 失败`);
    const html = await res.text();
    const doc = new DOMParser().parseFromString(html, 'text/html');

    applyBodyClassesFromPage(doc);
    document.title = doc.title;

    const contentHost = document.querySelector('.app .content');
    if (!contentHost) {
      window.location.href = url;
      return false;
    }
    contentHost.replaceChildren(...collectContentNodes(doc));

    if (window.AppShell && typeof AppShell.updatePage === 'function') {
      AppShell.updatePage({ page: meta.page, title: meta.title, crumb: meta.crumb });
    }

    history.pushState({ journeySoftNav: true, file, customerId: customerId || '' }, '', url);

    if (typeof syncCustomerContextFromUrl === 'function') syncCustomerContextFromUrl();

    await loadExternalScripts(doc);

    if (PAGE_BOOT[file]) {
      const pageModule = file === 'asset_diagnosis.html' ? window.AssetDiagnosisPage
        : file === 'wealth_inventory.html' ? window.WealthInventoryPage
          : null;
      if (!pageModule || typeof pageModule.boot !== 'function') {
        window.location.href = url;
        return false;
      }
      await pageModule.boot();
    } else {
      runInlineBootFromDoc(doc);
    }

    if (typeof AdvisorChat !== 'undefined' && AdvisorChat.onPageEnter) {
      await AdvisorChat.onPageEnter({ page: file, dock: true, ...(meta.advisor || {}) });
    }

    return true;
  }

  function installNavigatePatch() {
    if (typeof navigateWithCustomer !== 'function' || navigateWithCustomer._softPatched) return;
    const orig = navigateWithCustomer;
    const patched = function (path, customerId) {
      if (canSoftNav(path)) {
        go(path, customerId).catch(() => { orig(path, customerId); });
        return;
      }
      orig(path, customerId);
    };
    patched._softPatched = true;
    window.navigateWithCustomer = patched;
  }

  function onLinkClick(e) {
    const a = e.target.closest('a[href]');
    if (!a || a.target === '_blank' || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const href = a.getAttribute('href');
    if (!href || href.startsWith('#') || href.startsWith('http')) return;
    const file = pageName(href.split('?')[0]);
    if (!SOFT_PAGES.has(file) || !canSoftNav(file)) return;
    e.preventDefault();
    const cid = new URL(a.href, location.href).searchParams.get('customer_id')
      || getCustomerId()
      || '';
    go(file, cid).catch(() => { window.location.href = a.href; });
  }

  window.addEventListener('popstate', (e) => {
    if (!e.state || !e.state.journeySoftNav) return;
    go(e.state.file, e.state.customerId).catch(() => location.reload());
  });

  document.addEventListener('click', onLinkClick, true);
  installNavigatePatch();

  window.JourneySoftNav = { go, canSoftNav, SOFT_PAGES };
})();
