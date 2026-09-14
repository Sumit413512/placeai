(() => {
  'use strict';
  if (window.__PLACEAI_ACCESS_PORTAL_LOADED__) return;
  window.__PLACEAI_ACCESS_PORTAL_LOADED__ = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const esc = (value = '') => String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));

  const roles = {
    student: {
      label: 'Student',
      short: 'Student workspace',
      description: 'Applications, placement drives, readiness, documents and interview preparation.',
      access: 'Self-service registration'
    },
    recruiter: {
      label: 'Recruiter',
      short: 'Recruiter workspace',
      description: 'Verified jobs, approved candidate pipelines, interviews, offers and company verification.',
      access: 'Authorized provisioning'
    },
    institution_admin: {
      label: 'Institution Admin',
      short: 'Placement office',
      description: 'Students, recruiters, campus drives, approvals, attendance, reports and placement operations.',
      access: 'Institution-controlled access'
    },
    platform_admin: {
      label: 'Platform Admin',
      short: 'Platform control',
      description: 'Institution provisioning, platform operations, access review and administrative controls.',
      access: 'Restricted internal access'
    }
  };

  const roleOrder = ['student', 'recruiter', 'institution_admin', 'platform_admin'];
  let loginRole = 'student';
  let createRole = 'student';

  function roleCards(selected, mode) {
    return `<div class="access-role-grid">${roleOrder.map(key => {
      const role = roles[key];
      return `<button type="button" class="access-role-card ${selected === key ? 'is-selected' : ''}" data-access-role="${key}" data-access-role-mode="${mode}" aria-pressed="${selected === key ? 'true' : 'false'}"><strong>${role.label}</strong><span>${role.description}</span><em>${role.access}</em></button>`;
    }).join('')}</div>`;
  }

  function modeTabs(active) {
    return `<div class="access-mode-row" role="tablist" aria-label="Account access"><button type="button" class="${active === 'login' ? 'is-active' : ''}" data-access-switch="login">Sign in</button><button type="button" class="${active === 'create' ? 'is-active' : ''}" data-access-switch="create">Create / request access</button></div>`;
  }

  function renderLogin() {
    const view = $('#login-view');
    if (!view) return;
    const role = roles[loginRole];
    view.innerHTML = `${modeTabs('login')}<span class="section-kicker">Secure workspace access</span><h2 id="auth-title">Choose your role and sign in</h2><p class="form-intro">Select the workspace assigned to your account. The backend verifies that the selected role matches your actual account permissions.</p>${roleCards(loginRole, 'login')}<div class="access-selection-summary"><span class="access-role-dot"></span><div><b>${role.label}</b><span>${role.short}</span></div></div><form id="role-login-form" class="form-stack"><input type="hidden" name="role" value="${loginRole}"><label>Email address<input type="email" name="email" autocomplete="email" required placeholder="you@organization.com"></label><label>Password<div class="password-wrap"><input type="password" name="password" autocomplete="current-password" required maxlength="128" placeholder="Enter your password"><button type="button" data-access-toggle-password>Show</button></div></label><div id="role-login-error" class="access-form-error" role="alert"></div><div class="form-row-between"><span></span><button type="button" class="text-button" data-action="forgot-password">Forgot password?</button></div><button class="button button-primary button-full" type="submit">Continue to ${role.label}</button></form><div class="access-security-note"><strong>Account security:</strong> Recruiter, Institution Admin and Platform Admin accounts cannot be created publicly. They must be provisioned or approved by an authorized administrator.</div>`;
  }

  function studentSignupForm() {
    return `<div class="access-selection-summary"><span class="access-role-dot"></span><div><b>Student</b><span>Self-service registration</span></div></div><form id="role-student-signup-form" class="form-stack"><div class="form-two"><label>Full name<input name="full_name" required minlength="2" maxlength="200" placeholder="Your full name"></label><label>Username<input name="username" required minlength="3" maxlength="80" placeholder="e.g. student.name"></label></div><label>Email address<input type="email" name="email" autocomplete="email" required placeholder="you@example.com"></label><label>Institution code <span class="optional">optional</span><input name="organization_slug" maxlength="120" placeholder="Provided by your placement office"></label><label>Password<input type="password" name="password" autocomplete="new-password" minlength="12" maxlength="128" required aria-describedby="student-password-help" placeholder="12+ chars, upper/lowercase, number and symbol"><small id="student-password-help">Use 12+ characters with uppercase, lowercase, a number and a symbol.</small></label><div id="role-create-error" class="access-form-error" role="alert"></div><button class="button button-primary button-full" type="submit">Create student account</button></form>`;
  }

  function controlledAccessForm(roleKey) {
    const role = roles[roleKey];
    const organizationRequired = roleKey !== 'platform_admin';
    return `<div class="access-selection-summary"><span class="access-role-dot"></span><div><b>${role.label}</b><span>${role.access}</span></div></div><form id="role-access-request-form" class="form-stack"><input type="hidden" name="requested_role" value="${roleKey}"><div class="form-two"><label>Full name<input name="full_name" required minlength="2" maxlength="200" placeholder="Your full name"></label><label>Work email<input type="email" name="work_email" autocomplete="email" required placeholder="you@organization.com"></label></div><label>Organization ${organizationRequired ? '' : '<span class="optional">optional</span>'}<input name="organization_name" ${organizationRequired ? 'required' : ''} maxlength="250" placeholder="Institution or company"></label><label>Phone <span class="optional">optional</span><input name="phone" maxlength="40" placeholder="+91 …"></label><label>Access context <span class="optional">optional</span><textarea name="message" rows="4" maxlength="3000" placeholder="Describe your role and why you need this workspace."></textarea></label><label class="hidden" aria-hidden="true">Website<input name="website" tabindex="-1" autocomplete="off"></label><div id="role-create-error" class="access-form-error" role="alert"></div><button class="button button-primary button-full" type="submit">Submit ${role.label} access request</button></form><div class="access-security-note"><strong>No automatic privileged account creation.</strong> Your request is stored in the production database for review. Access is activated only after authorized provisioning.</div>`;
  }

  function renderCreate() {
    const view = $('#signup-view');
    if (!view) return;
    view.innerHTML = `${modeTabs('create')}<span class="section-kicker">Account access</span><h2 id="auth-create-title">Create or request the right workspace</h2><p class="form-intro">Choose the role you need. Student registration is self-service; privileged roles follow controlled provisioning.</p>${roleCards(createRole, 'create')}${createRole === 'student' ? studentSignupForm() : controlledAccessForm(createRole)}`;
  }

  function focusAccessForm(formId) {
    const panel = $('.auth-form-panel');
    if (panel) panel.scrollTop = 0;
    requestAnimationFrame(() => {
      const form = document.getElementById(formId);
      if (!form || !panel) return;
      const formRect = form.getBoundingClientRect();
      const panelRect = panel.getBoundingClientRect();
      const formTop = formRect.top - panelRect.top + panel.scrollTop;
      panel.scrollTop = Math.max(0, formTop - 12);
      const firstInput = [...form.querySelectorAll('input:not([type="hidden"]):not([disabled])')].find(input => input.getClientRects().length);
      if (firstInput) firstInput.focus({preventScroll: true});
    });
  }

  function showView(name) {
    const overlay = $('#auth-overlay');
    if (!overlay) return;
    window.PlaceAIModalState?.rememberOpener?.('auth');
    overlay.classList.remove('hidden');
    overlay.setAttribute('aria-labelledby', name === 'create' ? 'auth-create-title' : 'auth-title');
    ['login-view', 'signup-view', 'reset-view'].forEach(id => $("#" + id)?.classList.add('hidden'));
    if (name === 'create') {
      renderCreate();
      $('#signup-view')?.classList.remove('hidden');
    } else if (name === 'reset') {
      $('#reset-view')?.classList.remove('hidden');
    } else {
      renderLogin();
      $('#login-view')?.classList.remove('hidden');
    }
    if (name === 'create' || name === 'login') {
      const panel = $('.auth-form-panel');
      if (panel) panel.scrollTop = 0;
    }
    const modalState = window.PlaceAIModalState;
    if (modalState?.sync) modalState.sync();
    else document.body.classList.add('modal-open');
    modalState?.focusAuth?.();
  }

  const apiErrors = window.PlaceAIApiErrors;

  async function requestJson(path, options = {}) {
    const response = await fetch(path, {
      credentials: 'include',
      ...options,
      headers: {'Content-Type': 'application/json', ...(options.headers || {})}
    });
    const contentType = response.headers.get('content-type') || '';
    const data = contentType.includes('application/json') ? await response.json().catch(() => ({})) : {};
    if (!response.ok) throw apiErrors.createError(data, response.status);
    return data;
  }

  function setBusy(form, busy) {
    const button = $('button[type="submit"]', form);
    if (!button) return;
    if (!button.dataset.originalLabel) button.dataset.originalLabel = button.textContent;
    button.disabled = busy;
    button.textContent = busy ? 'Please wait…' : button.dataset.originalLabel;
  }

  async function loginSubmit(form) {
    setBusy(form, true);
    try {
      const body = Object.fromEntries(new FormData(form).entries());
      await requestJson('/auth/login-role', {method: 'POST', body: JSON.stringify(body)});
      location.reload();
    } catch (error) {
      apiErrors.applyToForm(form, error, $('#role-login-error'));
      setBusy(form, false);
    }
  }

  function validateStudentSignup(body) {
    const username = String(body.username || '').trim();
    const password = String(body.password || '');
    if (!/^[A-Za-z0-9._-]{3,80}$/.test(username)) throw new Error('Username may only contain letters, numbers, dot, underscore, and hyphen.');
    if (password.length < 12) throw new Error('Password must be at least 12 characters long.');
    if (!/[a-z]/.test(password)) throw new Error('Password must contain a lowercase letter.');
    if (!/[A-Z]/.test(password)) throw new Error('Password must contain an uppercase letter.');
    if (!/[0-9]/.test(password)) throw new Error('Password must contain a number.');
    if (!/[^A-Za-z0-9]/.test(password)) throw new Error('Password must contain a symbol.');
  }

  async function studentSignupSubmit(form) {
    setBusy(form, true);
    try {
      const body = Object.fromEntries(new FormData(form).entries());
      body.username = String(body.username || '').trim();
      body.email = String(body.email || '').trim();
      body.organization_slug = String(body.organization_slug || '').trim();
      validateStudentSignup(body);
      await requestJson('/auth/signup', {method: 'POST', body: JSON.stringify({username: body.username, email: body.email, password: body.password, role: 'student', organization_slug: body.organization_slug || null})});
      const login = await requestJson('/auth/login-role', {method: 'POST', body: JSON.stringify({email: body.email, password: body.password, role: 'student'})});
      if (body.full_name && login.access_token) {
        await requestJson('/students/profile', {method: 'PUT', headers: {Authorization: `Bearer ${login.access_token}`}, body: JSON.stringify({full_name: body.full_name})});
      }
      location.reload();
    } catch (error) {
      apiErrors.applyToForm(form, error, $('#role-create-error'));
      setBusy(form, false);
    }
  }

  async function accessRequestSubmit(form) {
    setBusy(form, true);
    try {
      const body = Object.fromEntries(new FormData(form).entries());
      const result = await requestJson('/public/access-requests', {method: 'POST', body: JSON.stringify(body)});
      const view = $('#signup-view');
      if (view) {
        view.innerHTML = `${modeTabs('create')}<div class="access-request-success" tabindex="-1"><div class="success-mark">✓</div><span class="section-kicker">Request received</span><h2 id="auth-access-success-title">Your ${roles[body.requested_role]?.label || 'account'} access request is recorded.</h2><p>${esc(result.message || 'An authorized administrator will review the request before any account is provisioned.')}</p><button type="button" class="button button-primary button-full" data-access-switch="login">Return to sign in</button></div>`;
        $('#auth-overlay')?.setAttribute('aria-labelledby', 'auth-access-success-title');
        const panel = $('.auth-form-panel');
        if (panel) panel.scrollTop = 0;
        requestAnimationFrame(() => view.querySelector('.access-request-success')?.focus({preventScroll: true}));
      }
    } catch (error) {
      apiErrors.applyToForm(form, error, $('#role-create-error'));
      setBusy(form, false);
    }
  }

  function relabelPlatformNavigation() {
    const leadButton = $('#app-nav button[data-view="leads"]');
    const label = leadButton?.querySelector('.nav-label');
    if (label && label.textContent !== 'Access requests') label.textContent = 'Access requests';
  }

  document.addEventListener('click', event => {
    const loginOpen = event.target.closest('[data-open-auth="login"]');
    if (loginOpen) {
      event.preventDefault();
      event.stopImmediatePropagation();
      showView('login');
      return;
    }
    const requestOpen = event.target.closest('[data-open-access="request"]');
    if (requestOpen) {
      event.preventDefault();
      event.stopImmediatePropagation();
      createRole = 'institution_admin';
      showView('create');
      return;
    }
    const switcher = event.target.closest('[data-access-switch]');
    if (switcher) {
      event.preventDefault();
      event.stopImmediatePropagation();
      showView(switcher.dataset.accessSwitch === 'create' ? 'create' : 'login');
      return;
    }
    const roleButton = event.target.closest('[data-access-role]');
    if (roleButton) {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (roleButton.dataset.accessRoleMode === 'login') {
        loginRole = roleButton.dataset.accessRole;
        renderLogin();
        focusAccessForm('role-login-form');
      } else {
        createRole = roleButton.dataset.accessRole;
        renderCreate();
        focusAccessForm(createRole === 'student' ? 'role-student-signup-form' : 'role-access-request-form');
      }
      return;
    }
    const togglePassword = event.target.closest('[data-access-toggle-password]');
    if (togglePassword) {
      event.preventDefault();
      event.stopImmediatePropagation();
      const input = togglePassword.parentElement?.querySelector('input');
      if (input) {
        input.type = input.type === 'password' ? 'text' : 'password';
        togglePassword.textContent = input.type === 'password' ? 'Show' : 'Hide';
      }
    }
  }, true);

  document.addEventListener('submit', event => {
    const form = event.target;
    if (!['role-login-form', 'role-student-signup-form', 'role-access-request-form'].includes(form.id)) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    if (form.id === 'role-login-form') loginSubmit(form);
    else if (form.id === 'role-student-signup-form') studentSignupSubmit(form);
    else accessRequestSubmit(form);
  }, true);

  const observer = new MutationObserver(() => relabelPlatformNavigation());

  function init() {
    renderLogin();
    renderCreate();
    relabelPlatformNavigation();
    const nav = $('#app-nav');
    if (nav) observer.observe(nav, {childList: true, subtree: true});
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
