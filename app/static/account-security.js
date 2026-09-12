(() => {
  'use strict';

  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const provisioningFormIds = new Set(['institution-student-form', 'institution-recruiter-form', 'admin-form']);
  const apiErrors = window.PlaceAIApiErrors;
  const ACCESS_STATUSES = ['new', 'under_review', 'approved', 'rejected', 'provisioned'];
  let accessEnhanceInFlight = false;

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

  function installSecurityButton() {
    const sidebar = document.querySelector('.sidebar-bottom');
    if (!sidebar || sidebar.querySelector('[data-account-security="change-password"]')) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'account-security-button';
    button.dataset.accountSecurity = 'change-password';
    button.innerHTML = '<span>Account security</span><strong>Change password</strong>';
    const signOut = sidebar.querySelector('.sidebar-user');
    sidebar.insertBefore(button, signOut || null);
  }

  function closePasswordDialog() {
    const overlay = document.querySelector('#password-rotation-overlay');
    if (!overlay || overlay.dataset.forced === 'true') return;
    overlay.remove();
    document.documentElement.classList.remove('placeai-password-rotation-open');
  }

  function showPasswordChange(user = null, forced = false) {
    if (document.querySelector('#password-rotation-overlay')) return;
    document.documentElement.classList.add('placeai-password-rotation-open');
    const overlay = document.createElement('div');
    overlay.id = 'password-rotation-overlay';
    overlay.className = 'password-rotation-overlay';
    overlay.dataset.forced = forced ? 'true' : 'false';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-labelledby', 'password-rotation-title');
    const accountName = esc(user?.username || user?.email || 'Your account');
    overlay.innerHTML = `<section class="password-rotation-card">
      ${forced ? '' : '<button class="password-rotation-close" type="button" data-account-security="close" aria-label="Close">×</button>'}
      <span class="password-rotation-kicker">Account security</span>
      <h2 id="password-rotation-title">${forced ? 'Create your permanent password' : 'Change your password'}</h2>
      <p>${forced ? `${accountName} was provisioned with a temporary password. Change it before entering the PlaceAI workspace.` : 'Enter your current password, then choose a strong new password. All older sessions will be invalidated.'}</p>
      <form id="password-rotation-form" class="password-rotation-form">
        <label>${forced ? 'Current temporary password' : 'Current password'}<input type="password" name="current_password" autocomplete="current-password" maxlength="128" required autofocus></label>
        <label>New password<input type="password" name="new_password" autocomplete="new-password" minlength="12" maxlength="128" required></label>
        <div class="password-rotation-help">Use 12+ characters with uppercase, lowercase, a number and a symbol.</div>
        <label>Confirm new password<input type="password" name="confirm_password" autocomplete="new-password" minlength="12" maxlength="128" required></label>
        <div id="password-rotation-error" class="password-rotation-error" role="alert"></div>
        <button class="password-rotation-submit" type="submit">${forced ? 'Change password and continue' : 'Change password'}</button>
      </form>
    </section>`;
    document.body.appendChild(overlay);

    const form = overlay.querySelector('#password-rotation-form');
    const error = overlay.querySelector('#password-rotation-error');
    const button = overlay.querySelector('button[type="submit"]');
    form.addEventListener('submit', async event => {
      event.preventDefault();
      event.stopImmediatePropagation();
      error.classList.remove('is-visible');
      error.textContent = '';
      const body = Object.fromEntries(new FormData(form).entries());
      const passwordError = validatePassword(String(body.new_password || ''));
      if (passwordError) {
        error.textContent = passwordError;
        error.classList.add('is-visible');
        return;
      }
      if (body.new_password !== body.confirm_password) {
        error.textContent = 'New password and confirmation do not match.';
        error.classList.add('is-visible');
        return;
      }
      if (body.current_password === body.new_password) {
        error.textContent = 'New password must be different from the current password.';
        error.classList.add('is-visible');
        return;
      }
      button.disabled = true;
      button.textContent = 'Updating password…';
      try {
        const response = await fetch('/auth/change-password', {
          method: 'POST',
          credentials: 'include',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            current_password: body.current_password,
            new_password: body.new_password,
          }),
        });
        const data = await response.json().catch(() => ({}));
        form.reset();
        if (!response.ok) throw apiErrors.createError(data, response.status);
        location.reload();
      } catch (err) {
        form.reset();
        apiErrors.applyToForm(form, err, error);
        button.disabled = false;
        button.textContent = forced ? 'Change password and continue' : 'Change password';
      }
    });
  }

  function formatDate(value) {
    if (!value) return '—';
    try {
      return new Intl.DateTimeFormat('en-IN', {day:'2-digit', month:'short', year:'numeric'}).format(new Date(value));
    } catch {
      return '—';
    }
  }

  function accessStatusBadge(value) {
    const safe = ACCESS_STATUSES.includes(value) ? value : 'new';
    return `<span class="status-badge status-${safe}">${esc(safe.replaceAll('_', ' '))}</span>`;
  }

  function accessReviewButton(row) {
    const label = row.status === 'new' ? 'Review' : row.status === 'approved' ? 'Provisioning' : 'Update';
    return `<button class="row-button ${row.status === 'new' || row.status === 'under_review' ? 'primary' : ''}" type="button" data-access-review="${esc(row.id)}">${label}</button>`;
  }

  function renderAccessRequests(panel, rows) {
    panel.dataset.placeaiAccessEnhanced = 'true';
    panel.innerHTML = `<div class="data-toolbar">
      <div><span class="table-primary">Privileged access review</span><span class="table-secondary">Platform Admin decisions are enforced by the backend. Approval authorizes provisioning; it does not create credentials by itself.</span></div>
      <span class="spacer"></span><span class="table-secondary">${rows.length} request${rows.length === 1 ? '' : 's'}</span>
    </div>
    <div class="table-wrap"><table class="data-table"><thead><tr>
      <th>Requester</th><th>Role</th><th>Organization</th><th>Received</th><th>Status</th><th>Action</th>
    </tr></thead><tbody>${rows.map(row => `<tr>
      <td><span class="table-primary">${esc(row.full_name)}</span><span class="table-secondary">${esc(row.work_email)}</span></td>
      <td>${esc(String(row.requested_role || '').replaceAll('_', ' '))}</td>
      <td>${esc(row.organization_name || '—')}</td>
      <td>${formatDate(row.created_at)}</td>
      <td>${accessStatusBadge(row.status)}${row.review_note ? `<span class="table-secondary">${esc(row.review_note)}</span>` : ''}</td>
      <td>${accessReviewButton(row)}</td>
    </tr>`).join('')}</tbody></table></div>`;
    panel._placeaiAccessRows = rows;
  }

  async function enhancePlatformAccessView() {
    const pageTitle = document.querySelector('#page-title')?.textContent?.trim();
    const content = document.querySelector('#app-content');
    const panel = content?.querySelector('.data-panel');
    if (pageTitle !== 'Access requests' || !panel || panel.dataset.placeaiAccessEnhanced === 'true' || accessEnhanceInFlight) return;
    accessEnhanceInFlight = true;
    try {
      const response = await fetch('/platform/access-requests', {credentials: 'include'});
      if (!response.ok) return;
      const rows = await response.json();
      if (document.querySelector('#page-title')?.textContent?.trim() !== 'Access requests') return;
      renderAccessRequests(panel, Array.isArray(rows) ? rows : []);
    } catch {
      // The core app remains usable even if the enhancement cannot load.
    } finally {
      accessEnhanceInFlight = false;
    }
  }

  function closeAccessReview() {
    document.querySelector('#placeai-access-review-overlay')?.remove();
    document.documentElement.classList.remove('placeai-password-rotation-open');
  }

  function openAccessReview(requestId) {
    const panel = document.querySelector('#app-content .data-panel');
    const rows = panel?._placeaiAccessRows || [];
    const row = rows.find(item => item.id === requestId);
    if (!row) return;

    document.documentElement.classList.add('placeai-password-rotation-open');
    const overlay = document.createElement('div');
    overlay.id = 'placeai-access-review-overlay';
    overlay.className = 'password-rotation-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    const options = ACCESS_STATUSES.map(status => `<option value="${status}" ${status === row.status ? 'selected' : ''}>${esc(status.replaceAll('_', ' '))}</option>`).join('');
    overlay.innerHTML = `<section class="password-rotation-card access-review-card">
      <button class="password-rotation-close" type="button" data-access-review-close aria-label="Close">×</button>
      <span class="password-rotation-kicker">Platform authorization</span>
      <h2>${esc(row.full_name)}</h2>
      <p>${esc(String(row.requested_role || '').replaceAll('_', ' '))} · ${esc(row.organization_name || 'No organization supplied')} · ${esc(row.work_email)}</p>
      <form id="placeai-access-review-form" class="password-rotation-form">
        <input type="hidden" name="request_id" value="${esc(row.id)}">
        <label>Review status<select name="status" class="access-review-select">${options}</select></label>
        <label>Internal review note<textarea name="review_note" rows="4" maxlength="3000">${esc(row.review_note || '')}</textarea></label>
        <div class="password-rotation-help">Approved means authorized for provisioning. Mark provisioned only after the correct role-specific account has actually been created. Permanent passwords are never emailed.</div>
        <div id="access-review-error" class="password-rotation-error" role="alert"></div>
        <button class="password-rotation-submit" type="submit">Save authorization decision</button>
      </form>
    </section>`;
    document.body.appendChild(overlay);
  }

  async function submitAccessReview(form) {
    const error = form.querySelector('#access-review-error');
    const button = form.querySelector('button[type="submit"]');
    const body = Object.fromEntries(new FormData(form).entries());
    error.classList.remove('is-visible');
    error.textContent = '';
    button.disabled = true;
    button.textContent = 'Saving decision…';
    try {
      const response = await fetch(`/platform/access-requests/${encodeURIComponent(body.request_id)}`, {
        method: 'PATCH',
        credentials: 'include',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          status: body.status,
          review_note: String(body.review_note || '').trim() || null,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw apiErrors.createError(data, response.status);
      closeAccessReview();
      const panel = document.querySelector('#app-content .data-panel');
      if (panel) {
        delete panel.dataset.placeaiAccessEnhanced;
        panel._placeaiAccessRows = null;
      }
      await enhancePlatformAccessView();
    } catch (err) {
      apiErrors.applyToForm(form, err, error);
      button.disabled = false;
      button.textContent = 'Save authorization decision';
    }
  }

  function installProtectionsAndEnhancements() {
    decorateProvisioningInputs();
    decorateCsvHandoff();
    installSecurityButton();
    enhancePlatformAccessView();

    const observer = new MutationObserver(records => {
      for (const record of records) {
        record.addedNodes.forEach(node => {
          if (!(node instanceof Element)) return;
          decorateProvisioningInputs(node);
          decorateCsvHandoff(node);
        });
      }
      installSecurityButton();
      queueMicrotask(enhancePlatformAccessView);
    });
    observer.observe(document.body, {childList: true, subtree: true});

    document.addEventListener('submit', event => {
      const form = event.target instanceof HTMLFormElement ? event.target : null;
      if (!form || form.id !== 'placeai-access-review-form') return;
      event.preventDefault();
      event.stopImmediatePropagation();
      submitAccessReview(form);
    }, true);

    document.addEventListener('change', event => {
      const input = event.target instanceof HTMLInputElement ? event.target : null;
      if (!input || input.id !== 'student-csv-file' || !input.files?.length) return;
      queueMicrotask(() => { input.value = ''; });
    });

    document.addEventListener('click', event => {
      const security = event.target.closest?.('[data-account-security]');
      if (security) {
        if (security.dataset.accountSecurity === 'change-password') showPasswordChange(null, false);
        else if (security.dataset.accountSecurity === 'close') closePasswordDialog();
        return;
      }
      const review = event.target.closest?.('[data-access-review]');
      if (review) {
        openAccessReview(review.dataset.accessReview);
        return;
      }
      if (event.target.closest?.('[data-access-review-close]')) closeAccessReview();
    });
  }

  async function init() {
    installProtectionsAndEnhancements();
    try {
      const response = await fetch('/auth/me', {credentials: 'include'});
      if (!response.ok) return;
      const user = await response.json();
      if (user?.must_change_password) showPasswordChange(user, true);
    } catch {
      // Unauthenticated public visitors should not see the forced-rotation surface.
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();