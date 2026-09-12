(() => {
  'use strict';

  const labelOverrides = {
    organization_slug: 'Institution code',
    organization_name: 'Organization',
    requested_role: 'Role',
    work_email: 'Work email',
    temporary_password: 'Temporary password',
    current_password: 'Current password',
    new_password: 'New password',
    confirm_password: 'Confirm password',
    graduation_year: 'Graduation year',
    target_organization_slug: 'Target institution code',
    scheduled_at: 'Scheduled date and time',
    registration_deadline: 'Registration deadline',
    event_date: 'Event date',
  };

  const PASSWORD_POLICY_HELP = 'Use 12–128 characters with uppercase, lowercase, a number and a symbol.';
  const PASSWORD_PATTERN = '(?=.*[a-z])(?=.*[A-Z])(?=.*[0-9])(?=.*[^A-Za-z0-9]).{12,128}';

  const cleanMessage = value => String(value || '')
    .replace(/^Value error,\s*/i, '')
    .replace(/^Assertion failed,\s*/i, '')
    .trim();

  function fieldLabel(field) {
    const key = String(field || '').trim();
    if (!key) return '';
    if (labelOverrides[key]) return labelOverrides[key];
    const text = key.replace(/[_-]+/g, ' ').trim();
    return text ? text.charAt(0).toUpperCase() + text.slice(1) : '';
  }

  function fallbackMessage(status) {
    if (status === 400) return 'Please review the submitted information and try again.';
    if (status === 401) return 'Your session is no longer valid. Sign in and try again.';
    if (status === 403) return 'You do not have permission to perform this action.';
    if (status === 404) return 'The requested record could not be found.';
    if (status === 409) return 'This change conflicts with an existing record. Refresh and try again.';
    if (status === 413) return 'The selected file is larger than the allowed upload limit.';
    if (status === 422) return 'Please correct the highlighted fields and try again.';
    if (status === 429) return 'Too many requests were submitted. Wait briefly and try again.';
    if (status >= 500) return 'PlaceAI could not complete this request right now. Please try again.';
    return 'PlaceAI could not complete this request. Please review the form and try again.';
  }

  function strongPasswordMessage(value) {
    const password = String(value || '');
    if (!password) return '';
    if (password.length < 12) return 'Password must be at least 12 characters long.';
    if (password.length > 128) return 'Password must be 128 characters or fewer.';
    if (!/[a-z]/.test(password)) return 'Password must contain a lowercase letter.';
    if (!/[A-Z]/.test(password)) return 'Password must contain an uppercase letter.';
    if (!/[0-9]/.test(password)) return 'Password must contain a number.';
    if (!/[^A-Za-z0-9]/.test(password)) return 'Password must contain a symbol.';
    return '';
  }

  function isStrongPasswordField(input) {
    if (!(input instanceof HTMLInputElement) || input.type !== 'password') return false;
    const name = input.name;
    if (name === 'temporary_password' || name === 'new_password') return true;
    if (name !== 'password') return false;
    const formId = input.closest('form')?.id || '';
    return formId === 'role-student-signup-form' || formId === 'signup-form';
  }

  function syncPasswordValidity(input) {
    if (!isStrongPasswordField(input)) return;
    input.setCustomValidity(strongPasswordMessage(input.value));
  }

  function decoratePasswordField(input) {
    if (!isStrongPasswordField(input) || input.dataset.placeaiPasswordPolicy === 'true') return;
    input.dataset.placeaiPasswordPolicy = 'true';
    input.minLength = 12;
    input.maxLength = 128;
    input.pattern = PASSWORD_PATTERN;
    input.title = PASSWORD_POLICY_HELP;
    if (input.name !== 'password') input.autocomplete = 'new-password';

    const existingHelpId = input.getAttribute('aria-describedby');
    if (!existingHelpId) {
      const help = document.createElement('small');
      const id = `placeai-password-policy-${Math.random().toString(36).slice(2, 10)}`;
      help.id = id;
      help.className = 'placeai-password-policy';
      help.textContent = PASSWORD_POLICY_HELP;
      input.setAttribute('aria-describedby', id);
      const label = input.closest('label');
      if (label) label.appendChild(help);
      else input.insertAdjacentElement('afterend', help);
    }

    input.addEventListener('input', () => syncPasswordValidity(input));
    input.addEventListener('change', () => syncPasswordValidity(input));
    input.addEventListener('invalid', () => syncPasswordValidity(input));
    syncPasswordValidity(input);
  }

  function enhancePasswordPolicies(root = document) {
    const inputs = [];
    if (root instanceof HTMLInputElement) inputs.push(root);
    root.querySelectorAll?.('input[type="password"]')?.forEach(input => inputs.push(input));
    inputs.forEach(decoratePasswordField);
  }

  function installPasswordPolicyContract() {
    enhancePasswordPolicies();
    const observer = new MutationObserver(records => {
      for (const record of records) {
        record.addedNodes.forEach(node => {
          if (node instanceof Element) enhancePasswordPolicies(node);
        });
      }
    });
    if (document.body) observer.observe(document.body, {childList: true, subtree: true});
  }

  function normalize(payload = {}, status = 0) {
    const detail = payload && typeof payload === 'object' ? payload.detail : null;
    const fieldErrors = {};
    const summaries = [];

    if (typeof detail === 'string' && cleanMessage(detail)) {
      return {message: cleanMessage(detail), fieldErrors};
    }

    if (Array.isArray(detail)) {
      for (const item of detail) {
        if (typeof item === 'string') {
          const message = cleanMessage(item);
          if (message) summaries.push(message);
          continue;
        }
        if (!item || typeof item !== 'object') continue;
        const message = cleanMessage(item.msg);
        if (!message) continue;
        const location = Array.isArray(item.loc)
          ? item.loc.filter(part => !['body', 'query', 'path', 'header'].includes(String(part)))
          : [];
        const last = [...location].reverse().find(part => typeof part === 'string' && part.trim());
        const field = last ? String(last) : '';
        if (field) {
          fieldErrors[field] ||= [];
          if (!fieldErrors[field].includes(message)) fieldErrors[field].push(message);
          summaries.push(`${fieldLabel(field)}: ${message}`);
        } else {
          summaries.push(message);
        }
      }
    }

    const unique = [...new Set(summaries)];
    return {
      message: unique.length ? unique.join(' ') : fallbackMessage(Number(status) || 0),
      fieldErrors,
    };
  }

  class PlaceAIApiError extends Error {
    constructor(payload, status) {
      const normalized = normalize(payload, status);
      super(normalized.message);
      this.name = 'PlaceAIApiError';
      this.status = Number(status) || 0;
      this.fieldErrors = normalized.fieldErrors;
      this.code = payload && typeof payload === 'object' ? (payload.code || null) : null;
    }
  }

  function createError(payload, status) {
    return new PlaceAIApiError(payload, status);
  }

  async function fromResponse(response) {
    const contentType = response?.headers?.get?.('content-type') || '';
    let payload = {};
    if (contentType.includes('application/json')) {
      payload = await response.json().catch(() => ({}));
    }
    return createError(payload, response?.status || 0);
  }

  function selectorForName(name) {
    const escaped = globalThis.CSS?.escape ? globalThis.CSS.escape(name) : String(name).replace(/["\\]/g, '\\$&');
    return `[name="${escaped}"]`;
  }

  function clearForm(form) {
    if (!(form instanceof HTMLFormElement)) return;
    form.querySelectorAll('.placeai-field-error').forEach(node => node.remove());
    form.querySelectorAll('[aria-invalid="true"]').forEach(node => node.removeAttribute('aria-invalid'));
  }

  function applyToForm(form, error, summaryNode = null) {
    if (!(form instanceof HTMLFormElement)) return 0;
    clearForm(form);
    const fieldErrors = error?.fieldErrors && typeof error.fieldErrors === 'object' ? error.fieldErrors : {};
    let applied = 0;
    for (const [field, messages] of Object.entries(fieldErrors)) {
      const input = form.querySelector(selectorForName(field));
      if (!input) continue;
      input.setAttribute('aria-invalid', 'true');
      const note = document.createElement('small');
      note.className = 'placeai-field-error';
      note.dataset.field = field;
      note.setAttribute('role', 'alert');
      note.textContent = [...new Set(messages)].join(' ');
      const label = input.closest('label');
      if (label) label.appendChild(note);
      else input.insertAdjacentElement('afterend', note);
      applied += 1;
    }
    if (summaryNode) {
      summaryNode.textContent = error?.message || fallbackMessage(error?.status || 0);
      summaryNode.classList?.add('is-visible');
    }
    const firstInvalid = form.querySelector('[aria-invalid="true"]');
    if (firstInvalid && typeof firstInvalid.focus === 'function') firstInvalid.focus({preventScroll: true});
    return applied;
  }

  window.PlaceAIApiErrors = Object.freeze({
    PlaceAIApiError,
    normalize,
    createError,
    fromResponse,
    clearForm,
    applyToForm,
    fieldLabel,
    strongPasswordMessage,
    enhancePasswordPolicies,
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', installPasswordPolicyContract, {once: true});
  } else {
    installPasswordPolicyContract();
  }
})();
