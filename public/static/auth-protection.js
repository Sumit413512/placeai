(() => {
  'use strict';
  const nativeFetch = window.fetch.bind(window);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const loginPaths = new Set(['/auth/login', '/auth/login-json', '/auth/login-role', '/auth/google']);
  let pendingMfa = null;

  function dialog(title, content, required = false) {
    const overlay = document.createElement('div');
    overlay.className = 'password-rotation-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-label', title);
    overlay.innerHTML = `<section class="password-rotation-card"><h2>${esc(title)}</h2>${content}</section>`;
    const previous = document.activeElement;
    const close = () => { overlay.remove(); previous?.focus?.(); };
    const cancel = document.createElement('button');
    cancel.type = 'button'; cancel.className = 'row-button'; cancel.textContent = required ? 'Sign out' : 'Close';
    cancel.onclick = async () => { if (required) { await fetch('/auth/logout', {method:'POST'}); location.assign('/'); } else close(); };
    overlay.firstElementChild.append(cancel);
    overlay.addEventListener('keydown', event => {
      if (event.key === 'Escape' && !required) { event.stopImmediatePropagation(); cancel.click(); }
      if (event.key !== 'Tab') return;
      event.stopPropagation();
      const items = [...overlay.querySelectorAll('button:not([disabled]), input:not([disabled]), a[href], textarea')];
      const first = items[0], last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    });
    document.body.append(overlay);
    overlay.querySelector('input,button')?.focus();
    return {overlay, close, cancel};
  }

  function completeMfa(challenge) {
    if (pendingMfa) return Promise.reject(new Error('Another sign-in is awaiting verification.'));
    return new Promise((resolve, reject) => {
      pendingMfa = challenge;
      const {overlay, close, cancel} = dialog('Verify your sign-in', '<p>Enter the six-digit code from your authenticator, or one unused recovery code.</p><form class="password-rotation-form"><label>Authenticator or recovery code<input name="code" autocomplete="one-time-code" maxlength="64" required></label><p role="alert"></p><button class="button button-primary" type="submit">Verify and sign in</button></form>');
      cancel.onclick = () => { pendingMfa = null; close(); reject(new Error('Sign-in cancelled.')); };
      const form = overlay.querySelector('form');
      form.onsubmit = async event => {
        event.preventDefault(); event.stopPropagation();
        const button = form.querySelector('button'); button.disabled = true;
        try {
          const response = await nativeFetch('/auth/mfa/verify', {method:'POST', credentials:'include', headers:{'Content-Type':'application/json'}, body:JSON.stringify({challenge, code:form.elements.code.value.trim()})});
          if (!response.ok) { const data = await response.json(); throw new Error(typeof data.detail === 'string' ? data.detail : 'Verification failed.'); }
          pendingMfa = null; form.reset(); close(); resolve(response);
        } catch (error) { form.querySelector('[role="alert"]').textContent = error.message; button.disabled = false; }
      };
    });
  }

  window.fetch = async (input, init) => {
    const response = await nativeFetch(input, init);
    let url;
    try { url = new URL(input instanceof Request ? input.url : String(input), location.href); } catch { return response; }
    if (url.origin !== location.origin) return response;
    if (response.ok && loginPaths.has(url.pathname)) {
      const data = await response.clone().json().catch(() => ({}));
      if (data.mfa_required && data.mfa_challenge) return completeMfa(data.mfa_challenge);
      if (data.access_token) return offerAuthenticator(response, data.access_token);
    }
    return response;
  };

  async function request(path, body, token = null) {
    const headers = {'Content-Type':'application/json'};
    if (token) headers.Authorization = `Bearer ${token}`;
    const response = await nativeFetch(path, {credentials:'include', headers, ...(body === undefined ? {} : {method:'POST', body:JSON.stringify(body)})});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : data.detail?.message || 'Request could not be completed. Please try again.');
    return data;
  }

  window.PlaceAIVerification = Object.freeze({
    showPending(email, message) {
      const {overlay, cancel, close} = dialog('Check your email', `<p>${esc(message)}</p><p>Confirm your email before your first sign-in. You can also sign in with a verified Google account.</p><button class="row-button" data-resend-link>Resend verification link</button><p role="status" aria-live="polite"></p>`);
      cancel.textContent = 'Back to sign in';
      cancel.onclick = () => { close(); document.querySelector('[data-access-switch="login"]')?.click(); };
      overlay.querySelector('[data-resend-link]').onclick = async event => {
        event.target.disabled = true;
        try { overlay.querySelector('[role="status"]').textContent = (await request('/auth/email-verification/resend', {email})).message; }
        catch (error) { overlay.querySelector('[role="status"]').textContent = error.message; }
        finally { event.target.disabled = false; }
      };
    }
  });

  async function offerAuthenticator(response, token) {
    let status;
    try { status = await request('/auth/security-status', undefined, token); }
    catch { return response; } // Required password rotation and backend access gates remain authoritative.
    if (status.mfa_enabled) return response;
    return new Promise(resolve => {
      let active = null;
      let currentResponse = response;
      const finish = () => { active?.close(); resolve(currentResponse); };
      const show = (title, content, label = 'Skip for now') => {
        active?.close();
        active = dialog(title, content);
        active.cancel.textContent = label;
        active.cancel.onclick = finish;
        return active.overlay;
      };
      const intro = show('Add an extra layer of protection', '<p>Set up an authenticator to protect your PlaceAI account with a one-time code at sign-in. You can also continue without setting it up.</p><button type="button" class="button button-primary" data-setup-authenticator>Set up authenticator</button>');
      intro.querySelector('[data-setup-authenticator]').onclick = () => {
        if (!status.email_verified) {
          const panel = show('Verify your email first', '<p>Confirm your email before setting up an authenticator. Use the verification link, then sign in again to complete setup.</p><button type="button" class="button button-primary" data-verify-email>Send verification link</button><p role="status" aria-live="polite"></p>');
          panel.querySelector('[data-verify-email]').onclick = async event => {
            event.target.disabled = true;
            try { panel.querySelector('[role="status"]').textContent = (await request('/auth/email-verification/request', {}, token)).message; }
            catch (error) { panel.querySelector('[role="status"]').textContent = error.message; }
            finally { event.target.disabled = false; }
          };
          return;
        }
        const panel = show('Set up your authenticator', '<p>Confirm your password to connect an authenticator app.</p><form class="password-rotation-form"><label>Current password<input name="password" type="password" autocomplete="current-password" maxlength="128" required></label><p role="alert"></p><button type="submit" class="button button-primary">Continue setup</button></form>');
        const form = panel.querySelector('form');
        form.onsubmit = async event => {
          event.preventDefault(); event.stopPropagation();
          const button = form.querySelector('button'); button.disabled = true;
          try {
            const setup = await request('/auth/mfa/enroll', {password:form.elements.password.value}, token);
            form.reset();
            if (!panel.isConnected) return;
            const next = show('Connect your authenticator', `<p>Add a time-based account named PlaceAI in your authenticator app using this setup key. Keep it private.</p><p><code>${esc(setup.secret)}</code></p><p>Setup expires in ten minutes. Enter a code to enable protection.</p><form class="password-rotation-form"><label>Six-digit code<input name="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" required></label><p role="alert"></p><button type="submit" class="button button-primary">Enable authenticator</button></form>`);
            const nextForm = next.querySelector('form');
            nextForm.onsubmit = async confirmEvent => {
              confirmEvent.preventDefault(); confirmEvent.stopPropagation();
              const submit = nextForm.querySelector('button'); submit.disabled = true;
              active.cancel.disabled = true; // Do not release an old session while factor enrolment rotates it.
              try {
                const result = await request('/auth/mfa/confirm', {code:nextForm.elements.code.value}, token);
                nextForm.reset();
                const {recovery_codes, ...tokens} = result;
                currentResponse = new Response(JSON.stringify(tokens), {status:200, headers:{'Content-Type':'application/json'}});
                const recovery = show('Save your recovery codes', '<p>Store these codes in your password manager or another safe place. Each works once. They will not be shown again.</p><textarea readonly rows="8" aria-label="One-time recovery codes"></textarea>', 'I saved my codes - continue');
                recovery.querySelector('textarea').value = recovery_codes.join('\n');
              } catch (error) { nextForm.querySelector('[role="alert"]').textContent = error.message; submit.disabled = false; active.cancel.disabled = false; }
            };
          } catch (error) { form.reset(); form.querySelector('[role="alert"]').textContent = error.message; button.disabled = false; }
        };
      };
    });
  }

  const url = new URL(location.href);
  const verificationToken = url.searchParams.get('verify_email_token');
  if (verificationToken !== null) {
    url.searchParams.delete('verify_email_token');
    history.replaceState({}, '', url.pathname + url.search + url.hash);
  }
  async function initialize() {
    if (verificationToken) {
      const {overlay, cancel} = dialog('Email verification', '<p role="status" aria-live="polite">Verifying your email...</p>');
      try { overlay.querySelector('[role="status"]').textContent = (await request('/auth/email-verification/confirm', {token:verificationToken})).message; cancel.onclick = () => location.reload(); }
      catch (error) { overlay.querySelector('[role="status"]').textContent = error.message; }
    }

  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, {once:true});
  else initialize();
})();
