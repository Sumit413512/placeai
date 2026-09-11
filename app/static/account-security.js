(() => {
  'use strict';

  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const provisioningFormIds = new Set(['institution-student-form', 'institution-recruiter-form', 'admin-form']);

  const apiErrors = window.PlaceAIApiErrors;

  function validatePassword(password) {
    if (password.length < 12) return 'Password must be at least 12 characters long.';
    if (!/[a-z]/.test(password)) return 'Password must contain a lowercase letter.';
    if (!/[A-Z]/.test(password)) return 'Password must contain an uppercase letter.';
    if (!/[0-9]/.test(password)) return 'Password must contain a number.';
    if (!/[^A-Za-z0-9]/.test(password)) return 'Password must contain a symbol.';
    return '';
  }

  function decorateProvisioningInputs(root = document) {
    const inputs = root.querySelectorAll?.('input[name="temporary_password"]') || [];
    inputs.forEach(input => {
      const form = input.closest('form');
      if (!form || !provisioningFormIds.has(form.id)) return;
      input.setAttribute('autocomplete', 'new-password');
      input.setAttribute('autocapitalize', 'none');
      input.setAttribute('spellcheck', 'false');
      input.dataset.placeaiSensitive = 'write-only';
      if (form.querySelector('.provisioning-credential-note')) return;
      const note = document.createElement('div');
      note.className = 'provisioning-credential-note password-rotation-help';
      note.setAttribute('role', 'note');
      note.textContent = 'One-time credential. Share it through your approved secure channel before submitting. PlaceAI will not display this value again, and the account must replace it at first sign-in.';
      const label = input.closest('label');
      (label?.parentNode || form).insertBefore(note, label?.nextSibling || null);
    });
  }

  function decorateCsvHandoff(root = document) {
    const inputs = root.querySelectorAll?.('#student-csv-file') || [];
    inputs.forEach(input => {
      const container = input.closest('.data-toolbar, .row-actions') || input.parentElement;
      if (!container || container.querySelector('.csv-credential-note')) return;
      const note = document.createElement('div');
      note.className = 'csv-credential-note password-rotation-help';
      note.setAttribute('role', 'note');
      note.textContent = 'CSV temporary passwords are one-time provisioning credentials. Transfer them through an approved secure channel, remove completed local copies, and do not expect PlaceAI to display them after import.';
      container.appendChild(note);
    });
  }

  function installProvisioningProtections() {
    decorateProvisioningInputs();
    decorateCsvHandoff();
    const observer = new MutationObserver(records => {
      for (const record of records) {
        record.addedNodes.forEach(node => {
          if (!(node instanceof Element)) return;
          decorateProvisioningInputs(node);
          decorateCsvHandoff(node);
        });
      }
    });
    observer.observe(document.body, {childList: true, subtree: true});

    document.addEventListener('submit', event => {
      const form = event.target instanceof HTMLFormElement ? event.target : null;
      if (!form || !provisioningFormIds.has(form.id)) return;
      const input = form.querySelector('input[name="temporary_password"]');
      if (!input) return;
      queueMicrotask(() => {
        input.value = '';
        input.dataset.clearedAfterSubmit = 'true';
      });
    });

    document.addEventListener('change', event => {
      const input = event.target instanceof HTMLInputElement ? event.target : null;
      if (!input || input.id !== 'student-csv-file' || !input.files?.length) return;
      queueMicrotask(() => { input.value = ''; });
    });
  }

  function showRotation(user) {
    if (document.querySelector('#password-rotation-overlay')) return;
    document.documentElement.classList.add('placeai-password-rotation-open');
    const overlay = document.createElement('div');
    overlay.id = 'password-rotation-overlay';
    overlay.className = 'password-rotation-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-labelledby', 'password-rotation-title');
    overlay.innerHTML = `<section class="password-rotation-card"><span class="password-rotation-kicker">Account security</span><h2 id="password-rotation-title">Create your permanent password</h2><p>${esc(user?.username || user?.email || 'This account')} was provisioned with a temporary password. Change it before entering the PlaceAI workspace.</p><form id="password-rotation-form" class="password-rotation-form"><label>Current temporary password<input type="password" name="current_password" autocomplete="current-password" maxlength="128" required autofocus></label><label>New password<input type="password" name="new_password" autocomplete="new-password" minlength="12" maxlength="128" required></label><div class="password-rotation-help">Use 12+ characters with uppercase, lowercase, a number and a symbol.</div><label>Confirm new password<input type="password" name="confirm_password" autocomplete="new-password" minlength="12" maxlength="128" required></label><div id="password-rotation-error" class="password-rotation-error" role="alert"></div><button class="password-rotation-submit" type="submit">Change password and continue</button></form></section>`;
    document.body.appendChild(overlay);

    const form = overlay.querySelector('#password-rotation-form');
    const error = overlay.querySelector('#password-rotation-error');
    const button = overlay.querySelector('button[type="submit"]');
    form.addEventListener('submit', async event => {
      event.preventDefault();
      error.classList.remove('is-visible');
      error.textContent = '';
      const body = Object.fromEntries(new FormData(form).entries());
      const passwordError = validatePassword(String(body.new_password || ''));
      if (passwordError) { error.textContent = passwordError; error.classList.add('is-visible'); return; }
      if (body.new_password !== body.confirm_password) { error.textContent = 'New password and confirmation do not match.'; error.classList.add('is-visible'); return; }
      if (body.current_password === body.new_password) { error.textContent = 'New password must be different from the temporary password.'; error.classList.add('is-visible'); return; }
      button.disabled = true;
      button.textContent = 'Updating password…';
      try {
        const response = await fetch('/auth/change-password', {method: 'POST', credentials: 'include', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({current_password: body.current_password, new_password: body.new_password})});
        const data = await response.json().catch(() => ({}));
        body.current_password = '';
        body.new_password = '';
        body.confirm_password = '';
        form.reset();
        if (!response.ok) throw apiErrors.createError(data, response.status);
        location.reload();
      } catch (err) {
        body.current_password = '';
        body.new_password = '';
        body.confirm_password = '';
        form.reset();
        apiErrors.applyToForm(form, err, error);
        button.disabled = false;
        button.textContent = 'Change password and continue';
      }
    });
  }

  async function init() {
    installProvisioningProtections();
    try {
      const response = await fetch('/auth/me', {credentials: 'include'});
      if (!response.ok) return;
      const user = await response.json();
      if (user?.must_change_password) showRotation(user);
    } catch {
      // Unauthenticated public visitors should not see the rotation surface.
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
