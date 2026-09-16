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

    const label = summary.querySelector('[data-access-summary-label], b');
    const detail = summary.querySelector('[data-access-summary-detail], div > span');
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

  function scheduleSummarySync() {
    requestAnimationFrame(syncLoginRoleSummary);
  }

  function install() {
    ensureStyles();
    setMobileNavigation(false);
    scheduleSummarySync();

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
