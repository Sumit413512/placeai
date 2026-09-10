(() => {
  'use strict';

  const STORAGE_KEY = 'placeai.workspace.view.v1';
  const SESSION_HINT_KEY = 'placeai.session.active.v1';
  const VIEW_PARAM = 'view';
  const SAFE_VIEW = /^[a-z0-9-]{1,48}$/;
  const originalFetch = window.fetch.bind(window);
  let runtimeToken = '';
  let refreshInFlight = null;

  const safeSessionGet = key => {
    try { return sessionStorage.getItem(key); } catch { return null; }
  };
  const safeSessionSet = (key, value) => {
    try { sessionStorage.setItem(key, value); } catch {}
  };
  const safeSessionRemove = key => {
    try { sessionStorage.removeItem(key); } catch {}
  };

  const normalizeView = value => {
    const view = String(value || '').trim().toLowerCase();
    return SAFE_VIEW.test(view) ? view : '';
  };

  const sameOriginPath = input => {
    try {
      const raw = input instanceof Request ? input.url : String(input);
      const url = new URL(raw, location.href);
      return url.origin === location.origin ? url.pathname : '';
    } catch { return ''; }
  };

  const mergedHeaders = (input, init) => {
    const headers = new Headers(input instanceof Request ? input.headers : undefined);
    new Headers(init?.headers || {}).forEach((value, key) => headers.set(key, value));
    return headers;
  };

  const isLoginPath = path => ['/auth/login', '/auth/login-json', '/auth/login-role', '/auth/google'].includes(path);
  const isAuthControlPath = path => isLoginPath(path) || ['/auth/signup', '/auth/refresh', '/auth/logout'].includes(path);

  async function refreshRuntimeToken() {
    if (refreshInFlight) return refreshInFlight;
    refreshInFlight = (async () => {
      try {
        const response = await originalFetch('/auth/refresh', {
          method: 'POST',
          credentials: 'include',
          headers: {'Content-Type': 'application/json'},
          body: '{}'
        });
        if (!response.ok) {
          runtimeToken = '';
          safeSessionRemove(SESSION_HINT_KEY);
          return '';
        }
        const payload = await response.json();
        runtimeToken = typeof payload?.access_token === 'string' ? payload.access_token : '';
        if (runtimeToken) safeSessionSet(SESSION_HINT_KEY, '1');
        return runtimeToken;
      } catch {
        runtimeToken = '';
        return '';
      } finally {
        refreshInFlight = null;
      }
    })();
    return refreshInFlight;
  }

  // Keep JWTs memory-only. The HttpOnly refresh cookie remains the authoritative
  // persistent session; this shim only makes reload bootstrap deterministic.
  window.fetch = async function placeaiSessionFetch(input, init = {}) {
    const path = sameOriginPath(input);
    let headers = mergedHeaders(input, init);
    let requestInit = {...init};

    if (runtimeToken && path && !isAuthControlPath(path) && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${runtimeToken}`);
      requestInit.headers = headers;
    }

    let response = await originalFetch(input, requestInit);

    if (response.ok && isLoginPath(path)) {
      safeSessionSet(SESSION_HINT_KEY, '1');
      try {
        const payload = await response.clone().json();
        if (typeof payload?.access_token === 'string') runtimeToken = payload.access_token;
      } catch {}
    }

    if (path === '/auth/logout' && response.ok) {
      runtimeToken = '';
      safeSessionRemove(SESSION_HINT_KEY);
      safeSessionRemove(STORAGE_KEY);
      return response;
    }

    if (response.status === 401 && path && !isAuthControlPath(path) && !headers.has('Authorization')) {
      const token = await refreshRuntimeToken();
      if (token) {
        headers = mergedHeaders(input, init);
        headers.set('Authorization', `Bearer ${token}`);
        response = await originalFetch(input, {...init, headers, credentials: 'include'});
      }
    }

    return response;
  };

  const viewFromUrl = () => {
    try { return normalizeView(new URL(location.href).searchParams.get(VIEW_PARAM)); }
    catch { return ''; }
  };

  const initialDesiredView = viewFromUrl() || normalizeView(safeSessionGet(STORAGE_KEY));
  let restoringInitialView = Boolean(initialDesiredView && initialDesiredView !== 'dashboard');
  let restoreTimer = null;

  function writeViewUrl(view) {
    try {
      const url = new URL(location.href);
      if (!view || view === 'dashboard') url.searchParams.delete(VIEW_PARAM);
      else url.searchParams.set(VIEW_PARAM, view);
      history.replaceState(
        {...(history.state || {}), placeaiView: view || 'dashboard'},
        '',
        `${url.pathname}${url.search}${url.hash}`
      );
    } catch {}
  }

  function rememberView(value) {
    const view = normalizeView(value);
    if (!view || view === 'mock-interview') return;
    safeSessionSet(STORAGE_KEY, view);
    writeViewUrl(view);
  }

  function clearView() {
    safeSessionRemove(STORAGE_KEY);
    writeViewUrl('');
  }

  function workspaceVisible() {
    const shell = document.querySelector('#app-shell');
    return Boolean(shell && !shell.classList.contains('hidden'));
  }

  function workspaceReady() {
    const content = document.querySelector('#app-content');
    return workspaceVisible() && Boolean(content) && !content.querySelector('.loading-state');
  }

  function findNavButton(view) {
    return [...document.querySelectorAll('#app-nav button[data-view]')]
      .find(item => item.dataset.view === view) || null;
  }

  function restoreInitialView() {
    if (!restoringInitialView || restoreTimer) return;
    const deadline = Date.now() + 30000;

    const attempt = () => {
      restoreTimer = null;
      if (!restoringInitialView) return;
      const button = findNavButton(initialDesiredView);

      if (workspaceReady() && button) {
        restoringInitialView = false;
        if (!button.classList.contains('active')) button.click();
        else rememberView(initialDesiredView);
        return;
      }

      if (Date.now() < deadline) restoreTimer = setTimeout(attempt, 80);
      else {
        restoringInitialView = false;
        clearView();
      }
    };

    restoreTimer = setTimeout(attempt, 0);
  }

  function rememberActiveWorkspaceView() {
    if (restoringInitialView || !workspaceReady()) return;
    const active = document.querySelector('#app-nav button.active[data-view]');
    if (active) rememberView(active.dataset.view);
  }

  function ensureSignupCancel() {
    const signup = document.querySelector('#signup-view');
    if (!signup || signup.classList.contains('hidden') || signup.querySelector('.auth-inline-cancel')) return;
    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'button button-secondary button-full auth-inline-cancel';
    cancel.dataset.action = 'close-auth';
    cancel.textContent = 'Cancel';
    const form = signup.querySelector('form');
    if (form) form.insertAdjacentElement('afterend', cancel);
    else signup.appendChild(cancel);
  }

  function settleSessionVisualState() {
    if (workspaceVisible()) {
      safeSessionSet(SESSION_HINT_KEY, '1');
      document.documentElement.classList.remove('placeai-session-restoring');
    }
  }

  document.addEventListener('click', event => {
    const logout = event.target.closest?.('[data-action="logout"]');
    if (logout) {
      clearView();
      safeSessionRemove(SESSION_HINT_KEY);
      return;
    }

    const viewButton = event.target.closest?.('[data-view]');
    if (viewButton?.dataset.view) rememberView(viewButton.dataset.view);

    if (event.target?.id === 'auth-overlay') {
      document.querySelector('#auth-overlay [data-action="close-auth"]')?.click();
    } else if (event.target?.id === 'generic-modal') {
      document.querySelector('#generic-modal [data-action="close-generic-modal"]')?.click();
    }
  }, true);

  function init() {
    if (safeSessionGet(SESSION_HINT_KEY)) {
      document.documentElement.classList.add('placeai-session-restoring');
      setTimeout(() => {
        document.documentElement.classList.remove('placeai-session-restoring');
        if (!workspaceVisible()) safeSessionRemove(SESSION_HINT_KEY);
      }, 6000);
    }

    const nav = document.querySelector('#app-nav');
    const shell = document.querySelector('#app-shell');
    const content = document.querySelector('#app-content');
    const auth = document.querySelector('#auth-overlay');

    const observer = new MutationObserver(() => {
      settleSessionVisualState();
      ensureSignupCancel();
      if (restoringInitialView) restoreInitialView();
      else rememberActiveWorkspaceView();
    });

    if (nav) observer.observe(nav, {subtree: true, childList: true, attributes: true, attributeFilter: ['class']});
    if (shell) observer.observe(shell, {attributes: true, attributeFilter: ['class']});
    if (content) observer.observe(content, {subtree: true, childList: true});
    if (auth) observer.observe(auth, {subtree: true, childList: true, attributes: true, attributeFilter: ['class']});

    ensureSignupCancel();
    restoreInitialView();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
