(() => {
  'use strict';
  if (window.__PLACEAI_UI_STATE_SHIM_LOADED__) return;
  window.__PLACEAI_UI_STATE_SHIM_LOADED__ = true;

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

// Password recovery runs from this early-loaded shim, before app.js. Capture the
// one-time token into sessionStorage before removing it from the address bar so a
// refresh cannot destroy an otherwise valid recovery attempt.
(() => {
  'use strict';
  if (window.__PLACEAI_RECOVERY_SHIM_LOADED__) return;
  window.__PLACEAI_RECOVERY_SHIM_LOADED__ = true;

  const RESET_TOKEN_KEY = 'placeai.password.reset.v1';
  const TOKEN_MIN = 20;
  const TOKEN_MAX = 512;

  const sessionGet = () => {
    try { return sessionStorage.getItem(RESET_TOKEN_KEY) || ''; } catch { return ''; }
  };
  const sessionSet = value => {
    try { sessionStorage.setItem(RESET_TOKEN_KEY, value); } catch {}
  };
  const sessionClear = () => {
    try { sessionStorage.removeItem(RESET_TOKEN_KEY); } catch {}
  };

  let token = '';
  try {
    const url = new URL(location.href);
    const incoming = url.searchParams.get('reset_token');
    if (incoming !== null) {
      if (incoming.length >= TOKEN_MIN && incoming.length <= TOKEN_MAX) {
        token = incoming;
        sessionSet(incoming);
      } else {
        sessionClear();
      }
      url.searchParams.delete('reset_token');
      history.replaceState(history.state || {}, '', `${url.pathname}${url.search}${url.hash}`);
    }
  } catch {}

  if (!token) token = sessionGet();
  if (!token || token.length < TOKEN_MIN || token.length > TOKEN_MAX) return;

  window.__placeaiPasswordRecoveryActive = true;

  const passwordChecks = value => ({
    length: value.length >= 12,
    lower: /[a-z]/.test(value),
    upper: /[A-Z]/.test(value),
    number: /[0-9]/.test(value),
    symbol: /[^A-Za-z0-9]/.test(value)
  });

  const apiMessage = (payload, fallback) => {
    if (typeof payload?.detail === 'string') return payload.detail;
    if (Array.isArray(payload?.detail)) {
      const messages = payload.detail
        .map(item => String(item?.msg || '').replace(/^Value error,\s*/i, '').trim())
        .filter(Boolean);
      if (messages.length) return messages.join(' ');
    }
    return fallback;
  };

  function injectStyles() {
    if (document.querySelector('#placeai-password-recovery-style')) return;
    const style = document.createElement('style');
    style.id = 'placeai-password-recovery-style';
    style.textContent = `
      .password-recovery-screen{position:fixed;inset:0;z-index:100000;display:grid;place-items:center;padding:24px;background:rgba(12,18,38,.78);backdrop-filter:blur(12px)}
      .password-recovery-card{width:min(520px,100%);background:#fff;border-radius:24px;padding:32px;box-shadow:0 30px 90px rgba(7,15,40,.34);font-family:DM Sans,system-ui,sans-serif;color:#172033}
      .password-recovery-brand{display:flex;align-items:center;gap:10px;font-weight:800;font-size:20px;margin-bottom:24px}.password-recovery-dot{width:13px;height:13px;border-radius:4px;background:#5b5bd6;box-shadow:18px 0 0 #8b5cf6,36px 0 0 #c084fc;margin-right:36px}
      .password-recovery-kicker{display:block;color:#5b5bd6;font-size:12px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;margin-bottom:8px}.password-recovery-card h1{font-family:Manrope,system-ui,sans-serif;font-size:28px;line-height:1.15;margin:0 0 8px}.password-recovery-copy{color:#64748b;margin:0 0 22px;line-height:1.55}
      .password-recovery-form{display:grid;gap:16px}.password-recovery-form label{display:grid;gap:7px;font-weight:700;font-size:14px}.password-recovery-form input{width:100%;box-sizing:border-box;border:1px solid #d8deea;border-radius:12px;padding:12px 14px;font:inherit;outline:none}.password-recovery-form input:focus{border-color:#5b5bd6;box-shadow:0 0 0 3px rgba(91,91,214,.12)}
      .password-rules{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:2px 0 4px;font-size:12px;color:#7b8496}.password-rule::before{content:'○';margin-right:6px}.password-rule.ok{color:#16845b}.password-rule.ok::before{content:'✓'}
      .password-recovery-error{min-height:20px;color:#b42318;font-size:13px;font-weight:650;line-height:1.45}.password-recovery-actions{display:flex;gap:10px;align-items:center}.password-recovery-submit{flex:1;border:0;border-radius:12px;padding:13px 16px;background:#5b5bd6;color:#fff;font:inherit;font-weight:800;cursor:pointer}.password-recovery-submit:disabled{opacity:.55;cursor:not-allowed}.password-recovery-cancel{border:0;background:transparent;color:#64748b;font:inherit;font-weight:700;cursor:pointer;padding:12px}
      .password-recovery-success{text-align:center;padding:8px 0}.password-recovery-success-icon{display:grid;place-items:center;width:58px;height:58px;margin:0 auto 18px;border-radius:50%;background:#e9f8f1;color:#16845b;font-size:28px;font-weight:900}.password-recovery-continue{width:100%;margin-top:18px}
      @media(max-width:560px){.password-recovery-card{padding:24px 20px;border-radius:20px}.password-rules{grid-template-columns:1fr}.password-recovery-actions{flex-direction:column}.password-recovery-cancel{width:100%}}
    `;
    document.head.appendChild(style);
  }

  function mountRecovery() {
    if (document.querySelector('#placeai-password-recovery')) return;
    injectStyles();

    const overlay = document.createElement('div');
    overlay.id = 'placeai-password-recovery';
    overlay.className = 'password-recovery-screen';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-labelledby', 'password-recovery-title');
    overlay.innerHTML = `
      <section class="password-recovery-card">
        <div class="password-recovery-brand"><span class="password-recovery-dot" aria-hidden="true"></span><span>PlaceAI</span></div>
        <span class="password-recovery-kicker">Secure account recovery</span>
        <h1 id="password-recovery-title">Set a new password</h1>
        <p class="password-recovery-copy">Use a strong password. This one-time recovery link remains available in this tab until the reset succeeds or you cancel.</p>
        <form id="password-recovery-form" class="password-recovery-form" novalidate>
          <label>New password<input id="password-recovery-new" type="password" autocomplete="new-password" minlength="12" maxlength="128" required></label>
          <div class="password-rules" aria-live="polite">
            <span class="password-rule" data-rule="length">12+ characters</span>
            <span class="password-rule" data-rule="upper">Uppercase letter</span>
            <span class="password-rule" data-rule="lower">Lowercase letter</span>
            <span class="password-rule" data-rule="number">Number</span>
            <span class="password-rule" data-rule="symbol">Symbol</span>
            <span class="password-rule" data-rule="match">Passwords match</span>
          </div>
          <label>Confirm new password<input id="password-recovery-confirm" type="password" autocomplete="new-password" minlength="12" maxlength="128" required></label>
          <div id="password-recovery-error" class="password-recovery-error" role="alert"></div>
          <div class="password-recovery-actions">
            <button id="password-recovery-submit" class="password-recovery-submit" type="submit" disabled>Reset password</button>
            <button id="password-recovery-cancel" class="password-recovery-cancel" type="button">Cancel</button>
          </div>
        </form>
      </section>`;
    document.body.appendChild(overlay);
    document.body.classList.add('modal-open');

    const form = overlay.querySelector('#password-recovery-form');
    const password = overlay.querySelector('#password-recovery-new');
    const confirm = overlay.querySelector('#password-recovery-confirm');
    const submit = overlay.querySelector('#password-recovery-submit');
    const error = overlay.querySelector('#password-recovery-error');

    const validate = () => {
      const checks = passwordChecks(password.value);
      const matches = Boolean(password.value) && password.value === confirm.value;
      Object.entries(checks).forEach(([name, ok]) => overlay.querySelector(`[data-rule="${name}"]`)?.classList.toggle('ok', ok));
      overlay.querySelector('[data-rule="match"]')?.classList.toggle('ok', matches);
      submit.disabled = !(Object.values(checks).every(Boolean) && matches);
      if (!submit.disabled) error.textContent = '';
    };

    password.addEventListener('input', validate);
    confirm.addEventListener('input', validate);

    overlay.querySelector('#password-recovery-cancel').addEventListener('click', () => {
      sessionClear();
      window.__placeaiPasswordRecoveryActive = false;
      location.assign(location.pathname || '/');
    });

    form.addEventListener('submit', async event => {
      event.preventDefault();
      validate();
      if (submit.disabled) {
        error.textContent = 'Your password must satisfy every requirement and both entries must match.';
        return;
      }

      submit.disabled = true;
      const originalLabel = submit.textContent;
      submit.textContent = 'Resetting…';
      error.textContent = '';

      try {
        const response = await fetch('/auth/reset-password', {
          method: 'POST',
          credentials: 'include',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({token, new_password: password.value})
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          if (response.status === 400) sessionClear();
          throw new Error(apiMessage(payload, response.status === 400 ? 'This reset link is invalid or expired. Request a fresh reset link.' : 'Password reset failed. Please try again.'));
        }

        sessionClear();
        window.__placeaiPasswordRecoveryActive = false;
        overlay.querySelector('.password-recovery-card').innerHTML = `
          <div class="password-recovery-success">
            <div class="password-recovery-success-icon">✓</div>
            <span class="password-recovery-kicker">Password updated</span>
            <h1>Password reset successful</h1>
            <p class="password-recovery-copy">Your previous sessions have been revoked. Sign in again using your new password.</p>
            <button id="password-recovery-continue" class="password-recovery-submit password-recovery-continue" type="button">Continue to sign in</button>
          </div>`;
        overlay.querySelector('#password-recovery-continue').addEventListener('click', () => location.assign(location.pathname || '/'));
      } catch (err) {
        error.textContent = err instanceof Error ? err.message : 'Password reset failed. Please try again.';
        submit.textContent = originalLabel;
        submit.disabled = false;
      }
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mountRecovery, {once: true});
  else mountRecovery();
})();
