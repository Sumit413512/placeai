(() => {
  'use strict';

  const originalFetch = window.fetch.bind(window);
  const LAST_VIEW_KEY = 'placeai:last-view';
  const SESSION_MARKER_KEY = 'placeai:session-known';
  let runtimeToken = '';
  let refreshInFlight = null;
  let restoredView = false;

  const toUrl = input => {
    try {
      if (input instanceof Request) return new URL(input.url, location.href);
      return new URL(String(input), location.href);
    } catch {
      return null;
    }
  };

  const sameOriginPath = input => {
    const url = toUrl(input);
    return url && url.origin === location.origin ? url.pathname : '';
  };

  const cloneHeaders = (input, init) => {
    const headers = new Headers(input instanceof Request ? input.headers : undefined);
    new Headers(init?.headers || {}).forEach((value, key) => headers.set(key, value));
    return headers;
  };

  async function captureAccessToken(response) {
    if (!response?.ok) return;
    try {
      const contentType = response.headers.get('content-type') || '';
      if (!contentType.includes('application/json')) return;
      const payload = await response.clone().json();
      if (payload?.access_token) {
        runtimeToken = payload.access_token;
        sessionStorage.setItem(SESSION_MARKER_KEY, '1');
      }
    } catch {
      // Token capture is an optimization; the HttpOnly refresh cookie remains authoritative.
    }
  }

  async function refreshAccessToken() {
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
          sessionStorage.removeItem(SESSION_MARKER_KEY);
          return '';
        }
        const payload = await response.json();
        runtimeToken = payload?.access_token || '';
        if (runtimeToken) sessionStorage.setItem(SESSION_MARKER_KEY, '1');
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

  window.fetch = async function placeaiReliableFetch(input, init = {}) {
    const path = sameOriginPath(input);
    let nextInit = {...init};
    let headers = cloneHeaders(input, init);

    const isAuthBootstrap = path === '/auth/me';
    const isTokenEndpoint = ['/auth/login', '/auth/login-json', '/auth/login-role', '/auth/google', '/auth/refresh'].includes(path);
    const shouldAttachRuntimeToken =
      runtimeToken &&
      path.startsWith('/') &&
      !isTokenEndpoint &&
      path !== '/auth/logout' &&
      !headers.has('Authorization');

    if (shouldAttachRuntimeToken) {
      headers.set('Authorization', `Bearer ${runtimeToken}`);
      nextInit.headers = headers;
    }

    let response = await originalFetch(input, nextInit);
    if (isTokenEndpoint) captureAccessToken(response);

    if (response.status === 401 && isAuthBootstrap && !headers.has('Authorization')) {
      const token = await refreshAccessToken();
      if (token) {
        headers = cloneHeaders(input, init);
        headers.set('Authorization', `Bearer ${token}`);
        response = await originalFetch(input, {...init, headers, credentials: 'include'});
      }
    }

    if (path === '/auth/logout' && response.ok) {
      runtimeToken = '';
      sessionStorage.removeItem(SESSION_MARKER_KEY);
      sessionStorage.removeItem(LAST_VIEW_KEY);
    }

    return response;
  };

  function rememberView(target) {
    const button = target.closest?.('[data-view]');
    if (!button?.dataset.view) return;
    sessionStorage.setItem(LAST_VIEW_KEY, button.dataset.view);
  }

  function ensureAuthCancel() {
    const signup = document.querySelector('#signup-view');
    if (!signup || signup.classList.contains('hidden')) return;
    if (signup.querySelector('.auth-inline-cancel')) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'button button-secondary button-full auth-inline-cancel';
    button.dataset.action = 'close-auth';
    button.textContent = 'Cancel';
    const form = signup.querySelector('form');
    if (form) form.insertAdjacentElement('afterend', button);
    else signup.appendChild(button);
  }

  function restoreWorkspaceView() {
    if (restoredView) return;
    const shell = document.querySelector('#app-shell');
    const nav = document.querySelector('#app-nav');
    if (!shell || shell.classList.contains('hidden') || !nav?.children.length) return;

    restoredView = true;
    const saved = sessionStorage.getItem(LAST_VIEW_KEY);
    if (!saved || saved === 'dashboard') return;
    const selector = `button[data-view="${CSS.escape(saved)}"]`;
    const button = nav.querySelector(selector);
    if (button) button.click();
    else sessionStorage.removeItem(LAST_VIEW_KEY);
  }

  document.addEventListener('click', event => {
    rememberView(event.target);
    if (event.target.closest?.('[data-action="logout"]')) {
      sessionStorage.removeItem(LAST_VIEW_KEY);
    }
  }, true);

  const observer = new MutationObserver(() => {
    ensureAuthCancel();
    restoreWorkspaceView();
  });

  function init() {
    observer.observe(document.documentElement, {subtree: true, childList: true, attributes: true, attributeFilter: ['class']});
    ensureAuthCancel();
    restoreWorkspaceView();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
