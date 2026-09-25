(() => {
  'use strict';
  if (window.__PLACEAI_APP_CORE_LOADED__) return;
  window.__PLACEAI_APP_CORE_LOADED__ = true;

  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const esc = (v = '') => String(v ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const apiErrors = window.PlaceAIApiErrors;
  const fmtDate = v => v ? new Intl.DateTimeFormat('en-IN', { day:'2-digit', month:'short', year:'numeric' }).format(new Date(v)) : '—';
  const initials = v => (String(v || 'User').trim().split(/\s+/).slice(0,2).map(x => x[0] || '').join('').replace(/[^A-Za-z0-9]/g,'').toUpperCase().slice(0,2) || 'U');
  const statusBadge = v => `<span class="status-badge status-${esc(v)}">${esc(v)}</span>`;
  const tags = values => `<div class="skill-tags">${(values || []).slice(0,5).map(x => `<span class="skill-tag">${esc(x)}</span>`).join('')}</div>`;

  const navIcons = {
    dashboard:'<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>',
    opportunities:'<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18M10 12v2h4v-2"/></svg>',
    applications:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 4h10a2 2 0 0 1 2 2v14H8z"/><path d="M8 8H4v12h12M11 9h6M11 13h6M11 17h4"/></svg>',
    drives:'<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M8 3v4M16 3v4M3 10h18M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01"/></svg>',
    resume:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h5M9 12h6M9 16h6"/></svg>',
    notifications:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 8a6 6 0 1 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></svg>',
    profile:'<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>',
    jobs:'<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5h6v2M3 12h18"/></svg>',
    candidates:'<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="9" cy="8" r="3"/><circle cx="17" cy="9" r="2"/><path d="M3 20a6 6 0 0 1 12 0M14 20a5 5 0 0 1 7 0"/></svg>',
    analytics:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>',
    students:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m2 9 10-5 10 5-10 5zM6 11v5c3 2 9 2 12 0v-5M22 9v6"/></svg>',
    recruiters:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 21V6l7-3v18M10 9h11v12M6 9h1M6 13h1M6 17h1M14 13h3M14 17h3"/></svg>',
    audit:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 4 6v6c0 5 3.4 8.4 8 9 4.6-.6 8-4 8-9V6z"/><path d="m9 12 2 2 4-4"/></svg>',
    organizations:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 21V7l9-4 9 4v14M8 10h2M14 10h2M8 14h2M14 14h2M9 21v-4h6v4"/></svg>',
    leads:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h16v16H4zM4 9h16M8 13h8M8 17h5"/></svg>',
    interviews:'<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="9" cy="8" r="3"/><path d="M3 20a6 6 0 0 1 12 0M17 8h4M19 6v4M16 14h5v6h-5z"/></svg>',
    offers:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 3h14v18H5zM8 7h8M8 11h8M8 15h5"/><path d="m15 18 2 2 4-4"/></svg>',
    readiness:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 19V9M10 19V5M16 19v-7M22 19H2"/><path d="m4 7 5-3 6 4 5-4"/></svg>',
    documents:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h8l4 4v14H6zM14 3v5h5M9 12h6M9 16h4"/></svg>',
    assistant:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h14v11H9l-4 4z"/><path d="M9 9h.01M12 9h.01M15 9h.01"/></svg>',
    calendar:'<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M8 3v4M16 3v4M3 10h18M7 14h3M14 14h3M7 18h3"/></svg>',
    announcements:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 11v2l4 1 9 5V5L8 10zM8 14l1 6h3"/></svg>',
    incidents:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 3 20h18z"/><path d="M12 9v5M12 17h.01"/></svg>',
    approvals:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h12v18H6zM9 8h6M9 12h3"/><path d="m13 16 2 2 4-4"/></svg>',
    pipeline:'<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="6" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="18" r="2"/><path d="m7 7 3.5 3.5M13.5 13.5 17 17"/></svg>',
    verification:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 4 6v6c0 5 3.4 8.4 8 9 4.6-.6 8-4 8-9V6z"/><path d="m8.5 12 2.2 2.2 4.8-5"/></svg>',
    communications:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v11H8l-4 4z"/><path d="M8 9h8M8 12h5"/></svg>',
    attention:'<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v6M12 17h.01"/></svg>',
    analytics2:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20V11M10 20V4M16 20v-6M22 20H2"/><path d="m4 8 5-3 6 4 5-5"/></svg>',
    attendance:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h3v3h-3zM18 18h3v3h-3zM18 14h3v2h-3zM14 18h2v3h-2z"/></svg>',
    policies:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 3h14v18H5zM8 7h8M8 11h8M8 15h5"/><circle cx="17" cy="17" r="2"/></svg>',
    'custom-fields':'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v14H4zM8 9h8M8 13h5"/><path d="M17 14v5M14.5 16.5h5"/></svg>',
    reports:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 3h14v18H5zM8 16v-4M12 16V8M16 16v-6"/></svg>'
  };
  navIcons['mock-interview'] = navIcons.interviews;
  navIcons.integrations = navIcons.verification;
  navIcons.registrations = navIcons.students;
  navIcons.engagement = navIcons.analytics;
  navIcons.billing = navIcons.offers;
  const navIcon = id => `<span class="nav-icon">${navIcons[id] || navIcons.dashboard}</span>`;

  const state = {
    token: '',
    me: null,
    view: 'dashboard',
    nav: [],
    contextAction: null,
    profile: null,
    studentAccess: null,
  };

  function telemetryId(storage, key) {
    try {
      let value = storage.getItem(key);
      if (!value || value.length < 16 || value.length > 128) {
        value = globalThis.crypto?.randomUUID?.() || `${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}_${Math.random().toString(36).slice(2)}`;
        storage.setItem(key, value);
      }
      return value;
    } catch {
      return `${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}_${Math.random().toString(36).slice(2)}`;
    }
  }

  const placeAIVisitorId = telemetryId(localStorage, 'placeai_visitor_id');
  const placeAISessionId = globalThis.crypto?.randomUUID?.() || `${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}_${Math.random().toString(36).slice(2)}`;

  function trackPageView(path) {
    let referrerHost = '';
    try { referrerHost = document.referrer ? new URL(document.referrer).hostname : ''; } catch {}
    const headers = {'Content-Type':'application/json'};
    if (state.token) headers.Authorization = `Bearer ${state.token}`;
    fetch('/telemetry/page-view', {
      method: 'POST',
      headers,
      credentials: 'include',
      keepalive: true,
      body: JSON.stringify({
        visitor_id: placeAIVisitorId,
        session_id: placeAISessionId,
        path: String(path || location.pathname || '/').split('?')[0].split('#')[0],
        referrer_host: referrerHost || null,
      }),
    }).catch(() => {});
  }

  function toast(title, message = '', type = 'success') {
    const node = document.createElement('div');
    node.className = `toast ${type}`;
    node.innerHTML = `<div><strong>${esc(title)}</strong>${message ? `<span>${esc(message)}</span>` : ''}</div>`;
    $('#toast-region').appendChild(node);
    setTimeout(() => node.remove(), 3800);
  }

  async function api(path, options = {}, retry = true) {
    const headers = new Headers(options.headers || {});
    if (state.token) headers.set('Authorization', `Bearer ${state.token}`);
    if (!(options.body instanceof FormData) && options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
    const response = await fetch(path, { ...options, headers, credentials: 'include' });
    if (response.status === 401 && retry && path !== '/auth/refresh') {
      const refreshed = await refreshSession();
      if (refreshed) return api(path, options, false);
    }
    if (response.status === 204) return null;
    const contentType = response.headers.get('content-type') || '';
    if (!response.ok) {
      const data = contentType.includes('application/json') ? await response.json().catch(() => ({})) : {};
      throw apiErrors.createError(data, response.status);
    }
    if (contentType.includes('application/json')) return response.json();
    return response;
  }

  async function refreshSession() {
    try {
      const r = await fetch('/auth/refresh', { method:'POST', headers:{'Content-Type':'application/json'}, body:'{}', credentials:'include' });
      if (!r.ok) return false;
      const data = await r.json();
      state.token = data.access_token;
      return true;
    } catch { return false; }
  }

  const modalFocusableSelector = 'input:not([type="hidden"]):not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])';
  const modalOpeners = {auth: null, generic: null};
  const modalScrollLockOwners = new Set();
  const modalElement = kind => kind === 'generic' ? $('#generic-modal') : $('#auth-overlay');
  const modalIsVisible = element => element && !element.classList.contains('hidden');
  const modalFocusables = element => [...element.querySelectorAll(modalFocusableSelector)].filter(item => item.getClientRects().length && !item.disabled);
  const topmostModal = () => {
    const generic = $('#generic-modal');
    if (modalIsVisible(generic)) return generic;
    const auth = $('#auth-overlay');
    return modalIsVisible(auth) ? auth : null;
  };
  const focusModal = element => {
    requestAnimationFrame(() => {
      if (!modalIsVisible(element)) return;
      const target = modalFocusables(element).find(item => /^(INPUT|SELECT|TEXTAREA)$/.test(item.tagName)) || element.querySelector('[data-action="close-auth"], [data-action="close-generic-modal"], button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])') || element;
      if (!target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1');
      target.focus?.({preventScroll: true});
    });
  };
  const syncModalState = () => {
    for (const kind of ['auth', 'generic']) {
      if (modalIsVisible(modalElement(kind))) modalScrollLockOwners.add(kind);
      else modalScrollLockOwners.delete(kind);
    }
    document.body.classList.toggle('modal-open', modalScrollLockOwners.size > 0);
  };
  const rememberModalOpener = (kind = 'auth', candidate = document.activeElement) => {
    const dialog = modalElement(kind);
    const opener = candidate || document.activeElement;
    if (!opener || opener === document.body || dialog?.contains(opener)) return;
    if (typeof opener.focus === 'function') modalOpeners[kind] = opener;
  };
  const restoreModalOpener = (kind = 'auth') => {
    const opener = modalOpeners[kind];
    modalOpeners[kind] = null;
    requestAnimationFrame(() => {
      if (opener && document.contains(opener) && opener.getClientRects().length && !opener.disabled) {
        opener.focus?.();
        return;
      }
      const visible = topmostModal();
      if (visible) { focusModal(visible); return; }
    });
  };
  const trapModalTab = event => {
    const dialog = topmostModal();
    if (!dialog) return;
    const items = modalFocusables(dialog);
    if (!items.length) { event.preventDefault(); return; }
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    if (event.shiftKey && (active === first || !dialog.contains(active))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (active === last || !dialog.contains(active))) {
      event.preventDefault();
      first.focus();
    }
  };
  window.PlaceAIModalState = {sync: syncModalState, focusAuth: () => focusModal($('#auth-overlay')), rememberOpener: rememberModalOpener, restore: restoreModalOpener};

  function showAuth(view = 'login') {
    rememberModalOpener('auth');
    $('#auth-overlay').setAttribute('aria-labelledby', view === 'signup' ? 'auth-create-title' : view === 'reset' ? 'auth-reset-title' : 'auth-title');
    $('#auth-overlay').classList.remove('hidden');
    ['login-view','signup-view','reset-view'].forEach(id => $("#" + id).classList.add('hidden'));
    $("#" + (view === 'signup' ? 'signup-view' : view === 'reset' ? 'reset-view' : 'login-view')).classList.remove('hidden');
    syncModalState();
    focusModal($('#auth-overlay'));
  }
  function closeAuth() {
    $('#auth-overlay').classList.add('hidden');
    syncModalState();
    restoreModalOpener('auth');
  }
  function openModal(html) {
    rememberModalOpener('generic');
    const modal=$('#generic-modal');
    $('#generic-modal-content').innerHTML = html;
    const title = modal.querySelector('.generic-modal-content h1, .generic-modal-content h2, .generic-modal-content h3, .generic-modal-content h4, .generic-modal-content h5, .generic-modal-content h6');
    if (title) {
      title.id = 'generic-modal-title';
      modal.setAttribute('aria-labelledby', title.id);
      modal.removeAttribute('aria-label');
    } else {
      modal.removeAttribute('aria-labelledby');
      modal.setAttribute('aria-label', 'Dialog');
    }
    const cancel=$('#generic-modal-cancel');
    if(cancel) cancel.textContent = /<form\b/i.test(html) ? 'Cancel' : 'Close';
    modal.classList.remove('hidden');
    syncModalState();
    focusModal(modal);
  }
  function closeModal() {
    const modal = $('#generic-modal');
    modal.classList.add('hidden');
    $('#generic-modal-content').innerHTML = '';
    modal.removeAttribute('aria-labelledby');
    modal.setAttribute('aria-label', 'Dialog');
    syncModalState();
    restoreModalOpener('generic');
  }

  const navByRole = {
    student: [
      ['Workspace','dashboard','Dashboard'],['Workspace','opportunities','Opportunities'],['Workspace','applications','Applications'],['Campus','drives','Placement drives'],['Campus','interviews','Interviews'],['Campus','offers','Offers'],['Career','readiness','Readiness score'],['Career','mock-interview','Mock interview coach'],['Career','resume','Resume & AI'],['Career','documents','Document vault'],['Career','assistant','AI placement assistant'],['Planning','calendar','Placement calendar'],['Updates','announcements','Announcements'],['Updates','notifications','Notifications'],['Safety','incidents','Report an issue'],['Account','approvals','Profile approvals'],['Account','profile','Profile']
    ],
    recruiter: [
      ['Workspace','dashboard','Dashboard'],['Hiring','jobs','Jobs'],['Hiring','pipeline','Drive pipeline'],['Hiring','candidates','Candidates'],['Hiring','interviews','Interviews'],['Hiring','offers','Offers'],['Trust','verification','Company verification'],['Collaboration','communications','Placement office messages'],['Insights','analytics','Analytics'],['Insights','assistant','AI placement assistant'],['Updates','notifications','Notifications'],['Account','profile','Company profile']
    ],
    institution_admin: [
      ['Command centre','dashboard','Overview'],['Command centre','attention','Drive Rescue'],['Command centre','analytics2','Placement analytics'],['People','students','Students'],['People','approvals','Profile approvals'],['People','recruiters','Recruiters'],['Access','institution-access-requests','Access requests'],['Trust','verification','Company verification'],['Placements','jobs','Campus jobs'],['Placements','drives','Placement drives'],['Placements','pipeline','Drive pipelines'],['Placements','applications','Applications'],['Placements','interviews','Interviews'],['Placements','offers','Offer management'],['Operations','attendance','QR attendance'],['Operations','calendar','Placement calendar'],['Operations','announcements','Announcements'],['Operations','communications','Recruiter communication'],['Governance','policies','Placement policies'],['Governance','custom-fields','Custom fields'],['Governance','incidents','Incident reports'],['Governance','reports','Reports'],['Updates','notifications','Notifications'],['Governance','audit','Audit log']
    ],
    platform_admin: [
      ['Platform','dashboard','Overview'],['Platform','organizations','Institutions'],['People','registrations','Registrations'],['Insights','engagement','Engagement'],['Platform','integrations','Integrations'],['Access','leads','Access requests'],['Updates','notifications','Notifications']
    ]
  };

  function mountNav() {
    let items = navByRole[state.me.role] || [];
    if (state.me.role === 'student' && state.studentAccess?.student_kind === 'independent') {
      const allowed = new Set(['dashboard','opportunities','applications','interviews','offers','readiness','mock-interview','resume','documents','assistant','notifications','incidents','approvals','profile']);
      items = items.filter(([,id]) => allowed.has(id));
      items = [...items, ['Account','billing','Plan & billing']];
    }
    state.nav = items;
    let group = '';
    $('#app-nav').innerHTML = items.map(([g,id,label]) => {
      const heading = g !== group ? `<div class="nav-group-label">${esc(g)}</div>` : '';
      group = g;
      return `${heading}<button data-view="${id}" class="${state.view === id ? 'active' : ''}">${navIcon(id)}<span class="nav-label">${esc(label)}</span></button>`;
    }).join('');
  }

  function setContextAction(label = '', action = '') {
    const button = $('#context-action');
    state.contextAction = action || null;
    if (!label || !action) button.classList.add('hidden');
    else { button.classList.remove('hidden'); button.textContent = label; }
  }

  function setPage(title, eyebrow = 'Workspace') {
    $('#page-title').textContent = title;
    $('#page-eyebrow').textContent = eyebrow;
    const active = state.nav.find(x => x[1] === state.view);
    if (active) {
      $$('#app-nav button').forEach(b => b.classList.toggle('active', b.dataset.view === state.view));
      const activeButton = $(`#app-nav button[data-view="${state.view}"]`);
      requestAnimationFrame(() => activeButton?.scrollIntoView({ block:'nearest', inline:'nearest' }));
    }
  }

  function pageHead(title, subtitle, actionLabel = '', action = '') {
    // Primary page actions live in the sticky top bar. Keep a hidden proxy in the
    // document so the top-bar action can dispatch through the existing handler
    // without rendering a duplicate button inside the page body.
    setContextAction(actionLabel, action);
    const proxy = actionLabel && action ? `<button class="hidden" type="button" data-action="${esc(action)}" aria-hidden="true" tabindex="-1"></button>` : '';
    return `<div class="page-head"><div><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div></div>${proxy}`;
  }

  function emptyState(code, title, text, button = '') {
    return `<div class="empty-state"><span>${esc(code)}</span><h3>${esc(title)}</h3><p>${esc(text)}</p>${button}</div>`;
  }

  async function updateNotificationBadge() {
    const node = $('#notification-count');
    try {
      if (!state.me) return;
      const data = await api('/enterprise/notifications');
      const count = data.unread || 0;
      if (node) { node.textContent = count; node.classList.toggle('hidden', count === 0); }
      const dot = $('#notifications-button .notification-dot');
      if (dot) dot.classList.toggle('hidden', count === 0);
    } catch {
      if (node) node.classList.add('hidden');
    }
  }

  function notificationTarget(link) {
    const candidate = String(link || '').trim().split(':', 1)[0];
    return (state.nav || []).some(item => item[1] === candidate) ? candidate : 'notifications';
  }

  async function renderNotifications() {
    setPage('Notifications','Updates'); setContextAction();
    const data = await api('/enterprise/notifications');
    const items = data.items || [];
    $('#app-content').innerHTML = `${pageHead('Notification centre','Placement events, deadlines, approvals and actions from your real workspace.')}
      <section class="notification-panel">
        <div class="notification-panel-head"><div><span class="live-badge">LIVE WORKSPACE</span><h2>${data.unread || 0} unread update${(data.unread||0)===1?'':'s'}</h2><p>Notifications are stored in the PlaceAI database and linked to placement events.</p></div><div class="row-actions"><button class="row-button" data-action="notification-preferences">Preferences</button><button class="row-button primary" data-action="mark-notifications-read">Mark all read</button></div></div>
        <div class="notification-list">${items.length ? items.map(n=>`<article class="notification-item ${n.is_read ? '' : 'unread'}" data-notification-id="${n.id}"><span class="notification-type">${esc(n.category)}</span><div><strong>${esc(n.title)}</strong><p>${esc(n.message)}</p><span class="priority-label priority-${esc(n.priority)}">${esc(n.priority)}</span></div><div class="notification-end"><time>${fmtDate(n.created_at)}</time>${n.link?`<button class="row-button" data-action="open-notification" data-id="${n.id}" data-value="${esc(n.link)}">Open</button>`:''}</div></article>`).join('') : emptyState('NT','No notifications','New placement events and actions will appear here automatically.')}</div>
      </section>`;
    await updateNotificationBadge();
  }

  let bootWorkspaceCompleted = false;
  let bootWorkspaceInFlight = null;

  function bootWorkspace() {
    if (bootWorkspaceCompleted) return Promise.resolve(true);
    if (bootWorkspaceInFlight) return bootWorkspaceInFlight;
    const run = (async () => {
    try {
      state.me = await api('/auth/me');
    } catch {
      state.token=''; return false;
    }
    $('#marketing-site').classList.add('hidden');
    $('#app-shell').classList.remove('hidden');
    const display = state.me.username || state.me.email;
    $('#sidebar-user-name').textContent = display;
    $('#sidebar-user-role').textContent = state.me.role.replaceAll('_',' ');
    $('#sidebar-avatar').textContent = initials(display);
    $('#workspace-avatar').textContent = state.me.role === 'institution_admin' ? 'I' : state.me.role === 'recruiter' ? 'R' : state.me.role === 'platform_admin' ? 'P' : 'S';
    $('#workspace-kind').textContent = state.me.role === 'institution_admin' ? 'Institution workspace' : state.me.role === 'recruiter' ? 'Recruiter workspace' : state.me.role === 'platform_admin' ? 'Platform control' : 'Student workspace';
    $('#workspace-name').textContent = state.me.role === 'institution_admin' ? 'Placement Office' : display;
    $('#workspace-name').title = $('#workspace-name').textContent;
    if (state.me.role === 'student') {
      try { state.studentAccess = await api('/billing/status'); } catch { state.studentAccess = null; }
    }
    mountNav();
    await updateNotificationBadge();
    const attendanceToken=new URLSearchParams(location.search).get('attendance_token');
    if(attendanceToken && state.me.role==='student'){
      try{const checked=await api(`/enterprise/attendance/check-in?token=${encodeURIComponent(attendanceToken)}`,{method:'POST'});toast('Attendance recorded',`${checked.session} · checked in successfully.`);const u=new URL(location.href);u.searchParams.delete('attendance_token');history.replaceState({},'',u.pathname+u.search);}
      catch(err){toast('Attendance check-in failed',err.message,'error');}
    }
    await navigate('dashboard');
    return true;
    })();
    bootWorkspaceInFlight = run;
    run.then(
      result => {
        if (bootWorkspaceInFlight === run) bootWorkspaceInFlight = null;
        if (result) bootWorkspaceCompleted = true;
      },
      () => { if (bootWorkspaceInFlight === run) bootWorkspaceInFlight = null; }
    );
    return run;
  }

  async function navigate(view) {
    const premiumViews = new Set(['readiness','mock-interview','resume','documents','assistant']);
    if (state.me?.role === 'student' && state.studentAccess?.student_kind === 'independent' && premiumViews.has(view) && !state.studentAccess.premium_access) {
      view = 'billing';
    }
    if (view === 'mock-interview') { window.location.assign('/mock-interview'); return; }
    state.view = view;
    if (state.me) trackPageView(`/workspace/${state.me.role}/${view}`);
    mountNav();
    $('#app-content').innerHTML = `<div class="loading-state"><span class="loader"></span><p>Loading workspace…</p></div>`;
    try {
      if (view === 'notifications') { await renderNotifications(); return; }
      if (state.me.role === 'student') await renderStudent(view);
      else if (state.me.role === 'recruiter') await renderRecruiter(view);
      else if (state.me.role === 'institution_admin') await renderInstitution(view);
      else if (state.me.role === 'platform_admin') await renderPlatform(view);
    } catch (e) {
      $('#app-content').innerHTML = pageHead('Something needs attention', e.message) + emptyState('!', 'Unable to load this view', e.message, `<button class="button button-secondary" data-action="reload-view">Try again</button>`);
      setContextAction();
    }
  }

  async function renderStudent(view) {
    if (view === 'billing') {
      setPage('Plan & billing','Independent student'); setContextAction();
      const access = state.studentAccess || await api('/billing/status');
      const plans = await api('/billing/plans');
      const trialHours = access.trial_remaining_seconds ? Math.ceil(access.trial_remaining_seconds / 3600) : 0;
      const plan = plans.plans?.[0];
      $('#app-content').innerHTML = `${pageHead('Independent student access','University-linked students are institution-sponsored. Independent students receive a 3-day preparation trial, then need a paid plan for premium preparation tools.')}
        <div class="metric-grid">
          <article class="metric-card"><small>Account type</small><strong>${access.student_kind === 'university' ? 'University' : 'Independent'}</strong><span>${access.student_kind === 'university' ? 'Institution-sponsored access' : 'Public opportunities only; no campus opportunities'}</span></article>
          <article class="metric-card"><small>Access</small><strong>${esc(access.access_mode.replaceAll('_',' '))}</strong><span>${access.access_mode === 'trial' ? `${trialHours} trial hours remaining` : access.premium_access ? 'Preparation tools unlocked' : 'Premium preparation tools locked'}</span></article>
          <article class="metric-card"><small>Plan</small><strong>${plan ? `₹${plan.price_inr}/month` : 'Sponsored'}</strong><span>${plan ? '3-day free trial for independent students' : 'No student payment required'}</span></article>
        </div>
        ${plan ? `<div class="data-panel"><div class="data-toolbar"><div><span class="table-primary">PlaceAI Independent Student</span><span class="table-secondary">Public recruiter opportunities + premium preparation tools. Campus/university opportunities remain unavailable without a valid institution code.</span></div></div><div class="ai-box"><div class="ai-box-head"><span>PREMIUM PREPARATION</span></div><p>${plan.includes.map(esc).join(' · ')}</p></div><p class="form-intro">Live payment checkout is intentionally not activated until the merchant/payment provider is selected and verified. The entitlement layer is already enforced server-side.</p></div>` : ''}
      `;
      return;
    }
    if (['interviews','offers','readiness','documents','assistant','calendar','announcements','incidents','approvals'].includes(view)) return renderStudentEnterprise(view);
    if (view === 'dashboard') {
      setPage('Dashboard','Student workspace'); setContextAction();
      const [d, apps, jobs] = await Promise.all([api('/students/dashboard'), api('/students/applications'), api('/students/jobs')]);
      const recentApps = apps.slice(0,4);
      const completion = d.profile_completion || 0;
      $('#app-content').innerHTML = `${pageHead('Your placement readiness','One view of your profile, applications and preparation progress.')}
        <div class="metric-grid"><article class="metric-card"><small>Profile completion</small><strong>${completion}%</strong><span class="${completion >= 80 ? 'metric-good':''}">${completion >= 80 ? 'Ready for recruiter review' : 'Complete your profile to improve visibility'}</span></article><article class="metric-card"><small>Total applications</small><strong>${d.applications}</strong><span>${d.active_applications} currently active</span></article><article class="metric-card"><small>Mock interviews</small><strong>${d.interviews_completed}</strong><span>${d.average_interview_score ? `${d.average_interview_score}% average score` : 'No scored interviews yet'}</span></article><article class="metric-card"><small>Open opportunities</small><strong>${jobs.length}</strong><span>${d.verified ? 'Institution verified profile' : 'Profile verification pending'}</span></article></div>
        <div class="dashboard-grid"><section class="panel"><div class="panel-head"><div><h2>Recent applications</h2><p>Latest movement in your job pipeline</p></div><button data-view="applications">View all</button></div>${recentApps.length ? `<div class="activity-list">${recentApps.map(a => `<div class="activity-item"><span class="activity-icon">${initials(a.company_name)}</span><div><strong>${esc(a.job_title)}</strong><small>${esc(a.company_name || 'Company')} · Applied ${fmtDate(a.applied_at)}</small></div>${statusBadge(a.status)}</div>`).join('')}</div>` : emptyState('AP','No applications yet','Browse opportunities and start building your placement pipeline.')}</section>
        <section class="panel"><div class="panel-head"><div><h2>Readiness checklist</h2><p>High-impact completion signals</p></div></div><div class="progress-stack"><div class="progress-item"><span>Profile completeness</span><b>${completion}%</b><div class="progress-bar"><i style="--p:${Math.max(2,completion)}%"></i></div></div><div class="progress-item"><span>Resume uploaded</span><b>${d.has_resume ? '100%' : '0%'}</b><div class="progress-bar"><i style="--p:${d.has_resume ? 100 : 2}%"></i></div></div><div class="progress-item"><span>Institution verification</span><b>${d.verified ? '100%' : 'Pending'}</b><div class="progress-bar"><i style="--p:${d.verified ? 100 : 25}%"></i></div></div></div></section></div>`;
    } else if (view === 'opportunities') {
      setPage('Opportunities','Student workspace');
      const [jobs,apps] = await Promise.all([api('/students/jobs'),api('/students/applications')]); state.appliedJobIds=new Set(apps.map(a=>a.job_id));
      $('#app-content').innerHTML = `${pageHead('Open opportunities','Public and institution-approved jobs available to your profile.')}
      <div class="data-panel opportunities-panel"><div class="data-toolbar opportunities-toolbar"><input id="job-search" class="search-box" type="search" autocomplete="off" aria-label="Search opportunities" placeholder="Search role, company, skill or location"><select id="job-type-filter" class="filter-select" aria-label="Filter opportunities by job type"><option value="">All job types</option><option>Full-time</option><option>Internship</option><option>Part-time</option></select><span class="spacer"></span><span id="job-result-count" class="table-secondary opportunity-count">${jobs.length} ${jobs.length===1?'opportunity':'opportunities'}</span></div><div class="table-wrap">${jobs.length ? `<table class="data-table opportunities-table"><colgroup><col class="col-role"><col class="col-company"><col class="col-skills"><col class="col-type"><col class="col-deadline"><col class="col-action"></colgroup><thead><tr><th>Role</th><th>Company</th><th>Skills</th><th>Type</th><th>Deadline</th><th class="action-heading">Action</th></tr></thead><tbody id="jobs-body">${jobs.map(jobRowStudent).join('')}</tbody></table>` : emptyState('JB','No open opportunities','Your institution or recruiters have not published matching jobs yet.')}</div></div>`;
      state.lastJobs = jobs;
    } else if (view === 'applications') {
      setPage('Applications','Student workspace');
      const apps = await api('/students/applications');
      $('#app-content').innerHTML = `${pageHead('Application pipeline','Track every application from submission through final outcome.')}${apps.length ? `<div class="data-panel"><div class="table-wrap"><table class="data-table"><thead><tr><th>Role</th><th>Company</th><th>Applied</th><th>AI match</th><th>Status</th></tr></thead><tbody>${apps.map(a => `<tr><td><span class="table-primary">${esc(a.job_title)}</span><span class="table-secondary">${esc(a.job_type || '')}</span></td><td>${esc(a.company_name || '—')}</td><td>${fmtDate(a.applied_at)}</td><td>${a.ai_match_score != null ? `${Math.round(a.ai_match_score)} / 100` : 'Not scored'}</td><td>${statusBadge(a.status)}</td></tr>`).join('')}</tbody></table></div></div>` : emptyState('AP','No applications yet','Applications you submit will appear here with recruiter status updates.',`<button class="button button-primary" data-view="opportunities">Browse jobs</button>`)}`;
    } else if (view === 'drives') {
      setPage('Placement drives','Campus placements');
      const drives = await api('/students/drives');
      $('#app-content').innerHTML = `${pageHead('Campus placement drives','Institution-approved hiring events for your batch.')}${drives.length ? `<div class="data-panel"><div class="table-wrap"><table class="data-table"><thead><tr><th>Drive</th><th>Company / role</th><th>Criteria</th><th>Event date</th><th>Status</th><th></th></tr></thead><tbody>${drives.map(d => `<tr><td><span class="table-primary">${esc(d.title)}</span><span class="table-secondary">Registration ${d.registration_deadline ? `until ${fmtDate(d.registration_deadline)}` : 'open'}</span></td><td>${esc(d.company_name || '—')}<span class="table-secondary">${esc(d.job_title || '')}</span></td><td>CGPA ${d.min_cgpa ?? 'Any'}<span class="table-secondary">${esc((d.allowed_branches || []).join(', ') || 'All branches')}</span></td><td>${fmtDate(d.event_date)}</td><td>${statusBadge(d.status)}</td><td><button class="row-button primary" data-action="check-eligibility" data-id="${d.id}">Check eligibility</button></td></tr>`).join('')}</tbody></table></div></div>` : emptyState('DR','No open campus drives','Your placement office has not opened a placement drive right now.')}`;
    } else if (view === 'resume') {
      setPage('Resume & AI','Career intelligence'); setContextAction();
      let resume = null; try { resume = await api('/students/resume'); } catch(e) { if(e.status !== 404) throw e; }
      const profile = await api('/students/profile'); state.profile = profile;
      $('#app-content').innerHTML = `<div class="page-head resume-readiness-head"><div><h1>Resume & AI Readiness</h1><p>Keep the source resume under your control and use AI features explicitly.</p></div></div>
      <section class="form-panel"><div class="panel-head"><div><h2>Resume</h2><p>PDF only · maximum 5 MB</p></div></div><div class="resume-card"><div><span class="resume-icon">PDF</span><div><strong>${resume ? esc(resume.original_filename) : 'No resume uploaded'}</strong><small>${resume ? `Uploaded ${fmtDate(resume.uploaded_at)} · ${resume.is_parsed ? 'AI parsed' : 'Not parsed'}` : 'Upload a text-based PDF to unlock resume analysis.'}</small></div></div><div class="row-actions"><label class="row-button primary">${resume ? 'Replace' : 'Upload'}<input id="resume-file" type="file" accept="application/pdf" hidden></label>${resume ? `<button class="row-button" data-action="parse-resume">Parse with AI</button>` : ''}</div></div>
      <div class="ai-box"><div class="ai-box-head"><span>AI PROFILE SUMMARY</span><button class="row-button primary" data-action="generate-summary">Generate / refresh</button></div><p>${profile.ai_summary ? esc(profile.ai_summary) : 'No AI summary yet. Generate one only after your profile contains accurate education and skills.'}</p></div>
      ${resume?.ai_parsed_data ? `<div class="ai-box"><div class="ai-box-head"><span>PARSED RESUME DATA</span><span>${(resume.ai_parsed_data.skills || []).length} skills detected</span></div>${tags(resume.ai_parsed_data.skills || [])}<p>${esc(resume.ai_parsed_data.summary || '')}</p></div>` : ''}</section>`;
    } else if (view === 'profile') {
      setPage('Profile','Student account'); setContextAction();
      const p = await api('/students/profile'); state.profile = p;
      const defs = await api('/enterprise/custom-fields').catch(()=>[]);
      const customValues = p.id ? await api(`/enterprise/custom-fields/values/${p.id}`).catch(()=>({})) : {};
      state.customFieldDefs = defs;
      $('#app-content').innerHTML = `${pageHead('Student profile','Keep academic, contact and institution-specific information accurate for eligibility checks.')}
      <form id="student-profile-form" class="form-panel"><div class="profile-section-head"><div><h2>Identity & contact</h2><p>Keep your recruiter-facing information accurate.</p></div>${p.is_verified?statusBadge('approved'):statusBadge('pending')}</div><div class="profile-grid">${inputField('Full name','full_name',p.full_name)}${inputField('College','college',p.college)}${inputField('Degree','degree',p.degree)}${inputField('Branch','branch',p.branch)}${inputField('Graduation year','graduation_year',p.graduation_year,'number')}${inputField('CGPA','cgpa',p.cgpa,'number','0.0','10','0.01')}${inputField('10th percentage','tenth_percentage',p.tenth_percentage,'number','0','100','0.01')}${inputField('12th percentage','twelfth_percentage',p.twelfth_percentage,'number','0','100','0.01')}${inputField('Diploma percentage','diploma_percentage',p.diploma_percentage,'number','0','100','0.01')}${inputField('Active backlogs','active_backlogs',p.active_backlogs,'number','0','100','1')}${inputField('Historical backlogs','historical_backlogs',p.historical_backlogs,'number','0','100','1')}${inputField('Academic gap (months)','academic_gap_months',p.academic_gap_months,'number','0','240','1')}${inputField('Work authorization','work_authorization',p.work_authorization)}<label class="field-label full">Skills <span class="field-help">Comma separated</span><input class="field-input" name="skills" value="${esc((p.skills || []).join(', '))}"></label><label class="field-label full">Certifications <span class="field-help">Comma separated</span><input class="field-input" name="certifications" value="${esc((p.certifications || []).join(', '))}"></label><label class="field-label full">Desired roles<input class="field-input" name="desired_roles" value="${esc((p.desired_roles || []).join(', '))}"></label>${inputField('Phone','phone',p.phone)}${inputField('LinkedIn URL','linkedin_url',p.linkedin_url,'url')}${inputField('GitHub URL','github_url',p.github_url,'url')}${inputField('Portfolio URL','portfolio_url',p.portfolio_url,'url')}<label class="field-label full">Professional bio<textarea class="field-input" rows="4" name="bio">${esc(p.bio || '')}</textarea></label></div>${defs.length?`<div class="custom-profile-section"><div class="profile-section-head"><div><h2>Institution-specific information</h2><p>Fields configured by your placement office.</p></div></div><div class="profile-grid">${defs.filter(d=>d.entity_type==='student').map(d=>customFieldControl(d,customValues[d.field_key]||'')).join('')}</div></div>`:''}<div class="note-box"><strong>Institution-verified academic data</strong><p>Changes to degree, branch, graduation year, CGPA, school percentages, backlogs or academic gaps are submitted to your placement office for approval instead of silently replacing verified records.</p></div><div class="form-footer"><button class="button button-primary" type="submit">Save profile</button></div></form>`;
    }
  }

  function jobRowStudent(j) {
    const skillHtml=(j.required_skills||[]).length?tags(j.required_skills):'<span class="table-secondary">No skills specified</span>';
    return `<tr><td class="opportunity-role"><span class="table-primary">${esc(j.title)}</span><span class="table-secondary">${esc(j.location || 'Location flexible')}</span></td><td class="opportunity-company"><span class="table-primary normal-weight">${esc(j.company_name || '—')}</span>${j.target_organization_name ? `<span class="table-secondary">Campus · ${esc(j.target_organization_name)}</span>`:''}</td><td class="opportunity-skills">${skillHtml}</td><td class="opportunity-type">${esc(j.job_type || '—')}</td><td class="opportunity-deadline">${fmtDate(j.deadline)}</td><td class="opportunity-action">${state.appliedJobIds?.has(j.id)?`<button class="row-button" type="button" disabled>Applied</button>`:`<button class="row-button primary" data-action="apply-job" data-id="${j.id}">Apply</button>`}</td></tr>`;
  }

  function filterStudentJobs(){
    if(!state.lastJobs || !$('#jobs-body')) return;
    const term=($('#job-search')?.value||'').trim().toLowerCase();
    const type=($('#job-type-filter')?.value||'').trim().toLowerCase();
    const filtered=state.lastJobs.filter(j=>{
      const haystack=[j.title,j.company_name,j.description,j.location,j.job_type,j.salary_range,j.experience_required,...(j.required_skills||[]),...(j.preferred_roles||[]),j.target_organization_name].filter(Boolean).join(' ').toLowerCase();
      return (!term || haystack.includes(term)) && (!type || String(j.job_type||'').toLowerCase()===type);
    });
    $('#jobs-body').innerHTML=filtered.length?filtered.map(jobRowStudent).join(''):`<tr><td colspan="6"><div class="table-empty-state"><strong>No matching opportunities</strong><span>Try a different search term or job type.</span></div></td></tr>`;
    const count=$('#job-result-count');
    if(count) count.textContent=`${filtered.length} ${filtered.length===1?'opportunity':'opportunities'}`;
  }

  async function renderRecruiter(view) {
    if (['pipeline','interviews','offers','verification','communications','assistant'].includes(view)) return renderRecruiterEnterprise(view);
    if (view === 'dashboard') {
      setPage('Dashboard','Recruiter workspace'); setContextAction('Post job','open-job-form');
      const [d,jobs] = await Promise.all([api('/recruiters/dashboard'),api('/jobs/my/listings')]);
      $('#app-content').innerHTML = `${pageHead('Hiring overview',d.verified ? 'Your recruiter account is verified and ready for controlled campus hiring.' : 'Your recruiter account is awaiting verification.','Post a job','open-job-form')}
      <div class="metric-grid"><article class="metric-card"><small>Active jobs</small><strong>${d.active_jobs}</strong><span>${jobs.length} total listings</span></article><article class="metric-card"><small>Applications</small><strong>${d.applications}</strong><span>Across your hiring pipeline</span></article><article class="metric-card"><small>Interview stage</small><strong>${d.interviews}</strong><span>${d.shortlisted} shortlisted</span></article><article class="metric-card"><small>Offers / hires</small><strong>${d.offers} / ${d.hired}</strong><span class="${d.hired ? 'metric-good':''}">Tracked final outcomes</span></article></div>
      <div class="dashboard-grid"><section class="panel"><div class="panel-head"><div><h2>Recent job listings</h2><p>Approval and application activity</p></div><button data-view="jobs">Manage jobs</button></div>${jobs.length ? `<div class="activity-list">${jobs.slice(0,5).map(j => `<div class="activity-item"><span class="activity-icon">${initials(j.company_name)}</span><div><strong>${esc(j.title)}</strong><small>${esc(j.company_name || '')} · ${j.application_count} applications</small></div>${statusBadge(j.approval_status)}</div>`).join('')}</div>` : emptyState('JB','No job listings','Create your first verified opportunity.')}</section><section class="panel"><div class="panel-head"><div><h2>Privacy boundary</h2><p>Candidate access in this deployment</p></div></div><div class="ai-box"><div class="ai-box-head"><span>PIPELINE-ONLY ACCESS</span></div><p>Your candidate search is restricted to students who have applied to your jobs. This prevents the student database from becoming an open recruiter directory.</p></div></section></div>`;
    } else if (view === 'jobs') {
      setPage('Jobs','Recruiter workspace'); setContextAction('Post job','open-job-form');
      const jobs = await api('/jobs/my/listings'); state.lastJobs = jobs;
      $('#app-content').innerHTML = `${pageHead('Job listings','Create public jobs or institution-targeted campus opportunities.','Post a job','open-job-form')}${jobs.length ? `<div class="data-panel"><div class="table-wrap"><table class="data-table"><thead><tr><th>Role</th><th>Visibility</th><th>Approval</th><th>Applications</th><th>Deadline</th><th></th></tr></thead><tbody>${jobs.map(j => `<tr><td><span class="table-primary">${esc(j.title)}</span><span class="table-secondary">${esc(j.company_name || '')} · ${esc(j.location || '')}</span></td><td>${j.visibility === 'campus' ? `Campus<span class="table-secondary">${esc(j.target_organization_name || 'Target institution')}</span>` : 'Public'}</td><td>${statusBadge(j.approval_status)}</td><td>${j.application_count}</td><td>${fmtDate(j.deadline)}</td><td><div class="row-actions"><button class="row-button primary" data-action="view-applicants" data-id="${j.id}">Applicants</button><button class="row-button" data-action="delete-job" data-id="${j.id}">Delete</button></div></td></tr>`).join('')}</tbody></table></div></div>` : emptyState('JB','No jobs yet','Post a public role or target a specific institution for campus hiring.',`<button class="button button-primary" data-action="open-job-form">Post first job</button>`)}`;
    } else if (view === 'candidates') {
      setPage('Candidates','Recruiter workspace'); setContextAction();
      const students = await api('/recruiters/students/search');
      $('#app-content').innerHTML = `${pageHead('Candidate pipeline','Only candidates available under your deployment privacy policy are shown.')}${students.length ? `<div class="data-panel"><div class="data-toolbar"><input id="candidate-search" class="search-box" placeholder="Filter by name, college or skill"><span class="spacer"></span><span class="table-secondary">${students.length} accessible candidates</span></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Candidate</th><th>Education</th><th>CGPA</th><th>Skills</th><th></th></tr></thead><tbody id="candidate-body">${students.map(candidateRow).join('')}</tbody></table></div></div>` : emptyState('CD','No candidates in your pipeline','Candidates appear after they apply to one of your jobs. This is an intentional privacy control.')}`; state.lastCandidates=students;
    } else if (view === 'analytics') {
      setPage('Analytics','Recruiter insights'); setContextAction();
      const [a,e] = await Promise.all([api('/recruiters/analytics'),api('/enterprise/analytics/recruiter')]);
      const skillRows = e.skill_availability || (a.top_skills || []).map(x=>({skill:x.skill,candidates:x.count,coverage:a.total_applications?Math.round(x.count/a.total_applications*100):0}));
      const campuses = e.campus_comparison || [];
      $('#app-content').innerHTML = `${pageHead('Recruiter analytics','Pipeline conversion, capability supply and authorized campus-level hiring intelligence.')}
      <div class="metric-grid">${enterpriseMetric('Applications',e.applications,'Across your active and historical roles')}${enterpriseMetric('Qualified signals',e.qualified_candidates,'AI score ≥ 70; human review required')}${enterpriseMetric('Interview conversion',`${e.interview_conversion}%`,`${e.interviews} scheduled interview records`)}${enterpriseMetric('Offer conversion',`${e.offer_conversion}%`,`${e.offers} formal offers recorded`)}</div>
      ${featurePanel('Applicant capability snapshot','Ranked skill availability across candidates already inside your authorized pipeline.',skillRows.length?`<div class="skill-intelligence-grid">${skillRows.slice(0,8).map((item,i)=>{const coverage=Math.min(100,Math.round(item.coverage||0));const blocks=Math.max(1,Math.ceil(coverage/20));return `<article class="skill-intel-card"><div class="skill-intel-rank">${String(i+1).padStart(2,'0')}</div><div class="skill-intel-body"><strong>${esc(item.skill)}</strong><span>${item.candidates} candidate${item.candidates===1?'':'s'} · ${coverage}% pipeline coverage</span><div class="signal-meter" aria-label="${coverage}% pipeline coverage">${[1,2,3,4,5].map(n=>`<i class="${n<=blocks?'on':''}"></i>`).join('')}</div></div><b>${coverage}%</b></article>`}).join('')}</div>`:emptyState('SK','Not enough data','Capability intelligence will appear after candidates enter your pipeline.'))}
      ${featurePanel('Pipeline distribution','Current movement across recruiter-controlled stages.',Object.keys(e.pipeline||{}).length?`<div class="pipeline-summary-grid">${Object.entries(e.pipeline).map(([stage,count])=>`<article><span>${esc(stage.replaceAll('-',' '))}</span><strong>${count}</strong></article>`).join('')}</div>`:emptyState('PL','No stage activity','Move candidates through a drive pipeline to populate conversion intelligence.'))}
      ${featurePanel('Campus comparison','Visible only for campuses represented in your authorized applicant pipeline.',campuses.length?`<div class="campus-comparison-grid">${campuses.map(c=>`<article><div><strong>${esc(c.campus)}</strong><span>${c.applications} applications</span></div><dl><div><dt>Interview conversion</dt><dd>${c.interview_conversion}%</dd></div><div><dt>Offer conversion</dt><dd>${c.offer_conversion}%</dd></div></dl></article>`).join('')}</div>`:emptyState('CP','Single-campus or no campus data','Cross-campus comparison appears only when your own applicant pipeline contains multiple authorized campuses.'))}`;
    } else if (view === 'profile') {
      setPage('Company profile','Recruiter account'); setContextAction();
      const [p,trust] = await Promise.all([api('/recruiters/profile'),api('/recruiters/company-trust')]);
      $('#app-content').innerHTML = `${pageHead('Recruiter profile','Maintain accurate company evidence and contact information for institution review.')}
      <div class="profile-trust-layout"><form id="recruiter-profile-form" class="form-panel"><div class="profile-grid">${inputField('Full name','full_name',p.full_name)}${inputField('Designation','designation',p.designation)}${inputField('Company name','company_name',p.company_name)}${inputField('Industry','industry',p.industry)}${inputField('Company website','company_website',p.company_website,'url')}${inputField('LinkedIn URL','linkedin_url',p.linkedin_url,'url')}${inputField('Phone','phone',p.phone)}<div class="field-label">Verification status<div>${p.is_verified ? statusBadge('approved') : statusBadge('pending')}</div></div></div><div class="form-footer"><button class="button button-primary">Save company profile</button></div></form>${trustCard(trust)}</div>`;
    }
  }


  function trustCard(trust, compact = false) {
    const safe = trust || {score:0,level:'high_risk',label:'Not reviewed',checks:[],disclaimer:''};
    return `<section class="trust-card ${compact ? 'compact' : ''}"><div class="trust-score-wrap"><div class="trust-score trust-${esc(safe.level)}"><strong>${safe.score}</strong><span>/100</span></div><div><small>COMPANY TRUST REVIEW</small><h3>${esc(safe.label)}</h3><p>Evidence-based screening for placement teams.</p></div></div><div class="trust-check-list">${(safe.checks||[]).map(c=>`<div class="trust-check"><span class="trust-state trust-state-${esc(c.status)}">${c.status==='verified'?'✓':c.status==='partial'?'~':'!'}</span><div><strong>${esc(c.label)}</strong><small>${esc(c.detail)}</small></div><b>${c.earned}/${c.weight}</b></div>`).join('')}</div><p class="trust-disclaimer">${esc(safe.disclaimer)}</p></section>`;
  }

  async function openCompanyTrustReview(recruiterId) {
    const path = state.me?.role === 'institution_admin' ? `/institutions/recruiters/${recruiterId}/trust-review` : '/recruiters/company-trust';
    const trust = await api(path);
    openModal(`<span class="section-kicker">Company due diligence</span><h2>Company trust review</h2><p class="form-intro">Use this as an evidence checklist before allowing a recruiter or job into a campus pipeline.</p>${trustCard(trust,true)}<button class="button button-primary button-full" data-action="close-generic-modal">Done</button>`);
  }

  function candidateRow(s){return `<tr><td><span class="table-primary">${esc(s.full_name || 'Unnamed candidate')}</span><span class="table-secondary">${esc(s.college || '—')}</span></td><td>${esc(s.degree || '—')}<span class="table-secondary">${esc(s.branch || '')} · ${s.graduation_year || '—'}</span></td><td>${s.cgpa ?? '—'}</td><td>${tags(s.skills)}</td><td><button class="row-button primary" data-action="view-candidate" data-id="${s.id}">Open profile</button></td></tr>`}

  async function renderInstitution(view) {
    if (view === 'institution-access-requests') {
      setPage('Access requests','Institution access'); setContextAction();
      const rows = await api('/institutions/access-requests');
      const manualStatuses = ['new', 'under_review', 'approved', 'rejected'];
      const statusControl = row => row.status === 'provisioned'
        ? `<span class="status-badge status-approved">provisioned</span><span class="table-secondary">Account already provisioned</span>`
        : `<select class="form-control" data-institution-access-status data-id="${esc(row.id)}" data-current-status="${esc(row.status)}" aria-label="Access request status for ${esc(row.full_name)}">${manualStatuses.map(status => `<option value="${status}" ${status === row.status ? 'selected' : ''}>${status.replaceAll('_',' ')}</option>`).join('')}</select>`;
      $('#app-content').innerHTML = `${pageHead('Recruiter access requests','Review recruiter workspace requests linked only to your institution. Platform and Institution Admin requests remain under Platform Admin control.')}${rows.length ? `<div class="data-panel"><div class="data-toolbar"><span class="table-secondary">${rows.length} institution-scoped request${rows.length === 1 ? '' : 's'}</span></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Requester</th><th>Organization</th><th>Context</th><th>Received</th><th>Status / action</th></tr></thead><tbody>${rows.map(row => `<tr><td><span class="table-primary">${esc(row.full_name)}</span><span class="table-secondary">${esc(row.work_email)}</span>${row.phone ? `<span class="table-secondary">${esc(row.phone)}</span>` : ''}</td><td>${esc(row.organization_name || '—')}</td><td>${esc(row.message || 'No access context provided.')}</td><td>${fmtDate(row.created_at)}</td><td>${statusControl(row)}</td></tr>`).join('')}</tbody></table></div></div>` : emptyState('AR','No recruiter access requests','Recruiter requests linked to this institution will appear here for placement-office review.')}`;
      return;
    }
    if (['attention','analytics2','approvals','verification','pipeline','interviews','offers','attendance','calendar','announcements','communications','policies','custom-fields','incidents','reports'].includes(view)) return renderInstitutionEnterprise(view);
    if (view === 'dashboard') {
      setPage('Overview','Placement command centre'); setContextAction('Add student','open-student-form');
      const d = await api('/institutions/dashboard');
      $('#workspace-name').textContent = d.organization.name;
      $('#workspace-name').title = d.organization.name;
      $('#workspace-avatar').textContent = initials(d.organization.name);
      $('#app-content').innerHTML = `${pageHead(`${d.organization.name} placement office`,'Operational view of student readiness, campus jobs, applications and outcomes.','Add student','open-student-form')}
      <div class="metric-grid"><article class="metric-card"><small>Students</small><strong>${d.total_students}</strong><span>${d.verified_students} institution verified</span></article><article class="metric-card"><small>Active campus jobs</small><strong>${d.active_jobs}</strong><span>${d.open_drives} open placement drives</span></article><article class="metric-card"><small>Applications</small><strong>${d.total_applications}</strong><span>${d.offers} offers recorded</span></article><article class="metric-card"><small>Placement rate</small><strong>${d.placement_rate}%</strong><span class="${d.hires ? 'metric-good':''}">${d.hires} hires recorded</span></article></div>
      <div class="dashboard-grid"><section class="panel"><div class="panel-head"><div><h2>Placement operating model</h2><p>Every campus opportunity follows the same controlled flow</p></div></div><div class="activity-list"><div class="activity-item"><span class="activity-icon">01</span><div><strong>Recruiter publishes campus opportunity</strong><small>Job remains pending until your placement team reviews it.</small></div><span>Controlled</span></div><div class="activity-item"><span class="activity-icon">02</span><div><strong>TPO approves and creates a drive</strong><small>CGPA, branch and batch criteria are configured once.</small></div><span>Auditable</span></div><div class="activity-item"><span class="activity-icon">03</span><div><strong>Eligible students apply</strong><small>Students see eligibility before submission.</small></div><span>Clear</span></div><div class="activity-item"><span class="activity-icon">04</span><div><strong>Recruiter moves outcomes</strong><small>Shortlist, interview, offer and hire stages feed institutional analytics.</small></div><span>Measured</span></div></div></section><section class="panel"><div class="panel-head"><div><h2>Institution identity</h2><p>Tenant scope used across placement records</p></div></div><div class="ai-box"><div class="ai-box-head"><span>INSTITUTION CODE</span><strong>${esc(d.organization.slug)}</strong></div><p>Students may use this code during self-registration to join your institution, subject to verification by the placement team.</p></div></section></div>`;
    } else if (view === 'students') {
      setPage('Students','Institution records'); setContextAction('Add student','open-student-form');
      const students = await api('/institutions/students'); state.lastStudents=students;
      $('#app-content').innerHTML = `${pageHead('Student records','Verify academic profiles used for campus eligibility.','Add student','open-student-form')}${students.length ? `<div class="data-panel"><div class="data-toolbar"><input id="institution-student-search" class="search-box" placeholder="Search name, branch, skill"><span class="spacer"></span><a class="row-button" href="/static/student-import-template.csv" download="placeai-student-import-template.csv">CSV template</a><label class="row-button primary">Import CSV<input id="student-csv-file" type="file" accept=".csv,text/csv" hidden></label><button class="row-button" data-action="export-students">Export CSV</button></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Student</th><th>Program</th><th>Batch</th><th>CGPA</th><th>Skills</th><th>Verified</th><th></th></tr></thead><tbody id="institution-student-body">${students.map(institutionStudentRow).join('')}</tbody></table></div></div>` : emptyState('ST','No student records','Add your first student or import a CSV batch using the provided template.',`<div class="row-actions"><button class="button button-primary" data-action="open-student-form">Add student</button><label class="button button-secondary">Import CSV<input id="student-csv-file" type="file" accept=".csv,text/csv" hidden></label></div>`)}`;
    } else if (view === 'recruiters') {
      setPage('Recruiters','Institution access'); setContextAction('Provision recruiter','open-recruiter-form');
      const recruiters = await api('/institutions/recruiters');
      $('#app-content').innerHTML = `${pageHead('Recruiter partners','Recruiters linked to campus opportunities for your institution.','Provision recruiter','open-recruiter-form')}${recruiters.length ? `<div class="data-panel"><div class="table-wrap"><table class="data-table"><thead><tr><th>Recruiter</th><th>Company</th><th>Industry</th><th>Verification</th><th>Evidence</th></tr></thead><tbody>${recruiters.map(r => `<tr><td><span class="table-primary">${esc(r.full_name || 'Recruiter')}</span><span class="table-secondary">${esc(r.designation || '')}</span></td><td>${esc(r.company_name || '—')}</td><td>${esc(r.industry || '—')}</td><td>${r.is_verified ? statusBadge('approved') : statusBadge('pending')}</td><td><button class="row-button" data-action="company-trust-review" data-id="${r.id}">Trust review</button></td></tr>`).join('')}</tbody></table></div></div>` : emptyState('RC','No campus recruiters yet','Provision a recruiter account, then they can publish a campus job targeted to your institution.')}`;
    } else if (view === 'jobs') {
      setPage('Campus jobs','Placement approvals'); setContextAction();
      const jobs = await api('/institutions/jobs'); state.lastInstitutionJobs=jobs;
      $('#app-content').innerHTML = `${pageHead('Campus job approvals','Review recruiter-created opportunities before they are exposed to students.')}${jobs.length ? `<div class="data-panel"><div class="table-wrap"><table class="data-table"><thead><tr><th>Role</th><th>Company</th><th>Skills</th><th>Approval</th><th>Applications</th><th></th></tr></thead><tbody>${jobs.map(j => `<tr><td><span class="table-primary">${esc(j.title)}</span><span class="table-secondary">${esc(j.location || '')} · ${esc(j.job_type || '')}</span></td><td>${esc(j.company_name || '—')}</td><td>${tags(j.required_skills)}</td><td>${statusBadge(j.approval_status)}</td><td>${j.application_count}</td><td><div class="row-actions">${j.approval_status === 'pending' ? `<button class="row-button primary" data-action="approve-job" data-id="${j.id}">Approve</button><button class="row-button" data-action="reject-job" data-id="${j.id}">Reject</button>` : j.approval_status === 'approved' ? `<button class="row-button primary" data-action="open-drive-form" data-id="${j.id}">Create drive</button>`:''}</div></td></tr>`).join('')}</tbody></table></div></div>` : emptyState('JB','No campus jobs awaiting your team','Campus jobs appear after a verified recruiter targets your institution code.')}`;
    } else if (view === 'drives') {
      setPage('Placement drives','Campus operations'); setContextAction();
      const drives = await api('/institutions/drives');
      $('#app-content').innerHTML = `${pageHead('Placement drives','Configure and monitor eligibility-controlled campus hiring events.')}${drives.length ? `<div class="data-panel"><div class="table-wrap"><table class="data-table"><thead><tr><th>Drive</th><th>Company / role</th><th>Eligibility</th><th>Eligible students</th><th>Event</th><th>Status</th></tr></thead><tbody>${drives.map(d => `<tr><td><span class="table-primary">${esc(d.title)}</span><span class="table-secondary">Created ${fmtDate(d.created_at)}</span></td><td>${esc(d.company_name || '—')}<span class="table-secondary">${esc(d.job_title || '')}</span></td><td>CGPA ${d.min_cgpa ?? 'Any'}<span class="table-secondary">${esc((d.allowed_branches || []).join(', ') || 'All branches')} · ${esc((d.allowed_graduation_years || []).join(', ') || 'All batches')}</span></td><td>${d.eligible_students}</td><td>${fmtDate(d.event_date)}</td><td>${statusBadge(d.status)}</td></tr>`).join('')}</tbody></table></div></div>` : emptyState('DR','No placement drives','Approve a campus job first, then create a placement drive from that job.')}`;
    } else if (view === 'applications') {
      setPage('Applications','Institution outcomes'); setContextAction();
      const apps = await api('/institutions/applications');
      $('#app-content').innerHTML = `${pageHead('Campus application outcomes','Institution-level visibility into recruiter-managed application stages.')}${apps.length ? `<div class="data-panel"><div class="table-wrap"><table class="data-table"><thead><tr><th>Student</th><th>Role</th><th>Company</th><th>Applied</th><th>AI match</th><th>Status</th></tr></thead><tbody>${apps.map(a => `<tr><td><span class="table-primary">${esc(a.student?.full_name || 'Student')}</span><span class="table-secondary">${esc(a.student?.college || '')}</span></td><td>${esc(a.job_title || '—')}</td><td>${esc(a.company_name || '—')}</td><td>${fmtDate(a.applied_at)}</td><td>${a.ai_match_score != null ? Math.round(a.ai_match_score) : '—'}</td><td>${statusBadge(a.status)}</td></tr>`).join('')}</tbody></table></div></div>` : emptyState('AP','No campus applications yet','Applications will populate after an approved drive opens and eligible students apply.')}`;
    } else if (view === 'audit') {
      setPage('Audit log','Governance'); setContextAction();
      const events = await api('/institutions/audit');
      $('#app-content').innerHTML = `${pageHead('Institution audit log','Recent security and placement workflow events scoped to this institution.')}${events.length ? `<div class="data-panel"><div class="table-wrap"><table class="data-table"><thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Entity</th><th>Details</th></tr></thead><tbody>${events.map(ev => `<tr><td>${fmtDate(ev.created_at)}<span class="table-secondary">${new Date(ev.created_at).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}</span></td><td>${esc(ev.actor_email || 'System')}</td><td><span class="table-primary">${esc(ev.action.replaceAll('.',' › '))}</span></td><td>${esc(ev.entity_type || '—')}</td><td><span class="table-secondary">${esc(Object.entries(ev.metadata || {}).map(([k,v]) => `${k}: ${v}`).join(' · ') || '—')}</span></td></tr>`).join('')}</tbody></table></div></div>` : emptyState('AU','No audit events yet','Critical placement and account actions will be recorded here.')}`;
    }
  }

  function institutionStudentRow(s){return `<tr><td><span class="table-primary">${esc(s.full_name || 'Unnamed student')}</span><span class="table-secondary">${esc(s.college || '')}</span></td><td>${esc(s.degree || '—')}<span class="table-secondary">${esc(s.branch || '')}</span></td><td>${s.graduation_year || '—'}</td><td>${s.cgpa ?? '—'}</td><td>${tags(s.skills)}</td><td>${s.is_verified ? statusBadge('approved') : statusBadge('pending')}</td><td><button class="row-button ${s.is_verified ? '' : 'primary'}" data-action="toggle-student-verify" data-id="${s.id}" data-value="${s.is_verified ? 'false':'true'}">${s.is_verified ? 'Unverify':'Verify'}</button></td></tr>`}


  function platformRegistrationDetailHtml(d) {
    const p=d.profile||{}, a=d.activity||{};
    const value=v=>v===null||v===undefined||v===''?'—':Array.isArray(v)?(v.length?v.map(esc).join(', '):'—'):typeof v==='boolean'?(v?'Yes':'No'):esc(v);
    const row=(label,v)=>`<tr><th>${esc(label)}</th><td>${value(v)}</td></tr>`;
    let profileRows='';
    if(p.profile_type==='student'){
      profileRows=[
        ['College',p.college],['Phone',p.phone],['Degree',p.degree],['Branch',p.branch],['Graduation year',p.graduation_year],['CGPA',p.cgpa],
        ['Skills',p.skills],['Desired roles',p.desired_roles],['Placement status',p.placement_status],['Placement opt-in',p.placement_opt_in],
        ['Profile verified',p.is_verified],['10th %',p.tenth_percentage],['12th %',p.twelfth_percentage],['Active backlogs',p.active_backlogs],
        ['Historical backlogs',p.historical_backlogs],['LinkedIn',p.linkedin_url],['GitHub',p.github_url],['Portfolio',p.portfolio_url]
      ].map(([k,v])=>row(k,v)).join('');
    }else if(p.profile_type==='recruiter'){
      profileRows=[
        ['Company',p.company_name],['Designation',p.designation],['Phone',p.phone],['Industry',p.industry],['Website',p.company_website],
        ['LinkedIn',p.linkedin_url],['Verified',p.is_verified],['Verification status',p.verification_status],
        ['Verification confidence',p.verification_confidence!=null?`${p.verification_confidence}%`:null],['Official email domain',p.official_email_domain]
      ].map(([k,v])=>row(k,v)).join('');
    }else{
      profileRows=[
        ['Institution',p.organization_name],['Institution code',p.organization_slug],['Domain',p.domain],['Website',p.website],
        ['City',p.city],['State',p.state],['Country',p.country],['Institution active',p.organization_active]
      ].map(([k,v])=>row(k,v)).join('');
    }
    const activityRows=[
      ['Active sessions',a.active_sessions],['Mock interview attempts',a.mock_interview_attempts],['Mock interviews evaluated',a.mock_interviews_evaluated],
      ['Last mock interview',a.last_mock_interview_at?fmtDateTime(a.last_mock_interview_at):null],['Last mock score',a.last_mock_score],
      ['Applications',a.applications],['Resume uploaded',a.resume_uploaded],['Resume AI parsed',a.resume_parsed],
      ['Resume uploaded at',a.resume_uploaded_at?fmtDateTime(a.resume_uploaded_at):null],['Jobs created',a.jobs_created]
    ].map(([k,v])=>row(k,v)).join('');
    return `<span class="section-kicker">Platform registration</span><h2>${esc(d.name||d.email)}</h2><p class="form-intro">${esc(d.role.replaceAll('_',' '))} · ${esc(d.email)}</p>
      <div class="data-panel"><div class="table-wrap"><table class="data-table"><tbody>
      ${row('Username',d.username)}${row('Organization / company',d.organization)}${row('Registered',fmtDateTime(d.registered_at))}
      ${row('Last login',d.last_login_at?fmtDateTime(d.last_login_at):'Never')}${row('Account active',d.is_active)}${row('Email verified',d.email_verified)}
      </tbody></table></div></div>
      <div class="data-panel"><div class="data-toolbar"><div><span class="table-primary">Profile details</span><span class="table-secondary">Role-specific account information stored by PlaceAI.</span></div></div><div class="table-wrap"><table class="data-table"><tbody>${profileRows||row('Profile','No additional profile record')}</tbody></table></div></div>
      <div class="data-panel"><div class="data-toolbar"><div><span class="table-primary">Activity</span><span class="table-secondary">Operational usage linked to this account.</span></div></div><div class="table-wrap"><table class="data-table"><tbody>${activityRows}</tbody></table></div></div>
      <div class="ai-box"><div class="ai-box-head"><span>SECURITY BOUNDARY</span></div><p>${esc(d.security_note||'Authentication secrets are not exposed.')}</p></div>`;
  }

  async function renderPlatform(view) {
    if (view === 'dashboard') {
      setPage('Overview','Platform control'); setContextAction('Add institution','open-org-form');
      const o=await api('/platform/overview');
      $('#app-content').innerHTML = `${pageHead('Platform overview','Tenant and controlled-access operating metrics.','Add institution','open-org-form')}<div class="metric-grid"><article class="metric-card"><small>Institutions</small><strong>${o.organizations}</strong><span>Active platform tenants</span></article><article class="metric-card"><small>Students</small><strong>${o.students}</strong><span>Registered student users</span></article><article class="metric-card"><small>Recruiters</small><strong>${o.recruiters}</strong><span>Controlled recruiter accounts</span></article><article class="metric-card"><small>Active jobs</small><strong>${o.active_jobs}</strong><span>${o.applications} applications recorded</span></article><article class="metric-card"><small>Access requests</small><strong>${o.access_requests}</strong><span>Privileged workspace requests awaiting review</span></article></div>`;
    } else if (view === 'organizations') {
      setPage('Institutions','Platform control'); setContextAction('Add institution','open-org-form');
      const orgs=await api('/platform/organizations'); state.orgs=orgs;
      $('#app-content').innerHTML=`${pageHead('Institutions','Create and manage institution tenants.','Add institution','open-org-form')}${orgs.length?`<div class="data-panel"><div class="table-wrap"><table class="data-table"><thead><tr><th>Institution</th><th>Code</th><th>Location</th><th>Status</th><th></th></tr></thead><tbody>${orgs.map(o=>`<tr><td><span class="table-primary">${esc(o.name)}</span><span class="table-secondary">${esc(o.website||o.domain||'')}</span></td><td><span class="skill-tag">${esc(o.slug)}</span></td><td>${esc([o.city,o.state].filter(Boolean).join(', ')||'—')}</td><td>${o.is_active?statusBadge('approved'):statusBadge('rejected')}</td><td><button class="row-button primary" data-action="open-admin-form" data-id="${o.slug}">Create TPO admin</button></td></tr>`).join('')}</tbody></table></div></div>`:emptyState('IN','No institutions yet','Create the first institution tenant and provision its placement administrator.')}`;
    } else if (view === 'leads') {
      setPage('Access requests','Platform control'); setContextAction();
      const rows = await api('/platform/access-requests');
      const manualStatuses = ['new', 'under_review', 'approved', 'rejected'];
      const actionCell = row => {
        if (row.status === 'provisioned') {
          const resend = row.requested_role === 'recruiter'
            ? `<button class="row-button primary" data-action="platform-provision-recruiter" data-id="${esc(row.id)}" data-email="${esc(row.work_email)}" data-resend="true">Resend password setup link</button>`
            : '';
          return `<span class="status-badge status-approved">provisioned</span>${resend ? `<div class="row-actions access-action-row">${resend}</div>` : ''}`;
        }
        const select = `<select class="form-control" data-platform-access-status data-id="${esc(row.id)}" data-current-status="${esc(row.status)}" aria-label="Access request status for ${esc(row.full_name)}">${manualStatuses.map(status => `<option value="${status}" ${status === row.status ? 'selected' : ''}>${status.replaceAll('_',' ')}</option>`).join('')}</select>`;
        const provision = row.requested_role === 'recruiter' && row.status === 'approved'
          ? `<button class="row-button primary" data-action="platform-provision-recruiter" data-id="${esc(row.id)}" data-email="${esc(row.work_email)}">Provision recruiter</button>`
          : '';
        return `${select}${provision ? `<div class="row-actions access-action-row">${provision}</div>` : ''}`;
      };
      $('#app-content').innerHTML = `${pageHead('Access requests','Privileged workspace access requests stored in the production database.')}${rows.length ? `<div class="data-panel"><div class="data-toolbar"><span class="table-secondary">${rows.length} request${rows.length === 1 ? '' : 's'}</span></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Requester</th><th>Role</th><th>Organization</th><th>Context</th><th>Received</th><th>Status / action</th></tr></thead><tbody>${rows.map(r => `<tr><td><span class="table-primary">${esc(r.full_name)}</span><span class="table-secondary">${esc(r.work_email)}${r.phone ? ` · ${esc(r.phone)}` : ''}</span></td><td>${esc(r.requested_role.replaceAll('_',' '))}</td><td>${esc(r.organization_name || '—')}</td><td>${esc(r.message || 'No access context provided.')}</td><td>${fmtDate(r.created_at)}</td><td>${actionCell(r)}</td></tr>`).join('')}</tbody></table></div></div>` : emptyState('AR','No access requests','Privileged workspace requests will appear here when submitted.')}`;
    } else if (view === 'registrations') {
      setPage('Registrations','Platform control'); setContextAction();
      const role=state.platformRegistrationRole||'';
      const data=await api(`/platform/registrations?limit=200${role?`&role=${encodeURIComponent(role)}`:''}`);
      const s=data.summary||{};
      const roleOptions=[['','All roles'],['student','Students'],['recruiter','Recruiters'],['institution_admin','Institution admins'],['platform_admin','Platform admins']];
      $('#app-content').innerHTML=`${pageHead('Registrations & accounts','Platform-admin-only directory of registered PlaceAI accounts, login status and role-specific activity.')}
        <div class="metric-grid">
          <article class="metric-card"><small>All accounts</small><strong>${s.all_accounts||0}</strong><span>Registered PlaceAI users</span></article>
          <article class="metric-card"><small>Students</small><strong>${s.students||0}</strong><span>Student accounts</span></article>
          <article class="metric-card"><small>Recruiters</small><strong>${s.recruiters||0}</strong><span>Recruiter accounts</span></article>
          <article class="metric-card"><small>Institution admins</small><strong>${s.institution_admins||0}</strong><span>Placement-office administrators</span></article>
        </div>
        <div class="data-panel"><div class="data-toolbar"><div><span class="table-primary">Registered users</span><span class="table-secondary">Showing ${data.items.length} of ${data.total} records. Passwords and authentication secrets are never exposed.</span></div><label class="table-secondary">Role <select class="form-control" id="platform-registration-role">${roleOptions.map(([v,l])=>`<option value="${v}" ${v===role?'selected':''}>${l}</option>`).join('')}</select></label></div>
        <div class="table-wrap"><table class="data-table"><thead><tr><th>Person / account</th><th>Role</th><th>Organization</th><th>Registered</th><th>Last login</th><th>Usage</th><th>Status</th><th></th></tr></thead><tbody>
        ${data.items.map(r=>{const a=r.activity||{};const usage=r.role==='student'?`${a.mock_interview_attempts||0} mock · ${a.applications||0} applications · ${a.resume_uploaded?'resume uploaded':'no resume'}`:r.role==='recruiter'?`${a.jobs_created||0} jobs · ${a.active_sessions||0} active sessions`:`${a.active_sessions||0} active sessions`;return `<tr><td><span class="table-primary">${esc(r.name||r.username||r.email)}</span><span class="table-secondary">${esc(r.email)} · @${esc(r.username)}</span></td><td>${esc(r.role.replaceAll('_',' '))}</td><td>${esc(r.organization||'—')}</td><td>${fmtDate(r.registered_at)}</td><td>${r.last_login_at?fmtDateTime(r.last_login_at):'Never'}</td><td>${esc(usage)}</td><td>${r.is_active?statusBadge('approved'):statusBadge('rejected')}</td><td><button class="row-button primary" data-action="view-platform-registration" data-id="${esc(r.id)}">View details</button></td></tr>`;}).join('')}
        </tbody></table></div></div>`;
    } else if (view === 'engagement') {
      setPage('Engagement','Platform control'); setContextAction();
      const days=Number(state.platformEngagementDays||30);
      const e=await api(`/platform/engagement?days=${days}`), s=e.summary||{};
      const periods=[7,30,90];
      $('#app-content').innerHTML=`${pageHead('Visitors & engagement','Privacy-safe first-party usage analytics for PlaceAI. No IP addresses, fingerprints, passwords or full referrer URLs are collected.')}
        <div class="data-panel"><div class="data-toolbar"><div><span class="table-primary">Period</span><span class="table-secondary">Tracking started ${e.tracking_since?fmtDateTime(e.tracking_since):'with this release'}.</span></div><div>${periods.map(n=>`<button class="row-button ${days===n?'primary':''}" data-action="platform-engagement-period" data-id="${n}">${n} days</button>`).join(' ')}</div></div></div>
        <div class="metric-grid">
          <article class="metric-card"><small>Page views</small><strong>${s.page_views||0}</strong><span>Recorded page views</span></article>
          <article class="metric-card"><small>Unique visitors</small><strong>${s.unique_visitors||0}</strong><span>Anonymous random visitor IDs, hashed server-side</span></article>
          <article class="metric-card"><small>Signed-in users seen</small><strong>${s.signed_in_users_seen||0}</strong><span>Authenticated users with tracked views</span></article>
          <article class="metric-card"><small>New registrations</small><strong>${s.registrations||0}</strong><span>Accounts created in this period</span></article>
          <article class="metric-card"><small>Mock interviews</small><strong>${s.mock_interviews||0}</strong><span>Student practice sessions created</span></article>
          <article class="metric-card"><small>Applications</small><strong>${s.applications||0}</strong><span>Applications submitted</span></article>
        </div>
        <div class="data-panel"><div class="data-toolbar"><div><span class="table-primary">Most visited pages</span><span class="table-secondary">${esc(e.note||'')}</span></div></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Page / workspace view</th><th>Views</th><th>Unique visitors</th></tr></thead><tbody>${e.top_pages.length?e.top_pages.map(x=>`<tr><td><span class="table-primary">${esc(x.path)}</span></td><td>${x.views}</td><td>${x.visitors}</td></tr>`).join(''):'<tr><td colspan="3">No page-view telemetry recorded yet.</td></tr>'}</tbody></table></div></div>
        <div class="data-panel"><div class="data-toolbar"><div><span class="table-primary">Daily traffic</span><span class="table-secondary">Views and unique visitors by day.</span></div></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Date</th><th>Views</th><th>Visitors</th></tr></thead><tbody>${e.daily.length?e.daily.map(x=>`<tr><td>${esc(x.date)}</td><td>${x.views}</td><td>${x.visitors}</td></tr>`).join(''):'<tr><td colspan="3">No traffic recorded in this period.</td></tr>'}</tbody></table></div></div>
        <div class="data-panel"><div class="data-toolbar"><div><span class="table-primary">Active registered users</span><span class="table-secondary">Accounts whose latest successful login falls inside this period.</span></div></div><div class="table-wrap"><table class="data-table"><tbody><tr><th>Students</th><td>${s.students_active||0}</td><th>Recruiters</th><td>${s.recruiters_active||0}</td></tr><tr><th>Institution admins</th><td>${s.institution_admins_active||0}</td><th>Resumes uploaded</th><td>${s.resumes_uploaded||0}</td></tr></tbody></table></div></div>`;
    } else if (view === 'integrations') {
      setPage('Integrations','Platform control'); setContextAction();
      const [summary, reset] = await Promise.all([api('/platform/integrations/status'), api('/platform/integrations/password-reset-email')]);
      const resetLabel = String(reset.status || 'unknown').replaceAll('_',' ');
      const safeBool = value => value ? statusBadge('approved') : statusBadge('pending');
      $('#app-content').innerHTML = `${pageHead('Integrations','Production integration readiness and privacy-safe delivery telemetry.')}<div class="metric-grid"><article class="metric-card"><small>Database</small><strong>${summary.database ? 'Connected' : 'Not ready'}</strong><span>Persistent production data</span></article><article class="metric-card"><small>Brevo SMTP</small><strong>${summary.brevo_smtp ? 'Configured' : 'Not ready'}</strong><span>Transactional email transport</span></article><article class="metric-card"><small>Password reset email</small><strong>${esc(resetLabel)}</strong><span>${reset.successes_24h} successful / ${reset.failures_24h} failed in 24h</span></article><article class="metric-card"><small>Gemini</small><strong>${summary.gemini ? 'Configured' : 'Not configured'}</strong><span>AI provider readiness</span></article></div><div class="data-panel"><div class="data-toolbar"><div><span class="table-primary">Password recovery delivery health</span><span class="table-secondary">Aggregate operational telemetry only. Recipient addresses, reset tokens and SMTP secrets are never displayed or stored in this telemetry.</span></div></div><div class="table-wrap"><table class="data-table"><tbody><tr><th>SMTP transport</th><td>${safeBool(reset.smtp_transport_configured)}</td><th>TLS</th><td>${safeBool(reset.tls_enabled)}</td></tr><tr><th>SMTP authentication</th><td>${reset.smtp_authentication_enabled ? safeBool(reset.smtp_authentication_configured) : 'Not required by transport'}</td><th>HTTPS reset links</th><td>${safeBool(reset.base_url_https)}</td></tr><tr><th>Attempts (24h)</th><td>${reset.attempts_24h}</td><th>Not configured (24h)</th><td>${reset.not_configured_24h}</td></tr><tr><th>Last success</th><td>${reset.last_success_at ? fmtDate(reset.last_success_at) : 'None recorded'}</td><th>Last failure</th><td>${reset.last_failure_at ? fmtDate(reset.last_failure_at) : 'None recorded'}</td></tr></tbody></table></div></div>`;

    }
  }

  function inputField(label,name,value,type='text',min='',max='',step='') { return `<label class="field-label">${esc(label)}<input class="field-input" type="${type}" name="${name}" value="${esc(value ?? '')}" ${min!==''?`min="${min}"`:''} ${max!==''?`max="${max}"`:''} ${step!==''?`step="${step}"`:''}></label>`; }
  function customFieldControl(def,value=''){ const name=`custom__${def.field_key}`; const req=def.required?'required':''; if(def.field_type==='select') return `<label class="field-label">${esc(def.label)}${def.required?' *':''}<select class="field-input" name="${esc(name)}" ${req}><option value="">Select…</option>${(def.options||[]).map(x=>`<option value="${esc(x)}" ${String(value)===String(x)?'selected':''}>${esc(x)}</option>`).join('')}</select></label>`; if(def.field_type==='boolean') return `<label class="field-label custom-boolean"><span>${esc(def.label)}${def.required?' *':''}</span><select class="field-input" name="${esc(name)}" ${req}><option value="">Select…</option><option value="Yes" ${String(value).toLowerCase()==='yes'?'selected':''}>Yes</option><option value="No" ${String(value).toLowerCase()==='no'?'selected':''}>No</option></select></label>`; return `<label class="field-label">${esc(def.label)}${def.required?' *':''}<input class="field-input" type="${def.field_type==='number'?'number':'text'}" name="${esc(name)}" value="${esc(value ?? '')}" ${req}></label>`; }

  function openJobForm() {
    openModal(`<span class="section-kicker">Recruiter workflow</span><h2>Post a job</h2><p class="form-intro">Public jobs are immediately visible. Campus jobs require the target institution to approve them.</p><form id="job-form" class="form-stack"><label>Role title<input name="title" required minlength="3"></label><label>Job description<textarea name="description" rows="5" required minlength="20"></textarea></label><div class="form-two"><label>Location<input name="location"></label><label>Job type<select name="job_type"><option>Full-time</option><option>Internship</option><option>Part-time</option></select></label></div><div class="form-two"><label>Salary range<input name="salary_range" placeholder="e.g. ₹7–9 LPA"></label><label>Experience required<input name="experience_required" placeholder="e.g. Fresher / 0–1 years"></label></div><label>Required skills<input name="required_skills" placeholder="Python, SQL, FastAPI"></label><label>Preferred roles<input name="preferred_roles" placeholder="Backend Developer, Software Engineer"></label><div class="form-two"><label>Visibility<select name="visibility" id="job-visibility"><option value="public">Public</option><option value="campus">Campus only</option></select></label><label>Target institution code<input name="target_organization_slug" id="target-org" placeholder="Required for campus jobs"></label></div><label>Application deadline<input name="deadline" type="datetime-local"></label><button class="button button-primary button-full">Publish job</button></form>`);
  }

  function openStudentForm() { openModal(`<span class="section-kicker">Institution records</span><h2>Add student</h2><p class="form-intro">Create an institution-linked student account with a temporary password.</p><form id="institution-student-form" class="form-stack"><div class="form-two"><label>Full name<input name="full_name" required></label><label>Username<input name="username" required></label></div><label>Email<input name="email" type="email" required></label><label>Temporary password<input name="temporary_password" type="password" minlength="12" required></label><div class="form-two"><label>Degree<input name="degree"></label><label>Branch<input name="branch"></label></div><div class="form-two"><label>Graduation year<input name="graduation_year" type="number"></label><label>CGPA<input name="cgpa" type="number" min="0" max="10" step="0.01"></label></div><button class="button button-primary button-full">Create student account</button></form>`); }
  function openRecruiterForm() { openModal(`<span class="section-kicker">Controlled recruiter access</span><h2>Provision recruiter</h2><p class="form-intro">Recruiter accounts created by the placement office are verified immediately.</p><form id="institution-recruiter-form" class="form-stack"><div class="form-two"><label>Full name<input name="full_name"></label><label>Company<input name="company_name" required></label></div><div class="form-two"><label>Username<input name="username" required></label><label>Email<input name="email" type="email" required></label></div><label>Temporary password<input name="temporary_password" type="password" minlength="12" required></label><button class="button button-primary button-full">Provision verified recruiter</button></form>`); }
  function openDriveForm(jobId) { const job=(state.lastInstitutionJobs||[]).find(x=>x.id===jobId); openModal(`<span class="section-kicker">Placement operation</span><h2>Create placement drive</h2><p class="form-intro">${esc(job?.company_name||'Recruiter')} · ${esc(job?.title||'Campus job')}</p><form id="drive-form" class="form-stack enterprise-form"><input type="hidden" name="job_id" value="${jobId}"><label>Drive title<input name="title" required value="${esc(job?.company_name||'')} ${esc(job?.title||'')} Drive"></label><div class="form-two"><label>Minimum CGPA<input name="min_cgpa" type="number" min="0" max="10" step="0.01"></label><label>Status<select name="status"><option value="open">Open</option><option value="draft">Draft</option></select></label></div><div class="form-three"><label>10th minimum %<input name="min_tenth_percentage" type="number" min="0" max="100" step="0.01"></label><label>12th minimum %<input name="min_twelfth_percentage" type="number" min="0" max="100" step="0.01"></label><label>Diploma minimum %<input name="min_diploma_percentage" type="number" min="0" max="100" step="0.01"></label></div><div class="form-three"><label>Max active backlogs<input name="max_active_backlogs" type="number" min="0"></label><label>Max historical backlogs<input name="max_historical_backlogs" type="number" min="0"></label><label>Max academic gap (months)<input name="max_academic_gap_months" type="number" min="0"></label></div><label>Eligible graduation years<input name="allowed_graduation_years" placeholder="2026, 2027"></label><label>Eligible branches<input name="allowed_branches" placeholder="Computer Science, IT, ECE"></label><label>Required skills<input name="required_skills" placeholder="Python, SQL, Java"></label><label>Required certifications<input name="required_certifications" placeholder="AWS Cloud Practitioner, NPTEL Java"></label><label>Required documents<input name="required_documents" placeholder="resume, marksheet, transcript"></label><div class="form-two"><label>Work authorization requirement<input name="work_authorization_required" placeholder="e.g. India"></label><label class="check-label enterprise-checkbox"><input type="checkbox" name="allow_placed_students" checked> Allow already-placed students</label></div><div class="form-two"><label>Registration deadline<input name="registration_deadline" type="datetime-local"></label><label>Event date<input name="event_date" type="datetime-local"></label></div><label>Custom eligibility rules <span class="optional">JSON, optional</span><textarea name="custom_eligibility_rules" rows="3" placeholder='{"max_offers": 1}'></textarea></label><label>Notes<textarea name="notes" rows="3"></textarea></label><div class="note-box"><strong>Explainable eligibility</strong><p>Students will see exactly which rule they meet or fail. A standard 8-stage placement pipeline is created automatically.</p></div><button class="button button-primary button-full">Create placement drive</button></form>`); }
  function openOrgForm(){openModal(`<span class="section-kicker">Platform administration</span><h2>Create institution</h2><form id="org-form" class="form-stack"><label>Institution name<input name="name" required></label><label>Institution code / slug<input name="slug" required placeholder="e.g. campus-main"></label><div class="form-two"><label>City<input name="city"></label><label>State<input name="state"></label></div><label>Website<input name="website" type="url"></label><button class="button button-primary button-full">Create institution</button></form>`)}
  function openAdminForm(slug){openModal(`<span class="section-kicker">Platform administration</span><h2>Create TPO administrator</h2><p class="form-intro">Institution code: ${esc(slug)}</p><form id="admin-form" class="form-stack"><input type="hidden" name="organization_slug" value="${esc(slug)}"><div class="form-two"><label>Full name<input name="full_name"></label><label>Username<input name="username" required></label></div><label>Email<input name="email" type="email" required></label><label>Temporary password<input name="temporary_password" type="password" minlength="12" required></label><button class="button button-primary button-full">Create institution admin</button></form>`)}

  async function viewApplicants(jobId){ const apps=await api(`/jobs/${jobId}/applicants`); const job=(state.lastJobs||[]).find(x=>x.id===jobId); openModal(`<span class="section-kicker">Candidate pipeline</span><h2>${esc(job?.title||'Job applicants')}</h2><p class="form-intro">${apps.length} applicant${apps.length===1?'':'s'}. AI ranking is an optional review aid; final placement decisions remain human-controlled.</p>${apps.length?`<div class="candidate-pipeline-list">${apps.map(a=>`<article class="candidate-pipeline-card"><div class="candidate-identity"><span class="candidate-avatar">${initials(a.student?.full_name||'Student')}</span><div><strong>${esc(a.student?.full_name||'Student')}</strong><small>${esc((a.student?.skills||[]).slice(0,4).join(' · ')||'Skills not listed')}</small></div></div><div class="candidate-facts"><div><span>CGPA</span><strong>${a.student?.cgpa??'—'}</strong></div><div><span>AI match</span><strong>${a.ai_match_score!=null?Math.round(a.ai_match_score):'—'}</strong>${a.ai_match_reasoning?`<button class="reason-link" type="button" data-action="show-ai-reason" data-reason="${esc(a.ai_match_reasoning)}">View reasoning</button>`:''}</div><div><span>Current status</span>${statusBadge(a.status)}</div></div><div class="candidate-stage-action"><label>Move candidate<select class="filter-select application-status-select" data-job="${jobId}" data-id="${a.id}"><option value="">Select next status…</option><option>shortlisted</option><option>interview</option><option>offered</option><option>hired</option><option>rejected</option></select></label></div></article>`).join('')}</div><div class="form-footer candidate-pipeline-footer"><span>Ranking scores should be reviewed together with resume, eligibility and interview evidence.</span><button class="button button-secondary" data-action="rank-candidates" data-id="${jobId}">Run AI-assisted ranking</button></div>`:emptyState('AP','No applicants yet','Applications will appear here when students submit.')}`); }

  async function viewCandidate(id){ const s=await api(`/recruiters/students/${id}`); openModal(`<span class="section-kicker">Candidate profile</span><h2>${esc(s.full_name||'Candidate')}</h2><p class="form-intro">${esc(s.degree||'')} ${s.branch?`· ${esc(s.branch)}`:''} ${s.cgpa!=null?`· CGPA ${s.cgpa}`:''}</p><div class="ai-box"><div class="ai-box-head"><span>SKILLS</span>${s.is_verified?statusBadge('approved'):statusBadge('pending')}</div>${tags(s.skills)}</div>${s.ai_summary?`<div class="ai-box"><div class="ai-box-head"><span>AI-ASSISTED SUMMARY</span></div><p>${esc(s.ai_summary)}</p></div>`:''}<div class="form-footer"><button class="button button-secondary" data-action="download-candidate-resume" data-id="${id}">Open resume</button></div>`); }

  document.addEventListener('click', async e => {
    const authOpen=e.target.closest('[data-open-auth]'); if(authOpen){showAuth(authOpen.dataset.openAuth);return;}
    const view=e.target.closest('[data-view]'); if(view && state.me){
      await navigate(view.dataset.view);
      if (window.matchMedia('(max-width: 760px)').matches) { $('.app-sidebar')?.classList.remove('open'); $('#sidebar-backdrop')?.classList.remove('open'); document.body.classList.remove('sidebar-open'); }
      return;
    }
    const action=e.target.closest('[data-action]');
    if(!action) return;
    const a=action.dataset.action,id=action.dataset.id;
    try{
      if(a==='close-auth')closeAuth();
      else if(a==='show-student-signup')showAuth('signup');
      else if(a==='show-login')showAuth('login');
      else if(a==='forgot-password')showAuth('reset');
      else if(a==='close-generic-modal')closeModal();
      else if(a==='toggle-password'){const input=action.parentElement.querySelector('input');input.type=input.type==='password'?'text':'password';action.textContent=input.type==='password'?'Show':'Hide';}
      else if(a==='toggle-sidebar'){const sidebar=$('.app-sidebar');const open=!sidebar.classList.contains('open');sidebar.classList.toggle('open',open);$('#sidebar-backdrop')?.classList.toggle('open',open);document.body.classList.toggle('sidebar-open',open);}
      else if(a==='logout'){await fetch('/auth/logout',{method:'POST',credentials:'include'});state.token='';location.href='/';}
      else if(a==='reload-view')navigate(state.view);
      else if(a==='open-notifications')navigate('notifications');
      else if(a==='open-job-form')openJobForm();
      else if(a==='open-student-form')openStudentForm();
      else if(a==='open-recruiter-form')openRecruiterForm();
      else if(a==='open-drive-form')openDriveForm(id);
      else if(a==='open-org-form')openOrgForm();
      else if(a==='open-admin-form')openAdminForm(id);
      else if(a==='view-platform-registration'){const d=await api(`/platform/registrations/${encodeURIComponent(id)}`);openModal(platformRegistrationDetailHtml(d));}
      else if(a==='platform-engagement-period'){state.platformEngagementDays=Number(id)||30;await navigate('engagement');}
      else if(a==='platform-provision-recruiter'){
        const email=String(action.dataset.email||'').trim();
        const resend=action.dataset.resend==='true';
        const prompt=resend?`Send a new one-time password setup link to ${email}?`:`Provision this Recruiter account and send a one-time password setup link to ${email}?`;
        if(!window.confirm(prompt))return;
        action.disabled=true;
        const original=action.textContent;
        action.textContent=resend?'Sending setup link…':'Provisioning recruiter…';
        try{
          const result=await api(`/platform/access-requests/${encodeURIComponent(id)}/provision-recruiter`,{method:'POST'});
          toast(result.setup_email_sent?'Recruiter account ready':'Setup email not delivered',result.message||'Recruiter provisioning completed.',result.setup_email_sent?'success':'error');
          await navigate('leads');
        }catch(error){
          action.disabled=false;
          action.textContent=original;
          throw error;
        }
      }
      else if(a==='view-applicants')await viewApplicants(id);
      else if(a==='view-candidate')await viewCandidate(id);
      else if(a==='apply-job'){openModal(`<span class="section-kicker">Application</span><h2>Submit application</h2><p class="form-intro">Add a concise cover note or submit without one.</p><form id="apply-form" class="form-stack"><input type="hidden" name="job_id" value="${id}"><label>Cover note <span class="optional">optional</span><textarea name="cover_note" rows="5" placeholder="Why are you interested in this role?"></textarea></label><button class="button button-primary button-full">Submit application</button></form>`);}
      else if(a==='check-eligibility'){const r=await api(`/students/drives/${id}/eligibility`);openModal(`<span class="section-kicker">Eligibility check</span><h2>${r.eligible?'You are eligible':'Not currently eligible'}</h2><p class="form-intro">${r.eligible?'Your current academic profile satisfies this drive’s configured criteria.':'Your profile does not satisfy every configured criterion.'}</p>${r.reasons?.length?`<div class="ai-box"><div class="ai-box-head"><span>REASONS</span></div><p>${r.reasons.map(esc).join('<br>')}</p></div>`:''}<button class="button button-primary button-full" data-action="close-generic-modal">Done</button>`);}
      else if(a==='parse-resume'){await api('/ai/parse-resume',{method:'POST'});toast('Resume parsed','Review the extracted data before relying on it.');navigate('resume');}
      else if(a==='generate-summary'){await api('/ai/generate-summary',{method:'POST'});toast('Summary generated','AI output should be reviewed for accuracy.');navigate('resume');}
      else if(a==='delete-job'){if(confirm('Delete this job permanently?')){await api(`/jobs/${id}`,{method:'DELETE'});toast('Job deleted');navigate('jobs');}}
      else if(a==='approve-job'||a==='reject-job'){const val=a==='approve-job'?'approved':'rejected';await api(`/institutions/jobs/${id}/approval`,{method:'PATCH',body:JSON.stringify({approval_status:val})});toast(`Job ${val}`);navigate('jobs');}
      else if(a==='toggle-student-verify'){await api(`/institutions/students/${id}/verification`,{method:'PATCH',body:JSON.stringify({is_verified:action.dataset.value==='true'})});toast('Verification updated');navigate('students');}
      else if(a==='rank-candidates'){const result=await api(`/ai/rank-candidates/${id}`,{method:'POST'});toast('AI ranking complete',`${result.ranked_candidates?.length||0} applicants scored. Review AI reasoning before making any hiring decision.`);await viewApplicants(id);}
      else if(a==='company-trust-review'){await openCompanyTrustReview(id);}
      else if(a==='show-ai-reason'){openModal(`<span class="section-kicker">AI match explanation</span><h2>Why this score?</h2><p class="form-intro">${esc(action.dataset.reason||'No reasoning is available yet.')}</p><div class="ai-box"><div class="ai-box-head"><span>HUMAN REVIEW REQUIRED</span></div><p>AI ranking is decision support only. Recruiters should review the candidate's actual resume, interview evidence and role requirements before making a hiring decision.</p></div><button class="button button-primary button-full" data-action="close-generic-modal">Done</button>`);}
      else if(a==='export-students'){const r=await fetch('/institutions/export/students.csv',{headers:{Authorization:`Bearer ${state.token}`}});if(!r.ok)throw new Error('Could not export student records');const blob=await r.blob();const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download='placeai-students.csv';document.body.appendChild(link);link.click();link.remove();URL.revokeObjectURL(url);}
      else if(a==='download-candidate-resume'){const r=await fetch(`/recruiters/students/${id}/resume`,{headers:{Authorization:`Bearer ${state.token}`}});if(!r.ok)throw new Error('Candidate resume is not available');const blob=await r.blob();const url=URL.createObjectURL(blob);window.open(url,'_blank','noopener');setTimeout(()=>URL.revokeObjectURL(url),60000);}
    }catch(err){toast('Action failed',err.message,'error');}
  });

  $('#context-action').addEventListener('click',()=>{if(!state.contextAction)return;document.querySelector(`[data-action="${state.contextAction}"]`)?.click() || ({'open-job-form':openJobForm,'open-student-form':openStudentForm,'open-recruiter-form':openRecruiterForm,'open-org-form':openOrgForm}[state.contextAction]?.());});

  document.addEventListener('change',async e=>{
    try{
      if(e.target.id==='job-type-filter'){filterStudentJobs();return;}
      if(e.target.matches?.('[data-platform-access-status]')){
        const select=e.target,previous=select.dataset.currentStatus||select.value,next=select.value,id=select.dataset.id;
        if(!id||next===previous)return;
        select.disabled=true;
        try{
          const result=await api(`/platform/access-requests/${encodeURIComponent(id)}`,{method:'PATCH',body:JSON.stringify({status:next,review_note:null})});
          select.dataset.currentStatus=result.status;
          select.value=result.status;
          toast('Access request updated',`Status changed to ${String(result.status).replaceAll('_',' ')}.`);
          await navigate('leads');
        }catch(error){
          select.value=previous;
          select.disabled=false;
          throw error;
        }
        return;
      }
      if(e.target.matches?.('[data-institution-access-status]')){
        const select=e.target,previous=select.dataset.currentStatus||select.value,next=select.value,id=select.dataset.id;
        if(!id||next===previous)return;
        select.disabled=true;
        try{
          const result=await api(`/institutions/access-requests/${encodeURIComponent(id)}`,{method:'PATCH',body:JSON.stringify({status:next,review_note:null})});
          select.dataset.currentStatus=result.status;
          select.value=result.status;
          toast('Access request updated',`Status changed to ${String(result.status).replaceAll('_',' ')}.`);
          await navigate('institution-access-requests');
        }catch(error){
          select.value=previous;
          select.disabled=false;
          throw error;
        }
        return;
      }
      if(e.target.id==='platform-registration-role'){state.platformRegistrationRole=e.target.value||'';await navigate('registrations');return;}
      if(e.target.id==='resume-file'&&e.target.files[0]){const form=new FormData();form.append('file',e.target.files[0]);await api('/students/resume',{method:'POST',body:form});toast('Resume uploaded');navigate('resume');}
      if(e.target.id==='student-csv-file'&&e.target.files[0]){const form=new FormData();form.append('file',e.target.files[0]);const result=await api('/institutions/import/students.csv',{method:'POST',body:form});toast('CSV import complete',`${result.created} created · ${result.failed} failed`);if(result.errors?.length){openModal(`<span class="section-kicker">CSV import report</span><h2>${result.created} students created</h2><p class="form-intro">${result.failed} rows could not be imported.</p><div class="ai-box"><div class="ai-box-head"><span>ROW ERRORS</span></div><p>${result.errors.map(x=>`Row ${x.row}: ${esc(x.error)}`).join('<br>')}</p></div><button class="button button-primary button-full" data-action="close-generic-modal">Done</button>`);}await navigate('students');}
      if(e.target.classList.contains('application-status-select')&&e.target.value){await api(`/jobs/${e.target.dataset.job}/applicants/${e.target.dataset.id}/status`,{method:'PATCH',body:JSON.stringify({status:e.target.value})});toast('Application stage updated');await viewApplicants(e.target.dataset.job);}
    }catch(err){toast('Update failed',err.message,'error');}
  });

  document.addEventListener('input',e=>{
    if(e.target.id==='job-search') filterStudentJobs();
    if(e.target.id==='candidate-search'&&state.lastCandidates){const term=e.target.value.toLowerCase();$('#candidate-body').innerHTML=state.lastCandidates.filter(s=>`${s.full_name||''} ${s.college||''} ${(s.skills||[]).join(' ')}`.toLowerCase().includes(term)).map(candidateRow).join('');}
    if(e.target.id==='institution-student-search'&&state.lastStudents){const term=e.target.value.toLowerCase();$('#institution-student-body').innerHTML=state.lastStudents.filter(s=>`${s.full_name||''} ${s.branch||''} ${(s.skills||[]).join(' ')}`.toLowerCase().includes(term)).map(institutionStudentRow).join('');}
  });

  document.addEventListener('submit',async e=>{
    const f=e.target; e.preventDefault(); const fd=new FormData(f); const obj=Object.fromEntries(fd.entries());
    try{
      if(f.id==='login-form'){const data=await api('/auth/login-json',{method:'POST',body:JSON.stringify({email:obj.email,password:obj.password})},false);state.token=data.access_token;closeAuth();await bootWorkspace();toast('Signed in');}
      else if(f.id==='signup-form'){const data={username:obj.username,email:obj.email,password:obj.password,role:'student',organization_slug:obj.organization_slug||null};await api('/auth/signup',{method:'POST',body:JSON.stringify(data)},false);const login=await api('/auth/login-json',{method:'POST',body:JSON.stringify({email:obj.email,password:obj.password})},false);state.token=login.access_token;closeAuth();await bootWorkspace();if(obj.full_name)await api('/students/profile',{method:'PUT',body:JSON.stringify({full_name:obj.full_name})});toast('Student account created');}
      else if(f.id==='forgot-form'){await api('/auth/forgot-password',{method:'POST',body:JSON.stringify({email:obj.email})},false);toast('Request accepted','If the account exists, reset instructions will be sent.');showAuth('login');}
      else if(f.id==='student-profile-form'){const num=(v)=>v!==''&&v!=null?Number(v):null;const customValues={};for(const [k,v] of Object.entries(obj)){if(k.startsWith('custom__')){customValues[k.slice(8)]=String(v??'');delete obj[k];}}const data={...obj,skills:String(obj.skills||'').split(',').map(x=>x.trim()).filter(Boolean),certifications:String(obj.certifications||'').split(',').map(x=>x.trim()).filter(Boolean),desired_roles:String(obj.desired_roles||'').split(',').map(x=>x.trim()).filter(Boolean),graduation_year:num(obj.graduation_year),cgpa:num(obj.cgpa),tenth_percentage:num(obj.tenth_percentage),twelfth_percentage:num(obj.twelfth_percentage),diploma_percentage:num(obj.diploma_percentage),active_backlogs:num(obj.active_backlogs),historical_backlogs:num(obj.historical_backlogs),academic_gap_months:num(obj.academic_gap_months)};await api('/students/profile',{method:'PUT',body:JSON.stringify(data)});if(state.profile?.id&&Object.keys(customValues).length)await api(`/enterprise/custom-fields/values/${state.profile.id}`,{method:'PUT',body:JSON.stringify({values:customValues})});toast('Profile saved','Verified academic changes may appear under Profile approvals until your placement office reviews them.');navigate('profile');}
      else if(f.id==='recruiter-profile-form'){await api('/recruiters/profile',{method:'PUT',body:JSON.stringify(obj)});toast('Company profile saved');navigate('profile');}
      else if(f.id==='job-form'){const data={...obj,required_skills:obj.required_skills.split(',').map(x=>x.trim()).filter(Boolean),preferred_roles:obj.preferred_roles.split(',').map(x=>x.trim()).filter(Boolean),deadline:obj.deadline?new Date(obj.deadline).toISOString():null,target_organization_slug:obj.visibility==='campus'?(obj.target_organization_slug||null):null};await api('/jobs',{method:'POST',body:JSON.stringify(data)});closeModal();toast(data.visibility==='campus'?'Campus job submitted':'Job published',data.visibility==='campus'?'The institution must approve it before students can access it.':'The job is live.');navigate('jobs');}
      else if(f.id==='institution-student-form'){const data={...obj,graduation_year:obj.graduation_year?Number(obj.graduation_year):null,cgpa:obj.cgpa?Number(obj.cgpa):null};await api('/institutions/students',{method:'POST',body:JSON.stringify(data)});closeModal();toast('Student account created');navigate('students');}
      else if(f.id==='institution-recruiter-form'){await api('/institutions/recruiters',{method:'POST',body:JSON.stringify(obj)});closeModal();toast('Verified recruiter provisioned');navigate('recruiters');}
      else if(f.id==='drive-form'){const n=v=>v!==''&&v!=null?Number(v):null;let custom={};if(String(obj.custom_eligibility_rules||'').trim()){try{custom=JSON.parse(obj.custom_eligibility_rules)}catch(_){throw new Error('Custom eligibility rules must be valid JSON.')}}const data={...obj,min_cgpa:n(obj.min_cgpa),min_tenth_percentage:n(obj.min_tenth_percentage),min_twelfth_percentage:n(obj.min_twelfth_percentage),min_diploma_percentage:n(obj.min_diploma_percentage),max_active_backlogs:n(obj.max_active_backlogs),max_historical_backlogs:n(obj.max_historical_backlogs),max_academic_gap_months:n(obj.max_academic_gap_months),allow_placed_students:fd.has('allow_placed_students'),allowed_graduation_years:String(obj.allowed_graduation_years||'').split(',').map(x=>Number(x.trim())).filter(Boolean),allowed_branches:String(obj.allowed_branches||'').split(',').map(x=>x.trim()).filter(Boolean),required_skills:String(obj.required_skills||'').split(',').map(x=>x.trim()).filter(Boolean),required_certifications:String(obj.required_certifications||'').split(',').map(x=>x.trim()).filter(Boolean),required_documents:String(obj.required_documents||'').split(',').map(x=>x.trim()).filter(Boolean),custom_eligibility_rules:custom,registration_deadline:obj.registration_deadline?new Date(obj.registration_deadline).toISOString():null,event_date:obj.event_date?new Date(obj.event_date).toISOString():null};await api('/institutions/drives',{method:'POST',body:JSON.stringify(data)});closeModal();toast('Placement drive created','Advanced eligibility and the default multi-round pipeline are ready.');navigate('drives');}
      else if(f.id==='org-form'){await api('/platform/organizations',{method:'POST',body:JSON.stringify({...obj,country:'India',primary_color:'#5B5BD6'})});closeModal();toast('Institution created');navigate('organizations');}
      else if(f.id==='admin-form'){await api('/platform/institution-admins',{method:'POST',body:JSON.stringify(obj)});closeModal();toast('TPO administrator created');navigate('organizations');}
      else if(f.id==='apply-form'){await api(`/students/jobs/${obj.job_id}/apply`,{method:'POST',body:JSON.stringify({cover_note:obj.cover_note||null})});closeModal();toast('Application submitted');navigate('applications');}
    }catch(err){apiErrors.applyToForm(f,err);toast('Could not complete request',err.message,'error');}
  });


  // ─────────────────────────────────────────────────────────────
  // PlaceAI Enterprise Feature Suite v3.0
  // ─────────────────────────────────────────────────────────────
  const fmtDateTime = v => v ? new Intl.DateTimeFormat('en-IN',{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}).format(new Date(v)) : '—';
  const toDateTimeLocal = v => { if(!v) return ''; const d=new Date(v); const z=n=>String(n).padStart(2,'0'); return `${d.getFullYear()}-${z(d.getMonth()+1)}-${z(d.getDate())}T${z(d.getHours())}:${z(d.getMinutes())}`; };
  const scoreTone = n => n >= 80 ? 'good' : n >= 60 ? 'warn' : 'risk';
  const enterpriseNavAliases = {readiness:'analytics',interviews:'drives',offers:'applications',documents:'resume',assistant:'resume',calendar:'drives',announcements:'notifications',incidents:'audit',approvals:'students',pipeline:'applications',verification:'audit',communications:'recruiters',attention:'analytics',analytics2:'analytics',attendance:'drives',policies:'audit','custom-fields':'students',reports:'analytics'};
  Object.entries(enterpriseNavAliases).forEach(([k,v])=>{ if(!navIcons[k]) navIcons[k]=navIcons[v] || navIcons.dashboard; });

  function enterpriseMetric(label,value,detail='',tone='') { return `<article class="metric-card enterprise-metric ${tone}"><small>${esc(label)}</small><strong>${esc(value)}</strong><span>${esc(detail)}</span></article>`; }
  function featurePanel(title,subtitle,body,extra='') { return `<section class="panel enterprise-panel"><div class="panel-head"><div><h2>${esc(title)}</h2><p>${esc(subtitle)}</p></div>${extra}</div>${body}</section>`; }
  function enterpriseTable(headers,rows){return `<div class="data-panel"><div class="table-wrap enterprise-table-wrap"><table class="data-table enterprise-table"><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div></div>`;}
  function timeline(events){return events.length?`<div class="timeline-list">${events.map(e=>`<article class="timeline-item"><span class="timeline-dot"></span><div><small>${esc((e.type||'event').replaceAll('_',' '))}</small><strong>${esc(e.title)}</strong><p>${fmtDateTime(e.at)}</p></div></article>`).join('')}</div>`:emptyState('CL','No calendar events','Upcoming drives, interviews, deadlines and joining dates will appear here.');}

  async function renderStudentEnterprise(view){
    setContextAction();
    if(view==='readiness'){
      setPage('Readiness score','Career intelligence'); const r=await api('/enterprise/readiness');
      $('#app-content').innerHTML=`${pageHead('Placement Readiness','Evidence-backed preparation score. This is not an employment prediction.')}<div class="readiness-hero"><div class="readiness-score ${scoreTone(r.score)}"><strong>${r.score}</strong><span>/100</span><small>READINESS</small></div><div><h2>${r.score>=80?'Strong evidence base':r.score>=60?'Good foundation with gaps':'Preparation gaps need attention'}</h2><p>${esc(r.disclaimer)}</p></div></div><div class="readiness-components">${r.components.map(c=>`<article><div><strong>${esc(c.name)}</strong><span>${c.score}/100</span></div><div class="professional-meter"><i style="width:${c.score}%"></i></div></article>`).join('')}</div>${featurePanel('Recommended next actions','Highest-value improvements based on your current evidence.',`<ol class="action-list">${r.recommended_actions.map(x=>`<li>${esc(x)}</li>`).join('')}</ol>`)}`;
    } else if(view==='interviews'){
      setPage('Interviews','Placement schedule'); const items=await api('/enterprise/interviews');
      $('#app-content').innerHTML=`${pageHead('Interview & assessment schedule','Your confirmed interview rounds, slots and instructions.')}${items.length?`<div class="card-grid">${items.map(i=>`<article class="operation-card"><div class="operation-card-top"><span class="status-pill">${esc(i.status)}</span><small>${fmtDateTime(i.scheduled_at)}</small></div><h3>${esc(i.round_name)}</h3><p>${esc(i.company_name||'Company')} · ${esc(i.job_title||'Role')}</p><dl><div><dt>Mode</dt><dd>${esc(i.mode)}</dd></div><div><dt>Venue / link</dt><dd>${i.meeting_url?`<a href="${esc(i.meeting_url)}" target="_blank" rel="noopener">Join meeting</a>`:esc(i.venue||'To be confirmed')}</dd></div><div><dt>Interviewer</dt><dd>${esc(i.interviewer||'To be assigned')}</dd></div><div><dt>Attendance</dt><dd>${esc(i.attendance_status)}</dd></div></dl>${i.instructions?`<div class="note-box">${esc(i.instructions)}</div>`:''}</article>`).join('')}</div>`:emptyState('IV','No interviews scheduled','When a recruiter or placement team schedules a round, it will appear here.')}`;
    } else if(view==='offers'){
      setPage('Offers','Placement outcomes'); const offers=await api('/enterprise/offers');
      $('#app-content').innerHTML=`${pageHead('Offer centre','Review offer terms and record your acceptance or decline decision.')}${offers.length?`<div class="card-grid">${offers.map(o=>`<article class="operation-card"><div class="operation-card-top">${statusBadge(o.status)}<small>${fmtDate(o.created_at)}</small></div><h3>${esc(o.role)}</h3><p>${esc(o.company_name)} · ${esc(o.location||'Location pending')}</p><div class="offer-number">${o.ctc_lpa!=null?`${o.ctc_lpa} LPA`:'CTC not recorded'}</div><dl><div><dt>Joining</dt><dd>${fmtDate(o.joining_date)}</dd></div><div><dt>PPO</dt><dd>${esc(o.ppo_status||'—')}</dd></div></dl>${o.has_offer_letter?`<div class="row-actions"><button class="row-button" data-action="download-offer-letter" data-id="${o.id}">Download offer letter</button></div>`:''}${o.status==='issued'?`<div class="row-actions"><button class="row-button primary" data-action="student-offer-decision" data-id="${o.id}" data-value="accepted">Accept</button><button class="row-button" data-action="student-offer-decision" data-id="${o.id}" data-value="declined">Decline</button></div>`:''}</article>`).join('')}</div>`:emptyState('OF','No offers yet','Formal offers created through your application pipeline will appear here.')}`;
    } else if(view==='documents'){
      setPage('Document vault','Student records'); const docs=await api('/enterprise/documents');
      $('#app-content').innerHTML=`${pageHead('Student document vault','Maintain placement documents with controlled visibility.')}<section class="form-panel compact-form"><form id="document-upload-form" class="inline-form"><label>Document type<select name="document_type"><option value="marksheet">Marksheet</option><option value="certification">Certification</option><option value="transcript">Transcript</option><option value="photo">Photograph</option><option value="identity">Optional identity document</option><option value="internship_letter">Internship letter</option><option value="offer_letter">Offer letter</option></select></label><label>Visibility<select name="visibility"><option value="institution_only">Institution only</option><option value="recruiter_with_permission">Recruiter with permission</option></select></label><label class="file-picker">Choose file<input id="student-document-file" type="file" accept=".pdf,.png,.jpg,.jpeg"></label><button class="button button-primary" type="submit">Upload document</button></form></section>${docs.length?enterpriseTable(['Document','Type','Visibility','Verified','Uploaded',''],docs.map(d=>`<tr><td><span class="table-primary">${esc(d.filename)}</span></td><td>${esc(d.document_type)}</td><td>${esc(d.visibility.replaceAll('_',' '))}</td><td>${d.is_verified?statusBadge('approved'):statusBadge('pending')}</td><td>${fmtDate(d.uploaded_at)}</td><td><button class="row-button" data-action="download-vault-document" data-id="${d.id}">Open</button></td></tr>`).join('')):emptyState('DV','Vault is empty','Upload marksheets, certificates, transcripts or other placement documents.')}`;
    } else if(view==='assistant'){
      setPage('AI placement assistant','Role-aware intelligence');
      $('#app-content').innerHTML=`${pageHead('AI Placement Assistant','Ask questions using only your authorized PlaceAI context.')}<div class="assistant-layout"><section class="assistant-card"><div id="assistant-transcript" class="assistant-transcript"><div class="assistant-message system"><strong>PlaceAI Assistant</strong><p>Ask about eligible drives, application status, upcoming interviews, resume preparation or your next actions.</p></div></div><form id="assistant-form" class="assistant-input"><textarea name="message" rows="3" placeholder="Which drives am I eligible for, and what should I prepare next?" required></textarea><button class="button button-primary">Ask PlaceAI</button></form></section><aside class="panel prompt-library"><h2>Useful questions</h2>${['Which drives am I eligible for?','Why am I not eligible for a drive?','Which roles match my skills?','When is my next interview?','What should I improve before my next application?'].map(q=>`<button data-action="assistant-suggestion" data-value="${esc(q)}">${esc(q)}</button>`).join('')}</aside></div>`;
    } else if(view==='calendar'){
      setPage('Placement calendar','Planning'); const events=await api('/enterprise/calendar'); $('#app-content').innerHTML=`${pageHead('Placement calendar','Registration deadlines, drives, interviews, announcements and joining dates in one timeline.')}${featurePanel('Upcoming placement events',`${events.length} scheduled item${events.length===1?'':'s'}.`,timeline(events))}`;
    } else if(view==='announcements'){
      setPage('Announcements','Updates'); const rows=await api('/enterprise/announcements'); $('#app-content').innerHTML=`${pageHead('Placement announcements','Official communication from your placement office.')}${rows.length?`<div class="announcement-list">${rows.map(a=>`<article class="announcement-card"><div><span class="priority-label priority-${esc(a.priority)}">${esc(a.priority)}</span><small>${fmtDate(a.created_at)}</small></div><h3>${esc(a.title)}</h3><p>${esc(a.body)}</p></article>`).join('')}</div>`:emptyState('AN','No announcements','Institution announcements targeted to your batch will appear here.')}`;
    } else if(view==='incidents'){
      setPage('Report an issue','Placement safety'); const rows=await api('/enterprise/incidents'); $('#app-content').innerHTML=`${pageHead('Confidential incident reporting','Report suspicious recruiters, payment demands, misleading job information or offer discrepancies.')}<div class="two-panel"><form id="incident-form" class="form-panel"><h2>New confidential report</h2><label class="field-label">Category<select class="field-input" name="category"><option>suspicious recruiter</option><option>misleading CTC</option><option>payment demand</option><option>inappropriate interview behaviour</option><option>fake job</option><option>offer discrepancy</option></select></label><label class="field-label">Describe what happened<textarea class="field-input" name="description" rows="6" required></textarea></label><label class="check-label"><input type="checkbox" name="confidential" checked> Keep this confidential to authorized placement administrators</label><button class="button button-primary">Submit report</button></form>${featurePanel('Your reports','Status is visible only to you and authorized institution staff.',rows.length?`<div class="activity-list">${rows.map(x=>`<div class="activity-item"><span class="activity-icon">!</span><div><strong>${esc(x.category)}</strong><small>${esc(x.description.slice(0,100))}</small></div>${statusBadge(x.status)}</div>`).join('')}</div>`:emptyState('IR','No reports submitted','Your submitted incident reports will appear here.'))}</div>`;
    } else if(view==='approvals'){
      setPage('Profile approvals','Account'); const rows=await api('/enterprise/profile-change-requests'); $('#app-content').innerHTML=`${pageHead('Profile approval requests','Academic changes that require institution verification are tracked here.')}${rows.length?enterpriseTable(['Field','Current','Requested','Status','Requested'],rows.map(r=>`<tr><td>${esc(r.field_name.replaceAll('_',' '))}</td><td>${esc(r.old_value||'—')}</td><td>${esc(r.new_value||'—')}</td><td>${statusBadge(r.status)}</td><td>${fmtDate(r.created_at)}</td></tr>`).join('')):emptyState('PA','No profile changes pending','Changes to verified academic fields will appear here for review.')}`;
    }
  }

  async function collectRecruiterApplications(){ const jobs=await api('/jobs/my/listings'); const groups=await Promise.all(jobs.map(j=>api(`/jobs/${j.id}/applicants`).catch(()=>[]))); return {jobs,apps:groups.flat()}; }

  async function renderRecruiterEnterprise(view){
    setContextAction();
    if(view==='verification'){
      setPage('Company verification','Trust & compliance'); const [v,p]=await Promise.all([api('/enterprise/company-verification'),api('/recruiters/profile')]); const a=v.assessment;
      $('#app-content').innerHTML=`${pageHead('Company Verification Centre','Build a transparent evidence file for placement-office review.')}<div class="verification-hero"><div class="verification-status verification-${esc(a.level)}"><small>VERIFICATION STATUS</small><strong>${esc(a.verification_status)}</strong><span>Confidence ${a.confidence}%</span></div><div><h2>${esc(v.company.company_name||'Company profile')}</h2><p>${esc(a.disclaimer)}</p>${a.risk_flags?.length?`<div class="risk-flags">${a.risk_flags.map(x=>`<span>${esc(x)}</span>`).join('')}</div>`:''}</div></div><div class="profile-trust-layout"><form id="verification-profile-form" class="form-panel"><h2>Company evidence</h2><div class="profile-grid">${inputField('Company name','company_name',p.company_name)}${inputField('Recruiter name','full_name',p.full_name)}${inputField('Designation','designation',p.designation)}${inputField('CIN','cin',p.cin)}${inputField('GSTIN','gstin',p.gstin)}${inputField('Official website','company_website',p.company_website,'url')}${inputField('Official email domain','official_email_domain',p.official_email_domain)}${inputField('LinkedIn / company presence','linkedin_url',p.linkedin_url,'url')}<label class="field-label full">Company address<textarea class="field-input" name="company_address" rows="3">${esc(p.company_address||'')}</textarea></label><label class="field-label full">Past college relationships <span class="field-help">Comma separated</span><input class="field-input" name="past_college_relationships" value="${esc((p.past_college_relationships||[]).join(', '))}"></label>${inputField('Previous successful placements','previous_successful_placements',p.previous_successful_placements,'number','0')}</div><div class="form-footer"><button class="button button-primary">Save evidence</button></div></form><section class="trust-card"><div class="panel-head"><div><h2>Verification checks</h2><p>Independent evidence signals—not a legal certification.</p></div></div><div class="trust-check-list">${a.checks.map(c=>`<div class="trust-check"><span class="trust-state trust-state-${esc(c.status)}">${c.status==='verified'?'✓':c.status==='partial'?'~':'!'}</span><div><strong>${esc(c.label)}</strong><small>${esc(c.detail)}</small></div><b>${c.earned}/${c.weight}</b></div>`).join('')}</div><form id="authorization-letter-form" class="upload-strip"><label>Recruitment authorization letter (PDF)<input id="authorization-letter-file" type="file" accept="application/pdf"></label><button class="row-button primary">Upload evidence</button></form></section></div>`;
    } else if(view==='pipeline'){
      setPage('Drive pipeline','Hiring operations'); const drives=await api('/enterprise/drives'); $('#app-content').innerHTML=`${pageHead('Advanced placement pipelines','Review institution-defined screening and interview stages. Structural changes are placement-office controlled.')}${drives.length?`<div class="card-grid">${drives.map(d=>`<article class="operation-card"><div class="operation-card-top">${statusBadge(d.status)}<small>${fmtDate(d.event_date)}</small></div><h3>${esc(d.title)}</h3><p>${esc(d.company_name||'')} · ${esc(d.job_title||'')}</p><button class="button button-secondary button-full" data-action="view-pipeline" data-id="${d.id}">Open pipeline</button></article>`).join('')}</div>`:emptyState('PL','No campus pipelines','Pipelines are created with institution placement drives.')}`;
    } else if(view==='interviews'){
      setPage('Interviews','Hiring operations'); const [items,data]=await Promise.all([api('/enterprise/interviews'),collectRecruiterApplications()]); state.recruiterInterviews=items; $('#app-content').innerHTML=`${pageHead('Interview & assessment scheduler','Schedule rounds, slots, meeting links, attendance and results.','Schedule interview','open-interview-form')}<button class="hidden" data-action="open-interview-form"></button>${items.length?enterpriseTable(['Candidate','Role / round','Schedule','Mode','Attendance','Result','Actions'],items.map(i=>`<tr><td>${esc(i.student_name||'Candidate')}</td><td><span class="table-primary">${esc(i.round_name)}</span><span class="table-secondary">${esc(i.job_title||'')}</span></td><td>${fmtDateTime(i.scheduled_at)}</td><td>${esc(i.mode)}</td><td>${esc(i.attendance_status)}</td><td>${esc(i.result||'—')}</td><td><div class="row-actions compact"><button class="row-button" data-action="manage-interview" data-id="${i.id}">Manage</button><button class="row-button" data-action="evaluate-interview" data-id="${i.id}">Evaluation</button></div></td></tr>`).join('')):emptyState('IV','No interviews scheduled','Schedule a round for an applicant from your pipeline.')}<div id="recruiter-app-cache" data-apps="${esc(JSON.stringify(data.apps.map(a=>({id:a.id,name:a.student?.full_name,role:a.job_title}))))}"></div>`;
    } else if(view==='offers'){
      setPage('Offers','Hiring outcomes'); const [offers,data]=await Promise.all([api('/enterprise/offers'),collectRecruiterApplications()]); state.recruiterOffers=offers; $('#app-content').innerHTML=`${pageHead('Offer management','Issue offers, record compensation structure and track joining outcomes.','Create offer','open-offer-form')}<button class="hidden" data-action="open-offer-form"></button>${offers.length?enterpriseTable(['Candidate','Role','CTC','Status','Joining','Offer letter','Actions'],offers.map(o=>`<tr><td>${esc(o.student_name||'Candidate')}</td><td><span class="table-primary">${esc(o.role)}</span><span class="table-secondary">${esc(o.company_name)}</span></td><td>${o.ctc_lpa!=null?`${o.ctc_lpa} LPA`:'—'}</td><td>${statusBadge(o.status)}</td><td>${fmtDate(o.joining_date)}</td><td>${o.has_offer_letter?`<button class="row-button" data-action="download-offer-letter" data-id="${o.id}">Download</button>`:'Not uploaded'}</td><td><div class="row-actions compact"><select class="filter-select offer-status-select" data-id="${o.id}"><option value="">Update…</option><option value="issued">Issued</option><option value="withdrawn">Withdrawn</option><option value="joining_confirmed">Joining confirmed</option><option value="joined">Joined</option></select><button class="row-button" data-action="upload-offer-letter" data-id="${o.id}">${o.has_offer_letter?'Replace':'Upload'} letter</button></div></td></tr>`).join('')):emptyState('OF','No offers created','Create an offer from an applicant record.')}<div id="recruiter-offer-app-cache" data-apps="${esc(JSON.stringify(data.apps.map(a=>({id:a.id,name:a.student?.full_name,role:a.job_title}))))}"></div>`;
    } else if(view==='communications'){
      setPage('Placement office messages','Collaboration'); const threads=await api('/enterprise/communications'); $('#app-content').innerHTML=`${pageHead('Recruiter communication hub','Keep campus hiring discussions and context inside the institutional workflow.','New thread','open-thread-form')}<button class="hidden" data-action="open-thread-form"></button>${threads.length?`<div class="thread-list">${threads.map(t=>`<button class="thread-card" data-action="open-thread" data-id="${t.id}"><strong>${esc(t.subject)}</strong><span>${t.message_count} messages · ${esc(t.status)}</span></button>`).join('')}</div>`:emptyState('CM','No conversation threads','Start a placement-office thread for a drive or hiring discussion.')}`;
    } else if(view==='assistant'){
      setPage('AI placement assistant','Hiring intelligence'); $('#app-content').innerHTML=`${pageHead('AI Placement Assistant','Ask pipeline questions using only candidates and jobs you are authorized to access.')}<div class="assistant-layout"><section class="assistant-card"><div id="assistant-transcript" class="assistant-transcript"><div class="assistant-message system"><strong>PlaceAI Assistant</strong><p>Try: Show candidates with Python + FastAPI and CGPA above 8.</p></div></div><form id="assistant-form" class="assistant-input"><textarea name="message" rows="3" placeholder="Show candidates with Python + FastAPI and CGPA above 8" required></textarea><button class="button button-primary">Ask PlaceAI</button></form></section></div>`;
    }
  }

  async function renderInstitutionEnterprise(view){
    setContextAction();
    if(view==='attention'){
      setPage('Attention centre','Command centre'); const a=await api('/enterprise/attention-centre'); $('#app-content').innerHTML=`${pageHead('Students needing attention','Operational signals for placement-team follow-up—not predictions of failure.')}<div class="metric-grid">${a.signals.map(s=>enterpriseMetric(s.label,s.count,`${s.count===0?'No action required':'Students require follow-up'}`,s.severity)).join('')}</div>${featurePanel('Follow-up queues','Prioritized records that need human action.',`<div class="attention-columns">${Object.entries(a.students).map(([k,rows])=>`<section><h3>${esc(k.replaceAll('_',' '))}</h3>${rows.length?rows.slice(0,8).map(x=>`<div class="mini-person"><strong>${esc(x.name||'Student')}</strong><span>${esc(x.branch||'')}</span></div>`).join(''):'<p class="muted-copy">No students in this queue.</p>'}</section>`).join('')}</div>`)}`;
    } else if(view==='analytics2'){
      setPage('Placement analytics','Executive intelligence'); const a=await api('/enterprise/analytics/institution');
      $('#app-content').innerHTML=`${pageHead('Placement Analytics 2.0','Executive outcomes, conversion, placement velocity and unplaced-student segmentation.')}
      <div class="metric-grid">${enterpriseMetric('Placement rate',`${a.placement_rate}%`,`${a.unique_students_placed} unique students placed`,'good')}${enterpriseMetric('Median CTC',a.median_ctc!=null?`${a.median_ctc} LPA`:'—','Accepted offers')}${enterpriseMetric('Average CTC',a.average_ctc!=null?`${a.average_ctc} LPA`:'—','Accepted offers')}${enterpriseMetric('Highest CTC',a.highest_ctc!=null?`${a.highest_ctc} LPA`:'—','Recorded accepted offers')}${enterpriseMetric('Offers generated',a.offers_generated,`${a.offer_acceptance_rate}% acceptance`)}${enterpriseMetric('Application → offer',`${a.application_to_offer_conversion}%`,`${a.company_participation} participating companies`)}${enterpriseMetric('Internship → PPO',`${a.internship_ppo_conversion}%`,`${a.ppo_confirmed} confirmed PPO outcome${a.ppo_confirmed===1?'':'s'}`)}${enterpriseMetric('Unplaced students',a.unplaced_students,'Actionable segments below')}</div>
      <div class="analytics-split">
        ${featurePanel('Department outcomes','Placement rate by department.',a.department_breakdown.length?`<div class="department-grid">${a.department_breakdown.map(x=>`<article class="department-card"><header><strong>${esc(x.department)}</strong><b>${x.placement_rate}%</b></header><span>${x.placed}/${x.students} placed</span><div class="professional-meter"><i style="width:${x.placement_rate}%"></i></div></article>`).join('')}</div>`:emptyState('AN','No outcome data','Department analytics will populate as offers and joining outcomes are recorded.'))}
        ${featurePanel('Unplaced student segmentation','Operational segments for placement-office follow-up.',a.unplaced_segmentation?.length?`<div class="segmentation-list">${a.unplaced_segmentation.map(x=>`<article><span>${esc(x.segment)}</span><strong>${x.count}</strong></article>`).join('')}</div>`:emptyState('US','No segmentation yet','Student placement activity will populate this view.'))}
      </div>
      ${featurePanel('Monthly placement trend','Accepted and joining-confirmed offers recorded over time.',a.monthly_placement_trend?.length?`<div class="trend-strip">${a.monthly_placement_trend.map(x=>`<article><small>${esc(x.month)}</small><strong>${x.placements}</strong><span>placements</span></article>`).join('')}</div>`:emptyState('TR','No monthly trend yet','Accepted offer outcomes will create a placement trend.'))}
      ${featurePanel('Drive conversion','Application-to-offer and offer-acceptance performance for each campus drive.',a.drive_conversion?.length?enterpriseTable(['Drive','Applications','Offers','Accepted','Application → offer','Offer acceptance'],a.drive_conversion.map(x=>`<tr><td><span class="table-primary">${esc(x.drive)}</span></td><td>${x.applications}</td><td>${x.offers}</td><td>${x.accepted}</td><td>${x.application_to_offer}%</td><td>${x.offer_acceptance}%</td></tr>`).join('')):emptyState('DR','No drive conversion yet','Drive funnels will appear as applications and offers are recorded.'))}
      ${featurePanel('Top company participation','Application volume across participating employers.',a.top_companies.length?`<div class="rank-list">${a.top_companies.map((x,i)=>`<div class="rank-item"><span>${String(i+1).padStart(2,'0')}</span><div><strong>${esc(x.company)}</strong><small>Authorized campus applicant activity</small></div><b>${x.applications} applications</b></div>`).join('')}</div>`:emptyState('CP','No company participation yet','Employer activity will appear after campus applications begin.'))}`;
    } else if(view==='approvals'){
      setPage('Profile approvals','Student governance'); const rows=await api('/enterprise/profile-change-requests'); $('#app-content').innerHTML=`${pageHead('Student profile approvals','Review sensitive academic changes before they affect eligibility.')} ${rows.length?enterpriseTable(['Student','Field','Current','Requested','Status',''],rows.map(r=>`<tr><td>${esc(r.student_name||'Student')}</td><td>${esc(r.field_name.replaceAll('_',' '))}</td><td>${esc(r.old_value||'—')}</td><td>${esc(r.new_value||'—')}</td><td>${statusBadge(r.status)}</td><td>${r.status==='pending'?`<div class="row-actions"><button class="row-button primary" data-action="review-profile-change" data-id="${r.id}" data-value="approved">Approve</button><button class="row-button" data-action="review-profile-change" data-id="${r.id}" data-value="rejected">Reject</button></div>`:''}</td></tr>`).join('')):emptyState('PA','No changes awaiting review','Sensitive student profile changes will appear here.')}`;
    } else if(view==='verification'){
      setPage('Company verification','Trust'); const recruiters=await api('/institutions/recruiters'); const assessments=await Promise.all(recruiters.map(r=>api(`/enterprise/institution/company-verification/${r.id}`).catch(()=>null))); $('#app-content').innerHTML=`${pageHead('Company Verification Centre','Evidence review across recruiters linked to your institution.')} ${recruiters.length?`<div class="verification-grid">${recruiters.map((r,i)=>{const a=assessments[i]?.assessment;return `<article class="verification-company-card"><div class="operation-card-top"><span class="status-pill">${esc(a?.verification_status||'Not reviewed')}</span><strong>${a?.confidence??0}%</strong></div><h3>${esc(r.company_name||'Company')}</h3><p>${esc(r.full_name||'Recruiter')} · ${esc(r.designation||'')}</p><div class="evidence-mini"><span>CIN <b>${r.cin?'Recorded':'Missing'}</b></span><span>GSTIN <b>${r.gstin?'Recorded':'Missing'}</b></span><span>Institution <b>${r.is_verified?'Verified':'Pending'}</b></span></div><button class="button button-secondary button-full" data-action="company-trust-review" data-id="${r.id}">Open evidence review</button></article>`}).join('')}</div>`:emptyState('CV','No recruiter companies','Provision or connect recruiters to begin company verification.')}`;
    } else if(view==='pipeline'){
      setPage('Drive pipelines','Placement operations'); const drives=await api('/enterprise/drives'); $('#app-content').innerHTML=`${pageHead('Advanced placement drive pipelines','Create role-specific screening, assessment and interview stages.')} ${drives.length?`<div class="card-grid">${drives.map(d=>`<article class="operation-card"><div class="operation-card-top">${statusBadge(d.status)}<small>${fmtDate(d.event_date)}</small></div><h3>${esc(d.title)}</h3><p>${esc(d.company_name||'')} · ${esc(d.job_title||'')}</p><button class="button button-secondary button-full" data-action="view-pipeline" data-id="${d.id}">Configure pipeline</button></article>`).join('')}</div>`:emptyState('PL','No placement drives','Create a placement drive first; a professional default pipeline is installed automatically.')}`;
    } else if(view==='interviews'){
      setPage('Interviews','Placement operations'); const [items,apps]=await Promise.all([api('/enterprise/interviews'),api('/institutions/applications')]); state.enterpriseApps=apps; state.enterpriseInterviews=items; $('#app-content').innerHTML=`${pageHead('Interview & assessment scheduler','Coordinate slots, modes, venues, attendance and human evaluation.','Schedule interview','open-interview-form')}<button class="hidden" data-action="open-interview-form"></button>${items.length?enterpriseTable(['Student','Round / role','Schedule','Mode','Attendance','Result','Actions'],items.map(i=>`<tr><td>${esc(i.student_name||'Student')}</td><td><span class="table-primary">${esc(i.round_name)}</span><span class="table-secondary">${esc(i.job_title||'')}</span></td><td>${fmtDateTime(i.scheduled_at)}</td><td>${esc(i.mode)}</td><td>${esc(i.attendance_status)}</td><td>${esc(i.result||'—')}</td><td><div class="row-actions compact"><button class="row-button" data-action="manage-interview" data-id="${i.id}">Manage</button><button class="row-button" data-action="evaluate-interview" data-id="${i.id}">Evaluation</button></div></td></tr>`).join('')):emptyState('IV','No interviews scheduled','Schedule a round for any campus applicant.')}`;
    } else if(view==='offers'){
      setPage('Offer management','Placement outcomes'); const [offers,apps]=await Promise.all([api('/enterprise/offers'),api('/institutions/applications')]); state.enterpriseApps=apps; state.enterpriseOffers=offers; $('#app-content').innerHTML=`${pageHead('Offer management','Record CTC structure, offer lifecycle, PPO status and joining outcomes.','Create offer','open-offer-form')}<button class="hidden" data-action="open-offer-form"></button>${offers.length?enterpriseTable(['Student','Company / role','CTC','Status','Joining','Offer letter','Actions'],offers.map(o=>`<tr><td>${esc(o.student_name||'Student')}</td><td><span class="table-primary">${esc(o.company_name)}</span><span class="table-secondary">${esc(o.role)}</span></td><td>${o.ctc_lpa!=null?`${o.ctc_lpa} LPA`:'—'}</td><td>${statusBadge(o.status)}</td><td>${fmtDate(o.joining_date)}</td><td>${o.has_offer_letter?`<button class="row-button" data-action="download-offer-letter" data-id="${o.id}">Download</button>`:'Not uploaded'}</td><td><div class="row-actions compact"><select class="filter-select offer-status-select" data-id="${o.id}"><option value="">Update…</option><option value="issued">Issued</option><option value="withdrawn">Withdrawn</option><option value="joining_confirmed">Joining confirmed</option><option value="joined">Joined</option></select><button class="row-button" data-action="upload-offer-letter" data-id="${o.id}">${o.has_offer_letter?'Replace':'Upload'} letter</button></div></td></tr>`).join('')):emptyState('OF','No offers recorded','Create a formal offer against a campus application.')}`;
    } else if(view==='attendance'){
      setPage('QR attendance','Placement operations'); const sessions=await api('/enterprise/attendance/sessions'); $('#app-content').innerHTML=`${pageHead('Placement drive QR attendance','Create check-in sessions for talks, tests, interviews, workshops and physical drives.','New attendance session','open-attendance-form')}<button class="hidden" data-action="open-attendance-form"></button>${sessions.length?`<div class="card-grid">${sessions.map(s=>`<article class="operation-card"><div class="operation-card-top">${s.is_active?statusBadge('approved'):statusBadge('closed')}<strong>${s.checkins} check-ins</strong></div><h3>${esc(s.title)}</h3><p>${esc(s.session_type.replaceAll('_',' '))} · ${fmtDateTime(s.starts_at)}</p><button class="button button-secondary button-full" data-action="show-attendance-qr" data-id="${s.id}">Show QR</button></article>`).join('')}</div>`:emptyState('QR','No attendance sessions','Create a QR session for an upcoming placement activity.')}`;
    } else if(view==='calendar'){
      setPage('Placement calendar','Operations'); const events=await api('/enterprise/calendar'); $('#app-content').innerHTML=`${pageHead('Placement calendar','One operational timeline for deadlines, drives, interviews and joining dates.')}${featurePanel('Institution calendar',`${events.length} scheduled event${events.length===1?'':'s'}.`,timeline(events))}`;
    } else if(view==='announcements'){
      setPage('Announcements','Student communication'); const rows=await api('/enterprise/announcements'); $('#app-content').innerHTML=`${pageHead('Announcement Centre','Target official placement communication by batch, branch or selected students.','Create announcement','open-announcement-form')}<button class="hidden" data-action="open-announcement-form"></button>${rows.length?`<div class="announcement-list">${rows.map(a=>`<article class="announcement-card"><div><span class="priority-label priority-${esc(a.priority)}">${esc(a.priority)}</span><small>${fmtDate(a.created_at)}</small></div><h3>${esc(a.title)}</h3><p>${esc(a.body)}</p><small>Audience: ${esc(a.audience_type.replaceAll('_',' '))}</small></article>`).join('')}</div>`:emptyState('AN','No announcements','Create an institution placement announcement.')}`;
    } else if(view==='communications'){
      setPage('Recruiter communication','Operations'); const [threads,recruiters]=await Promise.all([api('/enterprise/communications'),api('/institutions/recruiters')]); state.enterpriseRecruiters=recruiters; $('#app-content').innerHTML=`${pageHead('Recruiter Communication Hub','Keep company discussions, documents and decisions attached to the campus workflow.','New thread','open-thread-form')}<button class="hidden" data-action="open-thread-form"></button>${threads.length?`<div class="thread-list">${threads.map(t=>`<button class="thread-card" data-action="open-thread" data-id="${t.id}"><strong>${esc(t.subject)}</strong><span>${t.message_count} messages · ${esc(t.status)}</span></button>`).join('')}</div>`:emptyState('CM','No recruiter threads','Start a thread with a recruiter partner.')}`;
    } else if(view==='policies'){
      setPage('Placement policies','Governance'); const rows=await api('/enterprise/policies'); $('#app-content').innerHTML=`${pageHead('Placement Policy Engine','Configure institution rules that are evaluated before students apply.','Create policy','open-policy-form')}${rows.length?`<div class="policy-grid">${rows.map(p=>`<article class="operation-card policy-card"><div class="operation-card-top"><div>${p.is_active?statusBadge('approved'):statusBadge('closed')}<span class="policy-key">${esc(p.policy_key)}</span></div><span class="policy-state-copy">${p.is_active?'Active policy':'Inactive policy'}</span></div><h3>${esc(p.name)}</h3><p>${esc(p.description||'Institution placement policy')}</p><div class="policy-rule-grid">${policyRuleCards(p.rules||{})}</div></article>`).join('')}</div>`:emptyState('PO','No placement policies','Create rules such as maximum offers, block-if-placed or internship exceptions.')}`;
    } else if(view==='custom-fields'){
      setPage('Custom fields','Governance'); const rows=await api('/enterprise/custom-fields'); $('#app-content').innerHTML=`${pageHead('Institution custom fields','Collect institution-specific student data without changing the application schema.','Add custom field','open-custom-field-form')}<button class="hidden" data-action="open-custom-field-form"></button>${rows.length?enterpriseTable(['Field','Key','Type','Required','Options'],rows.map(x=>`<tr><td>${esc(x.label)}</td><td><code>${esc(x.field_key)}</code></td><td>${esc(x.field_type)}</td><td>${x.required?'Yes':'No'}</td><td>${esc((x.options||[]).join(', ')||'—')}</td></tr>`).join('')):emptyState('CF','No custom fields','Add fields such as SAP ID, registration number, hosteller status or minor specialization.')}`;
    } else if(view==='incidents'){
      setPage('Incident reports','Governance'); const rows=await api('/enterprise/incidents'); $('#app-content').innerHTML=`${pageHead('Student incident reports','Confidential review queue for recruiter, job, interview and offer concerns.')}${rows.length?enterpriseTable(['Category','Report','Status','Submitted',''],rows.map(x=>`<tr><td>${esc(x.category)}</td><td>${esc(x.description.slice(0,180))}</td><td>${statusBadge(x.status)}</td><td>${fmtDate(x.created_at)}</td><td><select class="filter-select incident-status-select" data-id="${x.id}"><option value="">Update…</option><option value="investigating">Investigating</option><option value="substantiated">Substantiated</option><option value="resolved">Resolved</option><option value="dismissed">Dismissed</option></select></td></tr>`).join('')):emptyState('IR','No incident reports','Student safety and integrity reports will appear here.')}`;
    } else if(view==='reports'){
      setPage('Reports','Institution reporting'); const reportTypes=[['placement-report','Placement Report'],['department-placement','Department Placement Report'],['company-participation','Company Participation Report'],['unplaced-students','Unplaced Student Report'],['offer-register','Offer Register'],['internship-report','Internship Report'],['recruiter-activity','Recruiter Activity Report']]; $('#app-content').innerHTML=`${pageHead('Institution reports','One-click operational exports for placement review, management and compliance.')}<div class="report-grid">${reportTypes.map(([key,label])=>`<article class="report-card"><span>REPORT</span><h3>${esc(label)}</h3><p>Export the current institution data snapshot.</p><div class="row-actions"><button class="row-button" data-action="download-report" data-id="${key}" data-value="pdf">PDF</button><button class="row-button" data-action="download-report" data-id="${key}" data-value="xlsx">XLSX</button><button class="row-button" data-action="download-report" data-id="${key}" data-value="csv">CSV</button></div></article>`).join('')}</div>`;
    }
  }

  function openInterviewForm(){
    const apps=state.enterpriseApps || (()=>{try{return JSON.parse($('#recruiter-app-cache')?.dataset.apps||'[]')}catch{return[]}})();
    openModal(`<span class="section-kicker">Interview scheduler</span><h2>Schedule interview / assessment</h2><form id="enterprise-interview-form" class="form-stack"><label>Applicant<select name="application_id" required><option value="">Select applicant…</option>${apps.map(a=>`<option value="${a.id}">${esc(a.name||'Candidate')} · ${esc(a.job_title||a.role||'Role')}</option>`).join('')}</select></label><div class="form-two"><label>Round<input name="round_name" required placeholder="Technical Round 1"></label><label>Date & time<input name="scheduled_at" type="datetime-local" required></label></div><div class="form-two"><label>Mode<select name="mode"><option value="online">Online</option><option value="onsite">On-site</option><option value="hybrid">Hybrid</option></select></label><label>Interviewer<input name="interviewer"></label></div><label>Venue<input name="venue"></label><label>Meeting link<input name="meeting_url" type="url"></label><label>Instructions<textarea name="instructions" rows="3"></textarea></label><button class="button button-primary button-full">Schedule interview</button></form>`);
  }
  function openOfferForm(){
    const apps=state.enterpriseApps || (()=>{try{return JSON.parse($('#recruiter-offer-app-cache')?.dataset.apps||'[]')}catch{return[]}})();
    openModal(`<span class="section-kicker">Offer management</span><h2>Create formal offer</h2><form id="enterprise-offer-form" class="form-stack"><label>Applicant<select name="application_id" required><option value="">Select applicant…</option>${apps.map(a=>`<option value="${a.id}">${esc(a.student?.full_name||a.name||'Candidate')} · ${esc(a.job_title||a.role||'Role')}</option>`).join('')}</select></label><div class="form-two"><label>CTC (LPA)<input name="ctc_lpa" type="number" min="0" step="0.01"></label><label>Fixed pay (LPA)<input name="fixed_pay_lpa" type="number" min="0" step="0.01"></label></div><div class="form-two"><label>Variable pay (LPA)<input name="variable_pay_lpa" type="number" min="0" step="0.01"></label><label>Location<input name="location"></label></div><label>Joining date<input name="joining_date" type="date"></label><label>Bond / service agreement<textarea name="bond_terms" rows="2"></textarea></label><div class="form-two"><label>Internship stipend<input name="internship_stipend" type="number" min="0"></label><label>PPO status<input name="ppo_status" placeholder="Not applicable / Eligible / Confirmed"></label></div><button class="button button-primary button-full">Create offer</button></form>`);
  }
  function openAttendanceForm(){openModal(`<span class="section-kicker">QR attendance</span><h2>Create attendance session</h2><form id="attendance-session-form" class="form-stack"><label>Session title<input name="title" required placeholder="Acme pre-placement talk"></label><label>Session type<select name="session_type"><option value="placement_drive">Placement drive</option><option value="pre_placement_talk">Pre-placement talk</option><option value="assessment">Assessment</option><option value="interview">Interview</option><option value="workshop">Workshop</option></select></label><div class="form-two"><label>Starts at<input name="starts_at" type="datetime-local"></label><label>Closes at<input name="closes_at" type="datetime-local"></label></div><button class="button button-primary button-full">Create QR session</button></form>`);}
  function openAnnouncementForm(){openModal(`<span class="section-kicker">Announcement centre</span><h2>Create announcement</h2><form id="announcement-form" class="form-stack"><label>Title<input name="title" required></label><label>Message<textarea name="body" rows="5" required></textarea></label><div class="form-two"><label>Audience<select name="audience_type"><option value="all_students">All students</option><option value="branch">Branch</option><option value="batch">Graduation batch</option><option value="eligible_students">Eligible students for a drive</option><option value="drive_participants">Specific drive participants</option></select></label><label>Priority<select name="priority"><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option></select></label></div><label>Audience values <span class="field-help">Branches/years, or a drive ID for eligible/participant audiences</span><input name="audience_values"></label><button class="button button-primary button-full">Publish announcement</button></form>`);}
  function policyRuleLabel(key) {
    const labels = {
      max_offers_per_student: 'Maximum active offers',
      min_next_offer_lpa: 'Minimum next offer',
      placed_salary_floor_multiplier: 'Required salary improvement',
      dream_company_min_ctc_lpa: 'Dream-company threshold',
      block_if_placed: 'Block already placed students',
      internship_offers_do_not_block: 'Internships do not consume offer limit',
      dream_company_exception: 'Dream-company exception'
    };
    return labels[key] || key.replaceAll('_',' ').replace(/\b\w/g, c => c.toUpperCase());
  }

  function policyRuleValue(key, value) {
    if (typeof value === 'boolean') return value ? 'Enabled' : 'Disabled';
    if (key === 'max_offers_per_student') return `${value} offer${Number(value) === 1 ? '' : 's'}`;
    if (key === 'min_next_offer_lpa' || key === 'dream_company_min_ctc_lpa') return `₹${value} LPA`;
    if (key === 'placed_salary_floor_multiplier') return `${value}× current offer`;
    if (Array.isArray(value)) return value.join(', ');
    if (value && typeof value === 'object') return 'Configured';
    return String(value ?? '—');
  }

  function policyRuleCards(rules) {
    const entries = Object.entries(rules || {});
    if (!entries.length) return '<div class="policy-rule-empty">No rules configured.</div>';
    return entries.map(([key,value]) => `<div class="policy-rule"><span>${esc(policyRuleLabel(key))}</span><strong>${esc(policyRuleValue(key,value))}</strong></div>`).join('');
  }

  function openPolicyForm(){openModal(`<span class="section-kicker">Policy engine</span><h2>Create placement policy</h2><p class="form-intro">Configure transparent participation rules. PlaceAI will explain any restriction to the student instead of silently blocking an application.</p><form id="policy-form" class="form-stack"><label>Policy name<input name="name" required placeholder="Offer participation policy"></label><label>Policy key<input name="policy_key" required placeholder="offer-participation"></label><label>Description<textarea name="description" rows="3"></textarea></label><div class="form-two"><label>Maximum active offers<input name="max_offers_per_student" type="number" min="0"></label><label>Minimum next offer (LPA)<input name="min_next_offer_lpa" type="number" min="0" step="0.1" placeholder="e.g. 10"></label></div><div class="form-two"><label>Placed salary improvement multiplier<input name="placed_salary_floor_multiplier" type="number" min="1" step="0.05" placeholder="e.g. 1.25"></label><label>Dream-company threshold (LPA)<input name="dream_company_min_ctc_lpa" type="number" min="0" step="0.1" placeholder="e.g. 12"></label></div><label class="check-label"><input name="block_if_placed" type="checkbox"> Block already placed students unless an exception applies</label><label class="check-label"><input name="internship_offers_do_not_block" type="checkbox"> Internship opportunities do not consume placement-offer limits</label><label class="check-label"><input name="dream_company_exception" type="checkbox"> Allow dream-company exception at/above the configured threshold</label><button class="button button-primary button-full">Save policy</button></form>`);}
  function openCustomFieldForm(){openModal(`<span class="section-kicker">Custom institution data</span><h2>Add custom student field</h2><form id="custom-field-form" class="form-stack"><label>Field label<input name="label" required placeholder="University Registration No."></label><label>Field key<input name="field_key" required placeholder="university_registration_no"></label><div class="form-two"><label>Field type<select name="field_type"><option value="text">Text</option><option value="number">Number</option><option value="select">Select</option><option value="boolean">Yes / No</option></select></label><label class="check-label"><input type="checkbox" name="required"> Required</label></div><label>Options <span class="field-help">Comma separated for select fields</span><input name="options"></label><button class="button button-primary button-full">Add custom field</button></form>`);}
  function openThreadForm(){ const recruiters=state.enterpriseRecruiters||[]; openModal(`<span class="section-kicker">Recruiter communication</span><h2>Start discussion thread</h2><form id="thread-form" class="form-stack">${state.me.role==='institution_admin'?`<label>Recruiter<select name="recruiter_profile_id"><option value="">Select recruiter…</option>${recruiters.map(r=>`<option value="${r.id}">${esc(r.company_name||'Company')} · ${esc(r.full_name||'Recruiter')}</option>`).join('')}</select></label>`:''}<label>Subject<input name="subject" required placeholder="2027 campus drive coordination"></label><button class="button button-primary button-full">Create thread</button></form>`); }
  async function openThread(id){const msgs=await api(`/enterprise/communications/${id}/messages`);openModal(`<span class="section-kicker">Placement communication</span><h2>Conversation</h2><p class="form-intro">Keep recruiter and placement-office decisions, instructions and supporting documents in one auditable thread.</p><div class="message-thread">${msgs.length?msgs.map(m=>`<article class="message-bubble ${m.sender_user_id===state.me.id?'own':''}"><strong>${esc(m.sender_email)}</strong><p>${esc(m.message)}</p>${m.has_attachment?`<button class="attachment-chip" data-action="download-thread-attachment" data-id="${m.id}" data-value="${id}">${navIcon('documents')}<span>${esc(m.attachment_filename||'Attachment')}</span><small>${m.attachment_size?`${Math.max(1,Math.round(m.attachment_size/1024))} KB`:''}</small></button>`:''}<small>${fmtDateTime(m.created_at)}</small></article>`).join(''):'<p>No messages yet.</p>'}</div><div class="communication-compose"><form id="thread-message-form" class="form-stack"><input type="hidden" name="thread_id" value="${id}"><label>Message<textarea name="message" rows="3" required placeholder="Add an instruction, decision or update…"></textarea></label><button class="button button-primary button-full">Send message</button></form><form id="thread-attachment-form" class="form-stack attachment-form"><input type="hidden" name="thread_id" value="${id}"><label>Supporting document<input id="thread-attachment-file" type="file" accept=".pdf,.docx,.xlsx,.csv,.txt,.png,.jpg,.jpeg" required></label><label>Document note<input name="message" maxlength="500" placeholder="e.g. Assessment schedule and candidate instructions"></label><button class="button button-secondary button-full">Attach document</button></form></div>`);}
  async function openPipeline(id){
    const stages=await api(`/enterprise/drives/${id}/pipeline`);
    const canEdit=state.me?.role==='institution_admin';
    const stageList=stages.length
      ? `<div class="pipeline-stage-list">${stages.map((s,i)=>`<div class="pipeline-stage"><span>${String(i+1).padStart(2,'0')}</span><div><strong>${esc(s.name)}</strong><small>${esc(s.stage_type)}</small></div>${s.is_terminal?'<b>Final</b>':''}</div>`).join('')}</div>`
      : emptyState('PL','No pipeline stages','The placement office has not configured stages for this drive yet.');
    const controls=canEdit
      ? `<form id="pipeline-stage-form" class="form-stack"><input type="hidden" name="drive_id" value="${id}"><div class="form-two"><label>New stage name<input name="name" required></label><label>Stage type<select name="stage_type"><option value="screening">Screening</option><option value="assessment">Assessment</option><option value="interview">Interview</option><option value="offer">Offer</option><option value="custom">Custom</option></select></label></div><button class="button button-secondary button-full">Add stage</button></form>`
      : `<div class="note-box"><strong>Institution-controlled pipeline</strong><p>Pipeline structure is controlled by the institution placement office. Recruiters can review stages and move authorized applicants, but cannot alter the institution-owned stage design.</p></div>`;
    openModal(`<span class="section-kicker">Drive pipeline</span><h2>Screening & interview stages</h2>${stageList}${controls}`);
  }
  function openEvaluation(id){openModal(`<span class="section-kicker">Human interview assessment</span><h2>Structured evaluation</h2><form id="interview-evaluation-form" class="form-stack"><input type="hidden" name="interview_id" value="${id}"><div class="form-two"><label>Technical knowledge /10<input name="technical_knowledge" type="number" min="0" max="10"></label><label>Communication /10<input name="communication" type="number" min="0" max="10"></label></div><div class="form-two"><label>Problem solving /10<input name="problem_solving" type="number" min="0" max="10"></label><label>Role fit /10<input name="role_fit" type="number" min="0" max="10"></label></div><label>Recommendation<select name="recommendation"><option value="Proceed">Proceed</option><option value="Hold">Hold</option><option value="Reject">Reject</option></select></label><label>Human notes<textarea name="notes" rows="4"></textarea></label><button class="button button-primary button-full">Save human evaluation</button></form>`);}
  function openInterviewManage(id){ const rows=[...(state.recruiterInterviews||[]),...(state.enterpriseInterviews||[])]; const i=rows.find(x=>x.id===id); if(!i){toast('Interview unavailable','Refresh the interview workspace and try again.','error');return;} openModal(`<span class="section-kicker">Interview operations</span><h2>Manage ${esc(i.round_name)}</h2><p class="form-intro">Reschedule the slot, update attendance, or record the round result. Human evaluation remains separate.</p><form id="interview-manage-form" class="form-stack"><input type="hidden" name="interview_id" value="${esc(i.id)}"><div class="form-two"><label>Date & time<input name="scheduled_at" type="datetime-local" value="${esc(toDateTimeLocal(i.scheduled_at))}" required></label><label>Mode<select name="mode"><option value="online" ${i.mode==='online'?'selected':''}>Online</option><option value="offline" ${i.mode==='offline'?'selected':''}>On campus / offline</option><option value="hybrid" ${i.mode==='hybrid'?'selected':''}>Hybrid</option></select></label></div><div class="form-two"><label>Venue<input name="venue" value="${esc(i.venue||'')}"></label><label>Meeting URL<input name="meeting_url" type="url" value="${esc(i.meeting_url||'')}"></label></div><div class="form-two"><label>Interviewer<input name="interviewer" value="${esc(i.interviewer||'')}"></label><label>Student slot<input name="student_slot" value="${esc(i.student_slot||'')}"></label></div><div class="form-three"><label>Status<select name="status"><option value="scheduled" ${i.status==='scheduled'?'selected':''}>Scheduled</option><option value="rescheduled" ${i.status==='rescheduled'?'selected':''}>Rescheduled</option><option value="completed" ${i.status==='completed'?'selected':''}>Completed</option><option value="cancelled" ${i.status==='cancelled'?'selected':''}>Cancelled</option></select></label><label>Attendance<select name="attendance_status"><option value="pending" ${i.attendance_status==='pending'?'selected':''}>Pending</option><option value="present" ${i.attendance_status==='present'?'selected':''}>Present</option><option value="absent" ${i.attendance_status==='absent'?'selected':''}>Absent</option></select></label><label>Result<select name="result"><option value="pending" ${i.result==='pending'?'selected':''}>Pending</option><option value="proceed" ${i.result==='proceed'?'selected':''}>Proceed</option><option value="hold" ${i.result==='hold'?'selected':''}>Hold</option><option value="reject" ${i.result==='reject'?'selected':''}>Reject</option><option value="passed" ${i.result==='passed'?'selected':''}>Passed</option><option value="failed" ${i.result==='failed'?'selected':''}>Failed</option></select></label></div><label>Instructions<textarea name="instructions" rows="4">${esc(i.instructions||'')}</textarea></label><button class="button button-primary button-full">Save interview update</button></form>`); }
  function openOfferLetterForm(id){openModal(`<span class="section-kicker">Offer document</span><h2>Upload offer letter</h2><p class="form-intro">Attach the formal PDF so the authorized student, recruiter and placement team can access the same controlled document.</p><form id="offer-letter-form" class="form-stack"><input type="hidden" name="offer_id" value="${esc(id)}"><label>Offer letter PDF<input id="offer-letter-file" type="file" accept="application/pdf,.pdf" required></label><small class="field-help">PDF only · maximum 8 MB</small><button class="button button-primary button-full">Upload offer letter</button></form>`); }

  async function openNotificationPreferences(){const p=await api('/enterprise/notification-preferences');openModal(`<span class="section-kicker">Notifications</span><h2>Notification preferences</h2><form id="notification-preferences-form" class="form-stack"><label class="toggle-row"><span><strong>In-app notifications</strong><small>Placement events inside PlaceAI</small></span><input type="checkbox" name="in_app" ${p.in_app?'checked':''}></label><div class="note-box"><strong>External delivery</strong><p>External notification channels are not exposed until a production delivery provider is configured for workspace events.</p></div><button class="button button-primary button-full">Save preferences</button></form>`);}

  async function downloadAuthorized(path,filename){const r=await fetch(path,{headers:{Authorization:`Bearer ${state.token}`}});if(!r.ok){let d='Download failed';try{d=(await r.json()).detail||d}catch{}throw new Error(d)}const blob=await r.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=filename||'placeai-export';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);}

  // Enterprise action handlers are intentionally separate from the legacy handler so the
  // original working flows remain untouched.
  document.addEventListener('click',async e=>{
    const el=e.target.closest('[data-action]');if(!el)return;const a=el.dataset.action,id=el.dataset.id,val=el.dataset.value;
    try{
      if(a==='mark-notifications-read'){await api('/enterprise/notifications/read-all',{method:'POST'});toast('Notifications marked as read');await renderNotifications();}
      else if(a==='open-notification'){await api(`/enterprise/notifications/${id}/read`,{method:'PATCH'});await updateNotificationBadge();await navigate(notificationTarget(val));}
      else if(a==='notification-preferences')await openNotificationPreferences();
      else if(a==='assistant-suggestion'){const input=$('#assistant-form textarea');if(input){input.value=val;input.focus();}}
      else if(a==='view-pipeline')await openPipeline(id);
      else if(a==='open-interview-form')openInterviewForm();
      else if(a==='manage-interview')openInterviewManage(id);
      else if(a==='evaluate-interview')openEvaluation(id);
      else if(a==='upload-offer-letter')openOfferLetterForm(id);
      else if(a==='download-offer-letter'){try{await downloadAuthorized(`/enterprise/offers/${id}/letter`,'PlaceAI-offer-letter.pdf')}catch(err){toast('Offer letter unavailable',err.message,'error')}}
      else if(a==='open-offer-form')openOfferForm();
      else if(a==='student-offer-decision'){await api(`/enterprise/offers/${id}`,{method:'PATCH',body:JSON.stringify({status:val})});toast('Offer decision saved');navigate('offers');}
      else if(a==='open-attendance-form')openAttendanceForm();
      else if(a==='show-attendance-qr'){
        openModal(`<span class="section-kicker">QR attendance</span><h2>Student check-in QR</h2><p class="form-intro">Students scan this while signed in to PlaceAI. The QR uses the same host that opened this workspace, so it also works from a phone when the site is reachable there.</p><div class="qr-frame" id="attendance-qr-frame"><div class="qr-loading"><span class="loader"></span><span>Generating secure QR…</span></div></div><p class="form-intro qr-help">Keep this dialog open during check-in. Students must use an account linked to this institution.</p>`);
        const r=await fetch(`/enterprise/attendance/sessions/${id}/qr`,{headers:{Authorization:`Bearer ${state.token}`}});
        const frame=$('#attendance-qr-frame');
        if(!r.ok){let detail='Could not generate the QR code.';try{detail=(await r.json()).detail||detail}catch{}if(frame)frame.innerHTML=`<div class="qr-error"><strong>QR unavailable</strong><span>${esc(detail)}</span></div>`;throw new Error(detail);}
        const blob=await r.blob();
        const u=URL.createObjectURL(blob);
        if(frame)frame.innerHTML=`<img src="${u}" alt="Student attendance check-in QR code">`;
        setTimeout(()=>URL.revokeObjectURL(u),60000);
      }
      else if(a==='open-announcement-form')openAnnouncementForm();
      else if(a==='open-policy-form')openPolicyForm();
      else if(a==='open-custom-field-form')openCustomFieldForm();
      else if(a==='open-thread-form')openThreadForm();
      else if(a==='open-thread')await openThread(id);
      else if(a==='download-thread-attachment')await downloadAuthorized(`/enterprise/communications/${val}/messages/${id}/attachment`,'placeai-attachment');
      else if(a==='download-report')await downloadAuthorized(`/enterprise/reports/${id}.${val}`,`${id}.${val}`);
      else if(a==='download-vault-document')await downloadAuthorized(`/enterprise/documents/${id}/download`,'student-document');
      else if(a==='review-profile-change'){await api(`/enterprise/profile-change-requests/${id}`,{method:'PATCH',body:JSON.stringify({status:val})});toast(`Change ${val}`);navigate('approvals');}
    }catch(err){toast('Action failed',err.message,'error');}
  });

  document.addEventListener('change',async e=>{
    try{
      if(e.target.classList.contains('offer-status-select')&&e.target.value){await api(`/enterprise/offers/${e.target.dataset.id}`,{method:'PATCH',body:JSON.stringify({status:e.target.value})});toast('Offer status updated');navigate('offers');}
      else if(e.target.classList.contains('incident-status-select')&&e.target.value){await api(`/enterprise/incidents/${e.target.dataset.id}`,{method:'PATCH',body:JSON.stringify({status:e.target.value})});toast('Incident status updated');navigate('incidents');}
    }catch(err){toast('Update failed',err.message,'error');}
  });

  document.addEventListener('submit',async e=>{
    const f=e.target;if(!['assistant-form','document-upload-form','verification-profile-form','authorization-letter-form','enterprise-interview-form','enterprise-offer-form','attendance-session-form','announcement-form','policy-form','custom-field-form','thread-form','thread-message-form','thread-attachment-form','pipeline-stage-form','interview-evaluation-form','incident-form','notification-preferences-form'].includes(f.id))return;
    e.preventDefault();const fd=new FormData(f);const o=Object.fromEntries(fd.entries());
    try{
      if(f.id==='assistant-form'){const transcript=$('#assistant-transcript');transcript.insertAdjacentHTML('beforeend',`<div class="assistant-message user"><strong>You</strong><p>${esc(o.message)}</p></div><div class="assistant-message system pending"><strong>PlaceAI Assistant</strong><p>Reviewing your authorized placement context…</p></div>`);const r=await api('/ai/assistant',{method:'POST',body:JSON.stringify({message:o.message})});transcript.querySelector('.pending')?.remove();transcript.insertAdjacentHTML('beforeend',`<div class="assistant-message system"><strong>PlaceAI Assistant</strong><p>${esc(r.answer)}</p><small>${esc(r.guardrail)}</small></div>`);f.reset();transcript.scrollTop=transcript.scrollHeight;}
      else if(f.id==='document-upload-form'){const file=$('#student-document-file')?.files[0];if(!file)throw new Error('Choose a document first');const body=new FormData();body.append('file',file);await api(`/enterprise/documents?document_type=${encodeURIComponent(o.document_type)}&visibility=${encodeURIComponent(o.visibility)}`,{method:'POST',body});toast('Document uploaded');navigate('documents');}
      else if(f.id==='verification-profile-form'){const data={...o,past_college_relationships:String(o.past_college_relationships||'').split(',').map(x=>x.trim()).filter(Boolean),previous_successful_placements:o.previous_successful_placements?Number(o.previous_successful_placements):0};await api('/recruiters/profile',{method:'PUT',body:JSON.stringify(data)});toast('Company evidence saved');navigate('verification');}
      else if(f.id==='authorization-letter-form'){const file=$('#authorization-letter-file')?.files[0];if(!file)throw new Error('Choose the authorization letter PDF');const body=new FormData();body.append('file',file);await api('/enterprise/company-verification/authorization-letter',{method:'POST',body});toast('Authorization evidence uploaded');navigate('verification');}
      else if(f.id==='enterprise-interview-form'){const data={...o,scheduled_at:new Date(o.scheduled_at).toISOString()};await api('/enterprise/interviews',{method:'POST',body:JSON.stringify(data)});closeModal();toast('Interview scheduled');navigate('interviews');}
      else if(f.id==='interview-manage-form'){const data={scheduled_at:new Date(o.scheduled_at).toISOString(),mode:o.mode,venue:o.venue||null,meeting_url:o.meeting_url||null,interviewer:o.interviewer||null,student_slot:o.student_slot||null,instructions:o.instructions||null,status:o.status,attendance_status:o.attendance_status,result:o.result};await api(`/enterprise/interviews/${o.interview_id}`,{method:'PATCH',body:JSON.stringify(data)});closeModal();toast('Interview updated');navigate('interviews');}
      else if(f.id==='offer-letter-form'){const file=$('#offer-letter-file')?.files[0];if(!file)throw new Error('Choose the offer-letter PDF');const body=new FormData();body.append('file',file);await api(`/enterprise/offers/${o.offer_id}/letter`,{method:'POST',body});closeModal();toast('Offer letter uploaded');navigate('offers');}
      else if(f.id==='enterprise-offer-form'){const data={...o,ctc_lpa:o.ctc_lpa?Number(o.ctc_lpa):null,fixed_pay_lpa:o.fixed_pay_lpa?Number(o.fixed_pay_lpa):null,variable_pay_lpa:o.variable_pay_lpa?Number(o.variable_pay_lpa):null,internship_stipend:o.internship_stipend?Number(o.internship_stipend):null,joining_date:o.joining_date?new Date(o.joining_date).toISOString():null};await api('/enterprise/offers',{method:'POST',body:JSON.stringify(data)});closeModal();toast('Offer created');navigate('offers');}
      else if(f.id==='attendance-session-form'){const data={...o,starts_at:o.starts_at?new Date(o.starts_at).toISOString():null,closes_at:o.closes_at?new Date(o.closes_at).toISOString():null};await api('/enterprise/attendance/sessions',{method:'POST',body:JSON.stringify(data)});closeModal();toast('Attendance session created');navigate('attendance');}
      else if(f.id==='announcement-form'){const vals=String(o.audience_values||'').split(',').map(x=>x.trim()).filter(Boolean);const audience_value=o.audience_type==='branch'?{branches:vals}:o.audience_type==='batch'?{graduation_years:vals.map(Number).filter(Boolean)}:{};await api('/enterprise/announcements',{method:'POST',body:JSON.stringify({title:o.title,body:o.body,audience_type:o.audience_type,audience_value,priority:o.priority})});closeModal();toast('Announcement published');navigate('announcements');}
      else if(f.id==='policy-form'){const rules={};if(o.max_offers_per_student)rules.max_offers_per_student=Number(o.max_offers_per_student);if(o.min_next_offer_lpa)rules.min_next_offer_lpa=Number(o.min_next_offer_lpa);if(o.placed_salary_floor_multiplier)rules.placed_salary_floor_multiplier=Number(o.placed_salary_floor_multiplier);if(o.dream_company_min_ctc_lpa)rules.dream_company_min_ctc_lpa=Number(o.dream_company_min_ctc_lpa);if(fd.has('block_if_placed'))rules.block_if_placed=true;if(fd.has('internship_offers_do_not_block'))rules.internship_offers_do_not_block=true;if(fd.has('dream_company_exception'))rules.dream_company_exception=true;await api('/enterprise/policies',{method:'POST',body:JSON.stringify({policy_key:o.policy_key,name:o.name,description:o.description||null,rules,is_active:true})});closeModal();toast('Placement policy created');navigate('policies');}
      else if(f.id==='custom-field-form'){await api('/enterprise/custom-fields',{method:'POST',body:JSON.stringify({label:o.label,field_key:o.field_key,field_type:o.field_type,required:fd.has('required'),options:String(o.options||'').split(',').map(x=>x.trim()).filter(Boolean),entity_type:'student'})});closeModal();toast('Custom field added');navigate('custom-fields');}
      else if(f.id==='thread-form'){await api('/enterprise/communications',{method:'POST',body:JSON.stringify({recruiter_profile_id:o.recruiter_profile_id||null,subject:o.subject})});closeModal();toast('Discussion thread created');navigate('communications');}
      else if(f.id==='thread-message-form'){await api(`/enterprise/communications/${o.thread_id}/messages`,{method:'POST',body:JSON.stringify({message:o.message})});toast('Message sent');await openThread(o.thread_id);}
      else if(f.id==='thread-attachment-form'){const file=$('#thread-attachment-file')?.files[0];if(!file)throw new Error('Choose a document first');const body=new FormData();body.append('file',file);const note=String(o.message||'').trim();await api(`/enterprise/communications/${o.thread_id}/attachments?message=${encodeURIComponent(note||'Shared a placement document.')}`,{method:'POST',body});toast('Document attached');await openThread(o.thread_id);}
      else if(f.id==='pipeline-stage-form'){await api(`/enterprise/drives/${o.drive_id}/pipeline`,{method:'POST',body:JSON.stringify({name:o.name,stage_type:o.stage_type})});toast('Pipeline stage added');await openPipeline(o.drive_id);}
      else if(f.id==='interview-evaluation-form'){const data={technical_knowledge:o.technical_knowledge?Number(o.technical_knowledge):null,communication:o.communication?Number(o.communication):null,problem_solving:o.problem_solving?Number(o.problem_solving):null,role_fit:o.role_fit?Number(o.role_fit):null,recommendation:o.recommendation,notes:o.notes};await api(`/enterprise/interviews/${o.interview_id}/evaluation`,{method:'PUT',body:JSON.stringify(data)});closeModal();toast('Human evaluation saved');navigate('interviews');}
      else if(f.id==='incident-form'){await api('/enterprise/incidents',{method:'POST',body:JSON.stringify({category:o.category,description:o.description,confidential:fd.has('confidential')})});toast('Incident report submitted');navigate('incidents');}
      else if(f.id==='notification-preferences-form'){await api('/enterprise/notification-preferences',{method:'PUT',body:JSON.stringify({in_app:fd.has('in_app'),email:fd.has('email'),whatsapp:fd.has('whatsapp'),sms:fd.has('sms'),high_priority_only_external:fd.has('high_priority_only_external')})});closeModal();toast('Notification preferences saved');}
    }catch(err){apiErrors.applyToForm(f,err);toast('Could not complete request',err.message,'error');}
  });

  // Ctrl/Cmd + K command palette for fast role-scoped navigation.
  function openCommandPalette(){ const p=$('#command-palette');if(!p)return;p.classList.remove('hidden');const input=$('#command-search');input.value='';$('#command-results').innerHTML='<div class="command-hint">Search students, jobs, candidates or opportunities.</div>';setTimeout(()=>input.focus(),20); }
  function closeCommandPalette(){ $('#command-palette')?.classList.add('hidden'); }
  document.addEventListener('keydown',e=>{
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openCommandPalette();}
    if(e.key==='Tab') trapModalTab(e);
    if(e.key==='Escape'){
      if(!$('#command-palette')?.classList.contains('hidden')) closeCommandPalette();
      else if(!$('#generic-modal')?.classList.contains('hidden')) closeModal();
      else if(!$('#auth-overlay')?.classList.contains('hidden')) closeAuth();
    }
  });
  document.addEventListener('click',e=>{if(e.target.closest('[data-action="open-command-palette"]'))openCommandPalette();if(e.target.closest('[data-action="close-command-palette"]'))closeCommandPalette();const hit=e.target.closest('[data-command-view]');if(hit){closeCommandPalette();navigate(hit.dataset.commandView);}});
  let commandTimer=null;document.addEventListener('input',e=>{if(e.target.id!=='command-search')return;clearTimeout(commandTimer);commandTimer=setTimeout(async()=>{const q=e.target.value.trim();if(!q){$('#command-results').innerHTML='<div class="command-hint">Search students, jobs, candidates or opportunities.</div>';return;}try{const rows=await api(`/enterprise/search?q=${encodeURIComponent(q)}`);$('#command-results').innerHTML=rows.length?rows.map(x=>`<button class="command-result" data-command-view="${esc(x.view)}"><span class="command-result-icon">${esc((x.type||'?').slice(0,2).toUpperCase())}</span><span><strong>${esc(x.title)}</strong><small>${esc(x.subtitle||'')}</small></span><em>${esc(x.type||'record')}</em></button>`).join(''):'<div class="command-hint">No matching workspace records.</div>';}catch(err){$('#command-results').innerHTML=`<div class="command-hint">${esc(err.message)}</div>`;}},180);});


  async function handleResetToken(){const params=new URLSearchParams(location.search);const token=params.get('reset_token');if(!token)return false;const cleanUrl=new URL(location.href);cleanUrl.searchParams.delete('reset_token');history.replaceState({},'',cleanUrl.pathname+cleanUrl.search);showAuth('login');openModal(`<span class="section-kicker">Account recovery</span><h2>Set a new password</h2><form id="reset-password-form" class="form-stack"><input type="hidden" name="token" value="${esc(token)}"><label>New password<input type="password" name="new_password" minlength="12" required></label><button class="button button-primary button-full">Reset password</button></form>`);const form=$('#reset-password-form');form.addEventListener('submit',async e=>{e.preventDefault();const fd=new FormData(form);try{await api('/auth/reset-password',{method:'POST',body:JSON.stringify(Object.fromEntries(fd.entries()))},false);closeModal();history.replaceState({},'',location.pathname);toast('Password reset','You can now sign in with the new password.');showAuth('login');}catch(err){apiErrors.applyToForm(form,err);toast('Reset failed',err.message,'error')}});return true;}

  (async()=>{trackPageView(location.pathname);await handleResetToken();await bootWorkspace();})();
})();
