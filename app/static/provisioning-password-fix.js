(() => {
  'use strict';

  const AUTO_TEMP_PASSWORD_FIX_V1 = true;
  const FORM_IDS = new Set(['admin-form', 'institution-student-form', 'institution-recruiter-form']);
  const LOWER = 'abcdefghijkmnopqrstuvwxyz';
  const UPPER = 'ABCDEFGHJKLMNPQRSTUVWXYZ';
  const DIGITS = '23456789';
  const SYMBOLS = '!@#$%^&*_-+=';
  const ALL = LOWER + UPPER + DIGITS + SYMBOLS;

  function randomIndex(max) {
    if (!Number.isInteger(max) || max <= 0) return 0;
    const limit = Math.floor(256 / max) * max;
    const bytes = new Uint8Array(1);
    do {
      crypto.getRandomValues(bytes);
    } while (bytes[0] >= limit);
    return bytes[0] % max;
  }

  function pick(chars) {
    return chars[randomIndex(chars.length)];
  }

  function secureTemporaryPassword(length = 18) {
    const chars = [pick(LOWER), pick(UPPER), pick(DIGITS), pick(SYMBOLS)];
    while (chars.length < length) chars.push(pick(ALL));
    for (let i = chars.length - 1; i > 0; i -= 1) {
      const j = randomIndex(i + 1);
      [chars[i], chars[j]] = [chars[j], chars[i]];
    }
    return chars.join('');
  }

  function setPassword(input, value = secureTemporaryPassword()) {
    input.value = value;
    input.setCustomValidity('');
    input.dispatchEvent(new Event('input', {bubbles: true}));
  }

  async function copyPassword(input, button) {
    const value = String(input.value || '');
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      const wasReadOnly = input.readOnly;
      input.readOnly = false;
      input.select();
      document.execCommand('copy');
      input.setSelectionRange(0, 0);
      input.readOnly = wasReadOnly;
    }
    const previous = button.textContent;
    button.textContent = 'Copied';
    setTimeout(() => { button.textContent = previous; }, 1200);
  }

  function decorateInput(input) {
    if (!(input instanceof HTMLInputElement)) return;
    const form = input.closest('form');
    if (!form || !FORM_IDS.has(form.id) || input.dataset.placeaiAutoTempPassword === '1') return;

    input.dataset.placeaiAutoTempPassword = '1';
    input.readOnly = true;
    input.minLength = 12;
    input.maxLength = 128;
    input.autocomplete = 'off';
    input.setAttribute('aria-readonly', 'true');
    setPassword(input);

    const label = input.closest('label');
    if (!label) return;

    const controls = document.createElement('div');
    controls.className = 'row-actions provisioning-password-actions';
    controls.innerHTML = '<button type="button" class="button button-secondary" data-temp-password-copy>Copy temporary password</button><button type="button" class="button button-secondary" data-temp-password-regenerate>Regenerate</button>';
    label.appendChild(controls);

    const note = document.createElement('small');
    note.className = 'placeai-password-policy provisioning-password-generated-note';
    note.textContent = 'A secure one-time password has been generated automatically. Copy it before creating the account; the user must replace it at first sign-in.';
    label.appendChild(note);

    controls.querySelector('[data-temp-password-copy]')?.addEventListener('click', event => {
      copyPassword(input, event.currentTarget);
    });
    controls.querySelector('[data-temp-password-regenerate]')?.addEventListener('click', () => {
      setPassword(input);
    });
  }

  function enhance(root = document) {
    if (root instanceof HTMLInputElement && root.name === 'temporary_password') decorateInput(root);
    root.querySelectorAll?.('input[name="temporary_password"]')?.forEach(decorateInput);
  }

  function strongPasswordMessage(password) {
    if (password.length < 12) return 'Password must be at least 12 characters long.';
    if (password.length > 128) return 'Password must be 128 characters or fewer.';
    if (!/[a-z]/.test(password)) return 'Password must contain a lowercase letter.';
    if (!/[A-Z]/.test(password)) return 'Password must contain an uppercase letter.';
    if (!/[0-9]/.test(password)) return 'Password must contain a number.';
    if (!/[^A-Za-z0-9]/.test(password)) return 'Password must contain a symbol.';
    return '';
  }

  function showRotationError(form, errorElement, error) {
    const apiErrors = window.PlaceAIApiErrors;
    if (apiErrors?.applyToForm) {
      apiErrors.applyToForm(form, error, errorElement);
      return;
    }
    errorElement.textContent = error?.message || 'Password could not be updated. Check the details and try again.';
    errorElement.classList.add('is-visible');
  }

  async function submitPasswordRotation(form) {
    if (form.dataset.placeaiRotationSubmitting === 'true') return;
    const errorElement = form.querySelector('#password-rotation-error');
    const button = form.querySelector('button[type="submit"]');
    if (!(errorElement instanceof HTMLElement) || !(button instanceof HTMLButtonElement)) return;

    errorElement.classList.remove('is-visible');
    errorElement.textContent = '';
    const body = Object.fromEntries(new FormData(form).entries());
    const currentPassword = String(body.current_password || '');
    const newPassword = String(body.new_password || '');
    const confirmPassword = String(body.confirm_password || '');
    const policyError = strongPasswordMessage(newPassword);
    if (policyError) {
      errorElement.textContent = policyError;
      errorElement.classList.add('is-visible');
      return;
    }
    if (newPassword !== confirmPassword) {
      errorElement.textContent = 'New password and confirmation do not match.';
      errorElement.classList.add('is-visible');
      return;
    }
    if (currentPassword === newPassword) {
      errorElement.textContent = 'New password must be different from the current password.';
      errorElement.classList.add('is-visible');
      return;
    }

    form.dataset.placeaiRotationSubmitting = 'true';
    button.disabled = true;
    const forced = form.closest('#password-rotation-overlay')?.dataset.forced === 'true';
    button.textContent = 'Updating password…';
    try {
      const response = await fetch('/auth/change-password', {
        method: 'POST',
        credentials: 'include',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const apiErrors = window.PlaceAIApiErrors;
        throw apiErrors?.createError ? apiErrors.createError(data, response.status) : new Error(data.detail || 'Password update failed.');
      }
      form.reset();
      location.reload();
    } catch (error) {
      // Deliberately preserve the entered values on an API failure. The legacy handler
      // reset all fields before showing the server error, which made first-login retry
      // loops unnecessarily destructive.
      showRotationError(form, errorElement, error);
      delete form.dataset.placeaiRotationSubmitting;
      button.disabled = false;
      button.textContent = forced ? 'Change password and continue' : 'Change password';
    }
  }

  function install() {
    enhance(document);

    const observer = new MutationObserver(records => {
      for (const record of records) {
        record.addedNodes.forEach(node => {
          if (node instanceof Element) enhance(node);
        });
      }
    });
    observer.observe(document.body, {childList: true, subtree: true});

    // account-security.js historically cleared temporary_password on every submit,
    // including failed requests. Capture and restore the generated credential after
    // all capture listeners run so retries cannot fall back to an empty/invalid value.
    document.addEventListener('submit', event => {
      const form = event.target instanceof HTMLFormElement ? event.target : null;
      if (!form || !FORM_IDS.has(form.id)) return;
      const input = form.querySelector('input[name="temporary_password"]');
      if (!(input instanceof HTMLInputElement)) return;
      const credential = input.value || secureTemporaryPassword();
      queueMicrotask(() => {
        if (document.contains(input) && input.value !== credential) setPassword(input, credential);
      });
    }, true);

    // Intercept the dynamically-created password-rotation form before the legacy
    // target-level submit listener. This keeps credentials intact on validation/API
    // failure while retaining the same backend contract and successful reload path.
    document.addEventListener('submit', event => {
      const form = event.target instanceof HTMLFormElement ? event.target : null;
      if (!form || form.id !== 'password-rotation-form') return;
      event.preventDefault();
      event.stopImmediatePropagation();
      submitPasswordRotation(form);
    }, true);
  }

  if (AUTO_TEMP_PASSWORD_FIX_V1) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, {once: true});
    else install();
  }
})();
