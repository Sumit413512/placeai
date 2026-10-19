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
  let googleLibrary;
  let googleConfiguration;
  let googleConfiguredUntil = 0;
  let googleNonce = '';
  let googleHandler;

  async function getGoogleConfiguration() {
    if (!googleConfiguration || Date.now() >= googleConfiguredUntil) {
      googleConfiguredUntil = Date.now() + 480000;
      googleConfiguration = requestJson('/auth/google-config').then(config => {
        googleConfiguredUntil = Date.now() + Math.max(0, Math.min(480, (config.expires_in ?? 600) - 60)) * 1000;
        return config;
      }).catch(error => {
        googleConfiguration = null;
        throw error;
      });
    }
    return googleConfiguration;
  }

  async function completeSignIn(session) {
    if (!window.PlaceAIAuth) throw new Error('The workspace is still loading. Please try again in a moment.');
    await window.PlaceAIAuth.completeSignIn(session);
  }

  function loadGoogleLibrary() {
    if (window.google?.accounts?.id) return Promise.resolve();
    if (!googleLibrary) googleLibrary = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'https://accounts.google.com/gsi/client';
      script.async = true;
      const failed = () => { clearTimeout(timer); googleLibrary = null; script.remove(); reject(new Error('Google sign-in could not load. Check your connection and retry.')); };
      const timer = setTimeout(failed, 15000);
      script.onload = () => { clearTimeout(timer); resolve(); };
      script.onerror = failed;
      document.head.appendChild(script);
    });
    return googleLibrary;
  }

  async function renderGoogleSignIn(view) {
    const signup = view.id === 'signup-view';
    const area = document.createElement('div');
    area.className = 'google-sign-in';
    area.setAttribute('aria-live', 'polite');
    view.querySelector('.access-login-methods').append(area);
    area.textContent = 'Loading Google sign-in…';
    try {
      const config = await getGoogleConfiguration();
      if (!area.isConnected) return;
      if (!config.enabled) {
        area.textContent = 'Google sign-in is being set up. Please use your email and password.';
        return;
      }
      await loadGoogleLibrary();
      if (!area.isConnected) return;
      area.textContent = '';
      const buttonHost = document.createElement('div');
      const feedback = document.createElement('p');
      feedback.className = 'access-form-error';
      feedback.setAttribute('role', 'status');
      feedback.setAttribute('aria-live', 'polite');
      area.append(buttonHost, feedback);
      let resizeObserver;
      let linking = false;
      let signingIn = false;
      const signIn = async (credential, role, proof = {}) => {
        if (signingIn) return;
        signingIn = true;
        const errorArea = $(signup ? '#role-create-error' : '#role-login-error', view);
        if (errorArea) errorArea.textContent = '';
        feedback.textContent = 'Finishing Google sign-in…';
        try {
          const session = await requestJson('/auth/google', {method:'POST', body:JSON.stringify({credential, role, ...proof})});
          if (session.email_link_required) {
            linking = true;
            resizeObserver?.disconnect();
            buttonHost.replaceChildren();
            feedback.textContent = session.message;
            const form = document.createElement('form');
            form.className = 'access-form';
            const label = document.createElement('label');
            label.textContent = 'Code sent to your email';
            const input = document.createElement('input');
            input.name = 'google_link_code'; input.type = 'text'; input.inputMode = 'numeric';
            input.autocomplete = 'one-time-code'; input.pattern = '[0-9]{6}';
            input.minLength = 6; input.maxLength = 6; input.required = true;
            label.append(input);
            const confirm = document.createElement('button');
            confirm.type = 'submit'; confirm.className = 'button button-primary button-full';
            confirm.textContent = 'Confirm email and sign in';
            form.append(label, confirm);
            form.addEventListener('submit', async event => {
              event.preventDefault();
              if (!form.reportValidity()) return;
              confirm.disabled = true;
              try { await signIn(credential, role, {link_challenge:session.link_challenge, link_code:input.value}); }
              finally { confirm.disabled = false; }
            });
            const restart = document.createElement('button');
            restart.type = 'button'; restart.className = 'button button-secondary button-full';
            restart.textContent = 'Restart Google sign-in';
            restart.onclick = () => { area.remove(); googleConfiguration = null; renderGoogleSignIn(view); };
            buttonHost.append(form, restart);
            input.focus();
            return;
          }
          await completeSignIn(session);
          googleConfiguration = null;
        } catch (error) {
          feedback.textContent = error.message;
          feedback.scrollIntoView({block:'nearest'});
        } finally {
          signingIn = false;
        }
      };
      googleHandler = result => {
        if (area.isConnected) signIn(result.credential, signup ? 'student' : loginRole);
      };
      if (googleNonce !== config.nonce) {
        window.google.accounts.id.initialize({client_id:config.client_id, nonce:config.nonce, auto_select:false,
          use_fedcm_for_button:true, button_auto_select:false,
          callback:result => googleHandler?.(result)});
        googleNonce = config.nonce;
      }
      let renderedWidth = 0;
      const renderButton = () => {
        if (!area.isConnected) { resizeObserver?.disconnect(); return; }
        if (linking) return;
        const width = Math.round(Math.min(400, area.clientWidth || Math.max(200, window.innerWidth - 96)));
        if (width === renderedWidth) return;
        renderedWidth = width;
        buttonHost.replaceChildren();
        window.google.accounts.id.renderButton(buttonHost, {type:'standard', theme:'outline', size:'large', text:signup ? 'signup_with' : 'continue_with', width,
          click_listener:() => {
            feedback.textContent = 'Continue in the Google window. If it does not open, use your regular Chrome or Safari browser and try again.';
          }});
      };
      renderButton();
      if (window.ResizeObserver) {
        resizeObserver = new ResizeObserver(renderButton);
        resizeObserver.observe(area);
      }
    } catch (error) {
      if (!area.isConnected) return;
      area.textContent = error.message;
      const retry = document.createElement('button');
      retry.type = 'button'; retry.className = 'button button-secondary button-full';
      retry.textContent = 'Retry Google sign-in';
      retry.onclick = () => { area.remove(); googleConfiguration = null; renderGoogleSignIn(view); };
      area.append(retry);
    }
  }

  function roleCards(selected, mode) {
    return `<div class="access-role-grid ${mode === 'login' ? 'access-login-roles' : ''}" role="tablist" aria-label="${mode === 'login' ? 'Sign-in role' : 'Account access role'}">${roleOrder.map(key => {
      const role = roles[key];
      return `<button type="button" class="access-role-card ${selected === key ? 'is-selected' : ''}" data-access-role="${key}" data-access-role-mode="${mode}" role="tab" aria-selected="${selected === key ? 'true' : 'false'}"><strong>${role.label}</strong><span>${role.description}</span><em>${role.access}</em></button>`;
    }).join('')}</div>`;
  }

  function modeTabs(active) {
    return `<div class="access-mode-row" role="tablist" aria-label="Account access"><button type="button" role="tab" aria-selected="${active === 'login'}" class="${active === 'login' ? 'is-active' : ''}" data-access-switch="login">Sign in</button><button type="button" role="tab" aria-selected="${active === 'create'}" class="${active === 'create' ? 'is-active' : ''}" data-access-switch="create">Sign up</button></div>`;
  }

  function renderLogin() {
    const view = $('#login-view');
    if (!view) return;
    const role = roles[loginRole];
    view.innerHTML = `${modeTabs('login')}<span class="section-kicker">Secure workspace access</span><h2 id="auth-title">Choose your role and sign in</h2><p class="form-intro">Welcome back. Continue with Google or sign in with your email and password. Google opens your assigned workspace automatically.</p>${roleCards(loginRole, 'login')}<div class="access-selection-summary"><span class="access-role-dot" aria-hidden="true"></span><div><b data-access-summary-label>${role.label}</b><span data-access-summary-short>${role.short}</span></div></div><div id="role-login-error" class="access-form-error" role="alert"></div><div class="access-login-methods"></div><div class="access-method-divider">or continue with email</div><form id="role-login-form" class="form-stack"><input type="hidden" name="role" value="${loginRole}"><label>Email address<input type="email" name="email" autocomplete="email" required placeholder="you@organization.com"></label><label>Password<div class="password-wrap"><input type="password" name="password" autocomplete="current-password" required maxlength="128" placeholder="Enter your password"><button type="button" data-access-toggle-password>Show</button></div></label><div class="form-row-between"><span></span><button type="button" class="text-button" data-action="forgot-password">Forgot password?</button></div><button class="button button-primary button-full" type="submit">Continue to ${role.label}</button></form><div class="access-security-note"><strong>Workspace access:</strong> Recruiter, Institution Admin and Platform Admin accounts cannot be created publicly. They must be provisioned or approved by an authorized administrator.</div>`;
    if (!$('#auth-overlay')?.classList.contains('hidden')) renderGoogleSignIn(view);
  }

  function updateLoginRole(roleKey) {
    const role = roles[roleKey];
    const view = $('#login-view');
    if (!role || !view) return;
    loginRole = roleKey;
    view.querySelectorAll('[data-access-role-mode="login"]').forEach(button => {
      const selected = button.dataset.accessRole === roleKey;
      button.classList.toggle('is-selected', selected);
      button.setAttribute('aria-selected', selected ? 'true' : 'false');
    });
    const form = $('#role-login-form', view);
    const hiddenRole = form?.querySelector('input[name="role"]');
    if (hiddenRole) hiddenRole.value = roleKey;
    const summary = view.querySelector('.access-selection-summary');
    const summaryLabel = summary?.querySelector('[data-access-summary-label]');
    const summaryShort = summary?.querySelector('[data-access-summary-short]');
    if (summaryLabel) summaryLabel.textContent = role.label;
    if (summaryShort) summaryShort.textContent = role.short;
    const submit = form?.querySelector('button[type="submit"]');
    if (submit) submit.textContent = `Continue to ${role.label}`;
    focusAccessForm('role-login-form');
  }

  function studentSignupForm() {
    return `<div class="access-selection-summary"><span class="access-role-dot" aria-hidden="true"></span><div><b>Student</b><span>Self-service registration</span></div></div><form id="role-student-signup-form" class="form-stack"><div class="form-two"><label>Full name<input name="full_name" required minlength="2" maxlength="200" placeholder="Your full name"></label><label>Username<input name="username" required minlength="3" maxlength="80" placeholder="e.g. student.name"></label></div><label>Email address<input type="email" name="email" autocomplete="email" required placeholder="you@example.com"></label><label>Institution code <span class="optional">optional</span><input name="organization_slug" maxlength="120" placeholder="Provided by your placement office"></label><label>Password<input type="password" name="password" autocomplete="new-password" minlength="12" maxlength="128" required aria-describedby="student-password-help" placeholder="12+ chars, upper/lowercase, number and symbol"><small id="student-password-help">Use 12+ characters with uppercase, lowercase, a number and a symbol.</small></label><div id="role-create-error" class="access-form-error" role="alert"></div><button class="button button-primary button-full" type="submit">Create student account</button></form>`;
  }

  function controlledAccessForm(roleKey) {
    const role = roles[roleKey];
    const organizationRequired = roleKey !== 'platform_admin';
    return `<div class="access-selection-summary"><span class="access-role-dot" aria-hidden="true"></span><div><b>${role.label}</b><span>${role.access}</span></div></div><form id="role-access-request-form" class="form-stack"><input type="hidden" name="requested_role" value="${roleKey}"><div class="form-two"><label>Full name<input name="full_name" required minlength="2" maxlength="200" placeholder="Your full name"></label><label>Work email<input type="email" name="work_email" autocomplete="email" required placeholder="you@organization.com"></label></div><label>Organization ${organizationRequired ? '' : '<span class="optional">optional</span>'}<input name="organization_name" ${organizationRequired ? 'required' : ''} maxlength="250" placeholder="Institution or company"></label><label>Phone <span class="optional">optional</span><input name="phone" maxlength="40" placeholder="+91 …"></label><label>Access context <span class="optional">optional</span><textarea name="message" rows="4" maxlength="3000" placeholder="Describe your role and why you need this workspace."></textarea></label><label class="hidden" aria-hidden="true">Website<input name="website" tabindex="-1" autocomplete="off"></label><div id="role-create-error" class="access-form-error" role="alert"></div><button class="button button-primary button-full" type="submit">Submit ${role.label} access request</button></form><div class="access-security-note"><strong>No automatic privileged account creation.</strong> Your request is stored in the production database for review. Access is activated only after authorized provisioning.</div>`;
  }

  function renderCreate() {
    const view = $('#signup-view');
    if (!view) return;
    const student = createRole === 'student';
    const form = createRole === 'student' ? studentSignupForm() : controlledAccessForm(createRole);
    const title = student ? 'Create your student account' : 'Request your workspace';
    const intro = student ? 'Sign up with your Google account. No PlaceAI password is needed.' : 'College, recruiter and platform access is reviewed before activation.';
    const methods = student ? '<div class="access-login-methods"></div><div class="access-method-divider">or sign up with email</div>' : roleCards(createRole, 'create');
    const requestLink = student ? '<p class="form-intro">Need a college or recruiter workspace? <button type="button" class="text-button" data-request-workspace>Request access</button></p>' : '';
    view.innerHTML = `${modeTabs('create')}<span class="section-kicker">${student ? 'New to PlaceAI?' : 'Organization access'}</span><h2 id="auth-create-title">${title}</h2><p class="form-intro">${intro}</p>${methods}${form}${requestLink}`;
    if (student && !$('#auth-overlay')?.classList.contains('hidden')) renderGoogleSignIn(view);
  }

  function normalizeAndFocusFirstInput(form) {
    const firstInput = [...form.querySelectorAll('input:not([type="hidden"]):not([disabled])')].find(input => input.getClientRects().length);
    if (!firstInput) return;
    if (firstInput.getAttribute('tabindex') === '-1') firstInput.removeAttribute('tabindex');
    firstInput.focus({preventScroll: true});
  }

  function focusVisibleForm(formId) {
    requestAnimationFrame(() => {
      const form = document.getElementById(formId);
      if (form) normalizeAndFocusFirstInput(form);
    });
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
      normalizeAndFocusFirstInput(form);
    });
  }

  function showView(name, opener = null) {
    const overlay = $('#auth-overlay');
    if (!overlay) return;
    window.PlaceAIModalState?.rememberOpener?.('auth', opener || document.activeElement);
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
    if (name === 'login') focusVisibleForm('role-login-form');
    else if (name === 'create') focusVisibleForm(createRole === 'student' ? 'role-student-signup-form' : 'role-access-request-form');
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
      const session = await requestJson('/auth/login-role', {method: 'POST', body: JSON.stringify(body)});
      await completeSignIn(session);
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
    if (password.length >= 20 && password.length <= 128 && new Set(password.toLowerCase()).size >= 8) return ;
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
      const registration = await requestJson('/auth/signup', {method: 'POST', body: JSON.stringify({username: body.username, email: body.email, password: body.password, role: 'student', organization_slug: body.organization_slug || null})});
      if (registration.verification_required) {
        form.reset(); setBusy(form, false);
        window.PlaceAIVerification.showPending(body.email, registration.message);
        return;
      }
      const login = await requestJson('/auth/login-role', {method: 'POST', body: JSON.stringify({email: body.email, password: body.password, role: 'student'})});
      if (body.full_name && login.access_token) {
        await requestJson('/students/profile', {method: 'PUT', headers: {Authorization: `Bearer ${login.access_token}`}, body: JSON.stringify({full_name: body.full_name})});
      }
      await completeSignIn(login);
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
      showView('login', loginOpen);
      return;
    }
    const requestOpen = event.target.closest('[data-open-access="request"]');
    if (requestOpen) {
      event.preventDefault();
      event.stopImmediatePropagation();
      createRole = 'student';
      showView('create', requestOpen);
      return;
    }
    const switcher = event.target.closest('[data-access-switch]');
    if (switcher) {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (switcher.dataset.accessSwitch === 'create') createRole = 'student';
      showView(switcher.dataset.accessSwitch === 'create' ? 'create' : 'login', switcher);
      return;
    }
    const workspaceRequest = event.target.closest('[data-request-workspace]');
    if (workspaceRequest) {
      event.preventDefault(); event.stopImmediatePropagation();
      createRole = 'institution_admin'; showView('create', workspaceRequest); return;
    }
    const roleButton = event.target.closest('[data-access-role]');
    if (roleButton) {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (roleButton.dataset.accessRoleMode === 'login') {
        updateLoginRole(roleButton.dataset.accessRole);
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
