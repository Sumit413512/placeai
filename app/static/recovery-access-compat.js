(() => {
  'use strict';
  if (window.__PLACEAI_RECOVERY_ACCESS_COMPAT__) return;
  window.__PLACEAI_RECOVERY_ACCESS_COMPAT__ = true;

  const STATUS_SELECTOR = 'select[data-access-request-status]';
  let provisioning = false;

  function statusMessage(cell, text, kind = 'ok') {
    if (!cell) return;
    let node = cell.querySelector('.placeai-recovery-provision-status');
    if (!node) {
      node = document.createElement('span');
      node.className = 'placeai-recovery-provision-status';
      node.style.display = 'block';
      node.style.marginTop = '6px';
      node.style.fontSize = '11px';
      node.style.lineHeight = '1.4';
      cell.appendChild(node);
    }
    node.textContent = text;
    node.style.color = kind === 'error' ? '#9d2c2c' : '#526070';
  }

  function syncManagedProvisionedStatus(select) {
    if (!select) return;
    const current = select.dataset.currentStatus || select.value;
    const provisionedOptions = [...select.options].filter(option => option.value === 'provisioned');

    if (current === 'provisioned') {
      let option = provisionedOptions[0];
      if (!option) {
        option = new Option('Provisioned', 'provisioned', true, true);
        select.add(option);
      }
      provisionedOptions.slice(1).forEach(item => item.remove());
      select.value = 'provisioned';
      select.dataset.currentStatus = 'provisioned';
      select.disabled = true;
      select.title = 'Provisioned status is system-managed by the recruiter provisioning workflow.';
      return;
    }

    provisionedOptions.forEach(option => option.remove());
    if (!select.dataset.currentStatus) select.dataset.currentStatus = select.value;
    select.disabled = false;
    select.removeAttribute('title');
  }

  function syncAll(root = document) {
    if (root.matches?.(STATUS_SELECTOR)) syncManagedProvisionedStatus(root);
    root.querySelectorAll?.(STATUS_SELECTOR).forEach(syncManagedProvisionedStatus);
  }

  async function platformToken() {
    const response = await fetch('/auth/refresh', {
      method: 'POST',
      credentials: 'include',
      headers: {'Content-Type': 'application/json'},
      body: '{}',
    });
    if (!response.ok) throw new Error('Your Platform Admin session expired. Sign in again.');
    const payload = await response.json().catch(() => ({}));
    if (!payload.access_token) throw new Error('Could not refresh the Platform Admin session.');
    return payload.access_token;
  }

  async function provisionRecruiter(button) {
    if (provisioning) return;
    const requestId = button.dataset.provisionRecruiterRequest;
    const row = button.closest('tr');
    const select = row?.querySelector(STATUS_SELECTOR);
    const cell = button.closest('td');
    if (!requestId || !cell) return;

    const resend = (select?.dataset.currentStatus || select?.value) === 'provisioned';
    const promptText = resend
      ? 'Send a new one-time password setup link for this Recruiter account?'
      : 'Provision this approved Recruiter account and send its one-time password setup link?';
    if (!window.confirm(promptText)) return;

    provisioning = true;
    const original = button.textContent;
    button.disabled = true;
    button.textContent = resend ? 'Sending setup link…' : 'Provisioning recruiter…';

    try {
      const token = await platformToken();
      const response = await fetch(
        `/platform/access-requests/${encodeURIComponent(requestId)}/provision-recruiter`,
        {
          method: 'POST',
          credentials: 'include',
          headers: {Authorization: `Bearer ${token}`},
        },
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || 'Recruiter provisioning failed.');

      if (select && payload.status) {
        select.dataset.currentStatus = payload.status;
        if (payload.status === 'provisioned' && ![...select.options].some(option => option.value === 'provisioned')) {
          select.add(new Option('Provisioned', 'provisioned', true, true));
        }
        select.value = payload.status;
        syncManagedProvisionedStatus(select);
      }

      statusMessage(
        cell,
        payload.message || (payload.setup_email_sent
          ? 'Recruiter account ready. A one-time password setup link was sent to the approved work email.'
          : 'Recruiter account exists, but the setup email was not delivered. Retry after email delivery is healthy.'),
        payload.setup_email_sent === false ? 'error' : 'ok',
      );
      button.textContent = payload.status === 'provisioned' ? 'Resend password setup link' : original;
      button.disabled = false;
    } catch (error) {
      statusMessage(cell, error?.message || 'Recruiter provisioning failed.', 'error');
      button.textContent = original;
      button.disabled = false;
    } finally {
      provisioning = false;
    }
  }

  // This capture listener is intentionally registered before the legacy recovery
  // release-ux listener. It prevents the old create-user -> manual-status-PATCH flow
  // and delegates the entire operation to the canonical atomic provisioning endpoint.
  document.addEventListener('click', event => {
    const button = event.target.closest?.('[data-provision-recruiter-request]');
    if (!button) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    void provisionRecruiter(button);
  }, true);

  function install() {
    syncAll(document);
    const observer = new MutationObserver(records => {
      for (const record of records) {
        record.addedNodes.forEach(node => {
          if (node instanceof Element) syncAll(node);
        });
      }
      syncAll(document);
    });
    observer.observe(document.body, {childList: true, subtree: true});
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, {once: true});
  else install();
})();
