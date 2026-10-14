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
    }
    return response;
  };

  async function request(path, body) {
    const response = await fetch(path, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
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

  let securityOpen = false;
  async function showSecurity(required = false) {
    if (securityOpen) return;
    const status = await request('/auth/security-status');
    securityOpen = true;
    const {overlay, close, cancel} = dialog('Account protection', `<p>${status.email_verified ? 'Your email is verified.' : 'Verify your email to confirm ownership of this account.'}</p>${!status.email_verified ? '<button class="row-button" data-verify-email>Send verification link</button>' : ''}<p>${status.mfa_enabled ? 'Authenticator protection is enabled.' : status.mfa_recommended ? 'Authenticator protection is recommended for your administrator account.' : 'Add an authenticator for an extra layer of protection.'}</p><form class="password-rotation-form"><label>Current password<input name="password" type="password" autocomplete="current-password" maxlength="128" required></label>${status.mfa_enabled ? '<label>Authenticator or recovery code<input name="code" autocomplete="one-time-code" maxlength="64" required></label>' : ''}<button type="submit" class="button button-primary">${status.mfa_enabled ? 'Disable authenticator' : 'Set up authenticator'}</button></form><p role="status" aria-live="polite"></p>`, required);
    const originalCancel = cancel.onclick;
    cancel.onclick = async () => { securityOpen = false; await originalCancel(); };
    const message = overlay.querySelector('[role="status"]');
    overlay.querySelector('[data-verify-email]')?.addEventListener('click', async event => {
      event.target.disabled = true;
      try { message.textContent = (await request('/auth/email-verification/request', {})).message; }
      catch (error) { message.textContent = error.message; }
      finally { event.target.disabled = false; }
    });
    const form = overlay.querySelector('form');
    form.onsubmit = async event => {
      event.preventDefault(); event.stopPropagation();
      const button = form.querySelector('button'); button.disabled = true;
      try {
        const body = Object.fromEntries(new FormData(form));
        if (status.mfa_enabled) { await request('/auth/mfa/disable', body); form.reset(); location.reload(); return; }
        const setup = await request('/auth/mfa/enroll', body);
        form.reset(); close(); securityOpen = false;
        const next = dialog('Connect your authenticator', `<p>Add a time-based account named PlaceAI in your authenticator app using this setup key. Keep it private.</p><p><code>${esc(setup.secret)}</code></p><p>Setup expires in ten minutes. Enter a code to enable protection.</p><form class="password-rotation-form"><label>Six-digit code<input name="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" required></label><p role="alert"></p><button type="submit" class="button button-primary">Enable authenticator</button></form>`);
        const nextForm = next.overlay.querySelector('form');
        nextForm.onsubmit = async confirmEvent => {
          confirmEvent.preventDefault(); confirmEvent.stopPropagation();
          const submit = nextForm.querySelector('button'); submit.disabled = true;
          try {
            const result = await request('/auth/mfa/confirm', {code:nextForm.elements.code.value});
            nextForm.reset(); next.close();
            const recovery = dialog('Save your recovery codes', '<p>Store these codes in your password manager or another safe place. Each works once. They will not be shown again.</p><textarea readonly rows="8" aria-label="One-time recovery codes"></textarea>');
            recovery.overlay.querySelector('textarea').value = result.recovery_codes.join('\n');
            recovery.cancel.textContent = 'I saved my codes - continue'; recovery.cancel.onclick = () => location.reload();
          } catch (error) { nextForm.querySelector('[role="alert"]').textContent = error.message; submit.disabled = false; }
        };
      } catch (error) { message.textContent = error.message; button.disabled = false; }
    };
  }

  const url = new URL(location.href);
  const verificationToken = url.searchParams.get('verify_email_token');
  if (verificationToken !== null) {
    url.searchParams.delete('verify_email_token');
    history.replaceState({}, '', url.pathname + url.search + url.hash);
  }
  async function initialize() {
    if (verificationToken) {
      const {overlay, cancel} = dialog('Email verification', '<p role="status" aria-live="polite">Verifying your emailâ€¦</p>');
      try { overlay.querySelector('[role="status"]').textContent = (await request('/auth/email-verification/confirm', {token:verificationToken})).message; cancel.onclick = () => location.reload(); }
      catch (error) { overlay.querySelector('[role="status"]').textContent = error.message; }
    }
    const install = () => {
      const sidebar = document.querySelector('.sidebar-bottom');
      if (!sidebar || sidebar.querySelector('[data-auth-protection]')) return;
      const button = document.createElement('button'); button.type = 'button'; button.className = 'auth-protection-button row-button';
      button.dataset.authProtection = 'open'; button.textContent = 'Email and authenticator';
      button.onclick = () => showSecurity().catch(error => { button.textContent = error.message; });
      sidebar.prepend(button);
    };
    install();
    new MutationObserver(install).observe(document.body, {childList:true, subtree:true});
    try { const status = await request('/auth/security-status'); if (status.verification_required && !status.email_verified) await showSecurity(true); } catch {}
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, {once:true});
  else initialize();
})();
