(() => {
  'use strict';
  if (window.__PLACEAI_PRODUCTION_POLISH_LOADED__) return;
  window.__PLACEAI_PRODUCTION_POLISH_LOADED__ = true;

  const ROLE_SUMMARY = {
    student: {label: 'Student', detail: 'Student workspace'},
    recruiter: {label: 'Recruiter', detail: 'Recruiter workspace'},
    institution_admin: {label: 'Institution Admin', detail: 'Placement office'},
    platform_admin: {label: 'Platform Admin', detail: 'Platform control'},
  };
  const WORKSPACE_VIEW_KEY = 'placeai.workspace.view.v1';
  let workspaceGuardScheduled = false;

  function ensureStyles() {
    if (document.querySelector('link[data-placeai-production-polish]')) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = '/static/production-polish.css';
    link.dataset.placeaiProductionPolish = '';
    document.head.appendChild(link);
  }

  function marketingHeader() {
    return document.querySelector('#marketing-site .site-header');
  }

  function setMobileNavigation(open) {
    const header = marketingHeader();
    const menu = header?.querySelector('.mobile-menu[data-action="toggle-mobile-menu"]');
    if (!header || !menu) return;
    header.classList.toggle('mobile-open', Boolean(open));
    menu.setAttribute('aria-expanded', String(Boolean(open)));
    menu.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
    menu.textContent = open ? 'Close' : 'Menu';
  }

  function syncLoginRoleSummary() {
    const view = document.querySelector('#login-view');
    if (!view || view.classList.contains('hidden')) return;
    const selected = view.querySelector('[data-access-role-mode="login"].is-selected');
    const summary = view.querySelector('.access-selection-summary');
    if (!selected || !summary) return;
    const role = ROLE_SUMMARY[selected.dataset.accessRole];
    if (!role) return;

    const dot = summary.querySelector(':scope > .access-role-dot');
    const label = summary.querySelector('[data-access-summary-label]') || summary.querySelector(':scope > div > b');
    const detail = summary.querySelector('[data-access-summary-short]') || summary.querySelector('[data-access-summary-detail]') || summary.querySelector(':scope > div > span');

    if (dot) {
      if (dot.textContent) dot.textContent = '';
      dot.setAttribute('aria-hidden', 'true');
    }
    if (label) {
      label.dataset.accessSummaryLabel = '';
      if (label.textContent !== role.label) label.textContent = role.label;
    }
    if (detail) {
      detail.dataset.accessSummaryDetail = '';
      if (detail.textContent !== role.detail) detail.textContent = role.detail;
    }
    summary.setAttribute('aria-live', 'polite');
  }

  function clearWorkspaceViewState() {
    try { sessionStorage.removeItem(WORKSPACE_VIEW_KEY); } catch {}
    try {
      const url = new URL(location.href);
      if (url.searchParams.has('view')) {
        url.searchParams.delete('view');
        history.replaceState(history.state || {}, '', `${url.pathname}${url.search}${url.hash}`);
      }
    } catch {}
  }

  function repairInvalidWorkspaceView() {
    workspaceGuardScheduled = false;
    const shell = document.querySelector('#app-shell');
    const nav = document.querySelector('#app-nav');
    if (!shell || shell.classList.contains('hidden') || !nav) return;

    const buttons = [...nav.querySelectorAll('button[data-view]')];
    if (!buttons.length) return;
    const allowed = new Set(buttons.map(button => button.dataset.view).filter(Boolean));

    let requested = '';
    try { requested = new URL(location.href).searchParams.get('view') || ''; } catch {}
    let stored = '';
    try { stored = sessionStorage.getItem(WORKSPACE_VIEW_KEY) || ''; } catch {}

    const stale = [requested, stored].filter(Boolean).find(view => !allowed.has(view));
    if (!stale) return;

    clearWorkspaceViewState();
    const content = document.querySelector('#app-content');
    const dashboard = nav.querySelector('button[data-view="dashboard"]');
    const active = nav.querySelector('button.active[data-view]');
    const activeValid = Boolean(active?.dataset.view && allowed.has(active.dataset.view));
    const loading = Boolean(content?.querySelector('.loading-state'));

    if (dashboard && (!activeValid || loading)) {
      dashboard.click();
    }
  }

  function scheduleWorkspaceGuard() {
    if (workspaceGuardScheduled) return;
    workspaceGuardScheduled = true;
    requestAnimationFrame(repairInvalidWorkspaceView);
  }

  function scheduleSummarySync() {
    requestAnimationFrame(syncLoginRoleSummary);
  }

  function install() {
    ensureStyles();
    setMobileNavigation(false);
    scheduleSummarySync();
    scheduleWorkspaceGuard();

    const loginView = document.querySelector('#login-view');
    if (loginView) {
      const observer = new MutationObserver(scheduleSummarySync);
      observer.observe(loginView, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['class', 'aria-selected'],
      });
    }

    const nav = document.querySelector('#app-nav');
    const shell = document.querySelector('#app-shell');
    const content = document.querySelector('#app-content');
    const workspaceObserver = new MutationObserver(scheduleWorkspaceGuard);
    if (nav) workspaceObserver.observe(nav, {childList: true, subtree: true, attributes: true, attributeFilter: ['class']});
    if (shell) workspaceObserver.observe(shell, {attributes: true, attributeFilter: ['class']});
    if (content) workspaceObserver.observe(content, {childList: true, subtree: true});

    document.addEventListener('click', event => {
      const mobileToggle = event.target.closest?.('.mobile-menu[data-action="toggle-mobile-menu"]');
      if (mobileToggle) {
        event.preventDefault();
        event.stopImmediatePropagation();
        const header = marketingHeader();
        setMobileNavigation(!header?.classList.contains('mobile-open'));
        return;
      }

      if (event.target.closest?.('#marketing-site .marketing-nav a, #marketing-site .header-actions button')) {
        setMobileNavigation(false);
      }

      if (event.target.closest?.('[data-access-role-mode="login"]')) {
        scheduleSummarySync();
      }

      if (event.target.closest?.('#app-nav button[data-view]')) {
        scheduleWorkspaceGuard();
      }
    }, true);

    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && marketingHeader()?.classList.contains('mobile-open')) {
        setMobileNavigation(false);
      }
    });

    const desktopQuery = window.matchMedia('(min-width: 761px)');
    const resetForDesktop = event => {
      if (event.matches) setMobileNavigation(false);
    };
    if (desktopQuery.addEventListener) desktopQuery.addEventListener('change', resetForDesktop);
    else desktopQuery.addListener?.(resetForDesktop);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, {once: true});
  else install();
})();
