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
  let workspaceEnhancementScheduled = false;

  const esc = value => String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  const fmtDate = value => value ? new Intl.DateTimeFormat('en-IN', {day:'2-digit', month:'short', year:'numeric'}).format(new Date(value)) : '—';

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

  function syncRecruiterAccessTargetField() {
    const form = document.querySelector('#role-access-request-form');
    const role = form?.querySelector('input[name="requested_role"]')?.value;
    if (!form || role !== 'recruiter') return;
    const input = form.querySelector('input[name="organization_name"]');
    const label = input?.closest('label');
    if (!input || !label) return;
    const first = [...label.childNodes].find(node => node.nodeType === Node.TEXT_NODE);
    if (first) first.nodeValue = 'Target institution name or code ';
    input.placeholder = 'Exact institution name or institution code';
    input.setAttribute('aria-label', 'Target institution name or code');
  }

  function isInstitutionWorkspace() {
    return (document.querySelector('#sidebar-user-role')?.textContent || '').trim().toLowerCase() === 'institution admin';
  }

  function ensureInstitutionAccessNav() {
    const nav = document.querySelector('#app-nav');
    if (!nav || !isInstitutionWorkspace()) return;
    if (nav.querySelector('[data-institution-access-requests]')) return;

    const group = document.createElement('div');
    group.className = 'nav-group-label';
    group.dataset.institutionAccessGroup = '';
    group.textContent = 'Access';

    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.institutionAccessRequests = '';
    button.innerHTML = '<span class="nav-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h16v16H4zM4 9h16M8 13h8M8 17h5"/></svg></span><span class="nav-label">Access requests</span>';
    nav.append(group, button);
  }

  async function authorizedJson(path, options = {}) {
    const attempt = async token => {
      const headers = new Headers(options.headers || {});
      if (token) headers.set('Authorization', `Bearer ${token}`);
      if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
      return fetch(path, {...options, headers, credentials: 'include'});
    };

    let response = await attempt('');
    if (response.status === 401) {
      const refresh = await fetch('/auth/refresh', {method: 'POST', headers: {'Content-Type':'application/json'}, body: '{}', credentials: 'include'});
      if (refresh.ok) {
        const payload = await refresh.json().catch(() => ({}));
        response = await attempt(payload.access_token || '');
      }
    }
    const type = response.headers.get('content-type') || '';
    const data = type.includes('application/json') ? await response.json().catch(() => ({})) : {};
    if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
    return data;
  }

  function institutionAccessTable(rows) {
    if (!rows.length) {
      return '<div class="data-panel"><div class="table-empty-state"><strong>No recruiter access requests</strong><span>New recruiter requests appear here when the requester enters your exact institution name or institution code.</span></div></div>';
    }
    const statuses = ['new', 'under_review', 'approved', 'rejected'];
    return `<div class="data-panel"><div class="data-toolbar"><span class="table-secondary">${rows.length} institution-scoped request${rows.length === 1 ? '' : 's'}</span></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Requester</th><th>Target institution</th><th>Context</th><th>Received</th><th>Status / action</th></tr></thead><tbody>${rows.map(row => `<tr><td><span class="table-primary">${esc(row.full_name)}</span><span class="table-secondary">${esc(row.work_email)}</span></td><td>${esc(row.organization_name || '—')}</td><td><span class="table-secondary">${esc(row.message || row.phone || 'No additional context')}</span></td><td>${fmtDate(row.created_at)}</td><td><select class="form-control" data-institution-access-status data-id="${esc(row.id)}" data-current-status="${esc(row.status)}" aria-label="Access request status for ${esc(row.full_name)}">${statuses.map(status => `<option value="${status}" ${status === row.status ? 'selected' : ''}>${status.replaceAll('_',' ')}</option>`).join('')}</select>${row.status === 'approved' ? '<span class="table-secondary">Provision the recruiter account from Recruiters.</span>' : ''}</td></tr>`).join('')}</tbody></table></div></div>`;
  }

  async function renderInstitutionAccessRequests() {
    const nav = document.querySelector('#app-nav');
    const content = document.querySelector('#app-content');
    if (!nav || !content || !isInstitutionWorkspace()) return;
    nav.querySelectorAll('button').forEach(button => button.classList.remove('active'));
    nav.querySelector('[data-institution-access-requests]')?.classList.add('active');
    content.innerHTML = '<div class="panel"><div class="panel-head"><div><h2>Access requests</h2><p>Loading institution-scoped recruiter requests…</p></div></div></div>';
    try {
      const rows = await authorizedJson('/institutions/access-requests');
      content.innerHTML = `<div class="page-head"><div><h1>Recruiter access requests</h1><p>Review only recruiter requests explicitly targeted to your institution. Platform and Institution Admin requests remain Platform Admin-controlled.</p></div><button class="button button-secondary" type="button" data-institution-open-recruiters>Recruiters</button></div>${institutionAccessTable(rows)}`;
    } catch (error) {
      content.innerHTML = `<div class="page-head"><div><h1>Access requests</h1><p>${esc(error.message)}</p></div></div><div class="data-panel"><div class="table-empty-state"><strong>Unable to load access requests</strong><span>${esc(error.message)}</span><button class="button button-secondary" type="button" data-institution-access-retry>Try again</button></div></div>`;
    }
  }

  async function updateInstitutionAccessStatus(select) {
    const previous = select.dataset.currentStatus || '';
    select.disabled = true;
    try {
      const result = await authorizedJson(`/institutions/access-requests/${encodeURIComponent(select.dataset.id)}`, {
        method: 'PATCH',
        body: JSON.stringify({status: select.value}),
      });
      select.dataset.currentStatus = result.status;
      await renderInstitutionAccessRequests();
    } catch (error) {
      select.value = previous;
      select.disabled = false;
      window.alert(`Could not update access request: ${error.message}`);
    }
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
    if (stale) clearWorkspaceViewState();

    const content = document.querySelector('#app-content');
    const dashboard = nav.querySelector('button[data-view="dashboard"]');
    const active = nav.querySelector('button.active[data-view]');
    const activeValid = Boolean(active?.dataset.view && allowed.has(active.dataset.view));
    const customActive = Boolean(nav.querySelector('button.active[data-institution-access-requests]'));
    const loading = Boolean(content?.querySelector('.loading-state'));
    const unsupportedLoadingView = loading && !activeValid && !customActive;

    if (!stale && !unsupportedLoadingView) return;
    if (dashboard && (!activeValid || loading)) {
      dashboard.click();
    }
  }

  function scheduleWorkspaceGuard() {
    if (workspaceGuardScheduled) return;
    workspaceGuardScheduled = true;
    requestAnimationFrame(repairInvalidWorkspaceView);
  }

  function scheduleWorkspaceEnhancements() {
    if (workspaceEnhancementScheduled) return;
    workspaceEnhancementScheduled = true;
    requestAnimationFrame(() => {
      workspaceEnhancementScheduled = false;
      ensureInstitutionAccessNav();
      syncRecruiterAccessTargetField();
    });
  }

  function scheduleSummarySync() {
    requestAnimationFrame(syncLoginRoleSummary);
  }

  function install() {
    ensureStyles();
    setMobileNavigation(false);
    scheduleSummarySync();
    scheduleWorkspaceGuard();
    scheduleWorkspaceEnhancements();

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

    const authOverlay = document.querySelector('#auth-overlay');
    if (authOverlay) {
      const accessObserver = new MutationObserver(scheduleWorkspaceEnhancements);
      accessObserver.observe(authOverlay, {childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'aria-selected']});
    }

    const nav = document.querySelector('#app-nav');
    const shell = document.querySelector('#app-shell');
    const content = document.querySelector('#app-content');
    const workspaceObserver = new MutationObserver(() => {
      scheduleWorkspaceGuard();
      scheduleWorkspaceEnhancements();
    });
    if (nav) workspaceObserver.observe(nav, {childList: true, subtree: true, attributes: true, attributeFilter: ['class']});
    if (shell) workspaceObserver.observe(shell, {attributes: true, attributeFilter: ['class']});
    if (content) workspaceObserver.observe(content, {childList: true, subtree: true});

    document.addEventListener('click', event => {
      const institutionAccess = event.target.closest?.('[data-institution-access-requests]');
      if (institutionAccess) {
        event.preventDefault();
        event.stopImmediatePropagation();
        clearWorkspaceViewState();
        renderInstitutionAccessRequests();
        return;
      }

      if (event.target.closest?.('[data-institution-access-retry]')) {
        event.preventDefault();
        renderInstitutionAccessRequests();
        return;
      }

      if (event.target.closest?.('[data-institution-open-recruiters]')) {
        event.preventDefault();
        document.querySelector('#app-nav button[data-view="recruiters"]')?.click();
        return;
      }

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

      if (event.target.closest?.('[data-access-role-mode="login"], [data-access-role-mode="create"]')) {
        scheduleSummarySync();
        scheduleWorkspaceEnhancements();
      }

      if (event.target.closest?.('#app-nav button[data-view]')) {
        document.querySelector('[data-institution-access-requests]')?.classList.remove('active');
        scheduleWorkspaceGuard();
      }
    }, true);

    document.addEventListener('change', event => {
      const select = event.target.closest?.('[data-institution-access-status]');
      if (select) updateInstitutionAccessStatus(select);
    });

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
