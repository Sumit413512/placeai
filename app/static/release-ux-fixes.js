(() => {
  'use strict';

  const EXACT_COPY = new Map([
    ['Scattered résumés', 'Scattered resumes'],
    ['Profile completion, résumé records, documents, interview preparation and application history are tied to the signed-in student account.', 'Profile completion, resume records, documents, interview preparation and application history are tied to the signed-in student account.'],
    ['Profiles, document vault, résumé parsing, skills, readiness scoring and interview preparation.', 'Profiles, document vault, resume parsing, skills, readiness scoring and interview preparation.'],
    ['Résumé uploaded', 'Resume uploaded'],
    ['PARSED RÉSUMÉ DATA', 'PARSED RESUME DATA'],
  ]);

  const apiErrors = window.PlaceAIApiErrors;
  let provisioning = false;

  function normalizeCopy(root = document) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      const parent = node.parentElement;
      if (!parent || ['SCRIPT', 'STYLE', 'TEXTAREA', 'INPUT'].includes(parent.tagName)) continue;
      const current = node.nodeValue || '';
      let next = current;
      for (const [from, to] of EXACT_COPY.entries()) {
        if (next.includes(from)) next = next.replaceAll(from, to);
      }
      if (next !== current) node.nodeValue = next;
    }
  }

  function statusMessage(cell, text, kind = 'ok') {
    let node = cell.querySelector('.placeai-recruiter-provision-status');
    if (!node) {
      node = document.createElement('span');
      node.className = 'placeai-recruiter-provision-status';
      node.style.display = 'block';
      node.style.marginTop = '6px';
      node.style.fontSize = '11px';
      node.style.lineHeight = '1.4';
      cell.appendChild(node);
    }
    node.textContent = text;
    node.style.color = kind === 'error' ? '#9d2c2c' : '#526070';
  }

  function decorateAccessRows(root = document) {
    root.querySelectorAll?.('select[data-access-request-status]').forEach(select => {
      const row = select.closest('tr');
      const cell = select.closest('td');
      if (!row || !cell) return;
      const roleText = (row.children[1]?.textContent || '').trim().toLowerCase();
      const isRecruiter = roleText === 'recruiter';
      const eligible = isRecruiter && ['approved', 'provisioned'].includes(select.value);
      let button = cell.querySelector('[data-provision-recruiter-request]');
      if (!eligible) {
        button?.remove();
        return;
      }
      if (!button) {
        button = document.createElement('button');
        button.type = 'button';
        button.className = 'row-button primary';
        button.dataset.provisionRecruiterRequest = select.dataset.id || '';
        button.style.marginTop = '8px';
        cell.appendChild(button);
      }
      button.textContent = select.value === 'provisioned' ? 'Resend password setup link' : 'Provision recruiter';
      button.title = 'Atomically creates or updates the approved Recruiter account, then emails a one-time password setup link. No administrator chooses the permanent password.';
    });
  }

  function addRecruiterLoginHelp(root = document) {
    const form = root.querySelector?.('#role-login-form');
    if (!form) return;
    const role = form.querySelector('input[name="role"]')?.value;
    form.parentElement?.querySelector('.placeai-recruiter-login-help')?.remove();
    if (role !== 'recruiter') return;
    const note = document.createElement('div');
    note.className = 'access-security-note placeai-recruiter-login-help';
    note.innerHTML = '<strong>New recruiter account?</strong> After Platform Admin approval, use the one-time password setup link sent to your work email. You choose your own password there; an administrator does not need to create your permanent password.';
    form.insertAdjacentElement('afterend', note);
  }

  async function platformToken() {
    const response = await fetch('/auth/refresh', {
      method: 'POST',
      credentials: 'include',
      headers: {'Content-Type': 'application/json'},
      body: '{}',
    });
    if (!response.ok) throw new Error('Your Platform Admin session expired. Sign in again.');
    const payload = await response.json();
    if (!payload.access_token) throw new Error('Could not refresh the Platform Admin session.');
    return payload.access_token;
  }

  async function requestJson(path, options = {}) {
    const response = await fetch(path, {credentials: 'include', ...options});
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw apiErrors?.createError ? apiErrors.createError(payload, response.status) : new Error(payload.detail || 'Request failed.');
    }
    return payload;
  }

  async function provisionRecruiter(button) {
    if (provisioning) return;
    const requestId = button.dataset.provisionRecruiterRequest;
    const row = button.closest('tr');
    const select = row?.querySelector('select[data-access-request-status]');
    const cell = button.closest('td');
    const emailText = row?.children[0]?.querySelector('.table-secondary')?.textContent?.trim() || '';
    const email = emailText.split(' · ')[0].trim();
    if (!requestId || !cell || !email) return;

    const resend = select?.value === 'provisioned';
    const prompt = resend
      ? `Send a new one-time password setup link to ${email}?`
      : `Provision this Recruiter account and send a one-time password setup link to ${email}?`;
    if (!window.confirm(prompt)) return;

    provisioning = true;
    const original = button.textContent;
    button.disabled = true;
    button.textContent = resend ? 'Sending setup link…' : 'Provisioning recruiter…';
    try {
      const token = await platformToken();
      const result = await requestJson(`/platform/access-requests/${encodeURIComponent(requestId)}/provision-recruiter`, {
        method: 'POST',
        headers: {Authorization: `Bearer ${token}`},
      });
      if (select) {
        select.value = result.status || 'provisioned';
        select.dataset.currentStatus = select.value;
      }
      const message = result.setup_email_sent
        ? 'Recruiter account ready. A one-time password setup link was sent to the approved work email.'
        : 'The account was prepared, but the setup email could not be sent. Check transactional email health and retry.';
      statusMessage(cell, message, result.setup_email_sent ? 'ok' : 'error');
      decorateAccessRows(row || document);
    } catch (error) {
      statusMessage(cell, error?.message || 'Recruiter provisioning failed.', 'error');
      button.disabled = false;
      button.textContent = original;
    } finally {
      provisioning = false;
    }
  }

  async function updateAccessRequestStatus(select) {
    const requestId = select.dataset.id;
    const previousStatus = select.dataset.currentStatus || select.value;
    if (!requestId || select.value === previousStatus) return;
    select.disabled = true;
    try {
      const token = await platformToken();
      const result = await requestJson(`/platform/access-requests/${encodeURIComponent(requestId)}`, {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json', Authorization: `Bearer ${token}`},
        body: JSON.stringify({status: select.value, review_note: null}),
      });
      select.value = result.status;
      select.dataset.currentStatus = result.status;
      decorateAccessRows(select.closest('tr') || document);
    } catch (error) {
      select.value = previousStatus;
      const cell = select.closest('td');
      if (cell) statusMessage(cell, error?.message || 'Could not update the access request.', 'error');
    } finally {
      select.disabled = false;
    }
  }

  function apply(root = document) {
    normalizeCopy(root);
    decorateAccessRows(root);
    addRecruiterLoginHelp(document);
  }

  function install() {
    apply(document);
    const observer = new MutationObserver(records => {
      for (const record of records) {
        record.addedNodes.forEach(node => {
          if (node instanceof Element) apply(node);
        });
      }
      decorateAccessRows(document);
      addRecruiterLoginHelp(document);
    });
    observer.observe(document.body, {childList: true, subtree: true});

    document.addEventListener('change', event => {
      const select = event.target.closest?.('select[data-access-request-status]');
      if (!select) return;
      updateAccessRequestStatus(select);
    });

    document.addEventListener('click', event => {
      const button = event.target.closest?.('[data-provision-recruiter-request]');
      if (!button) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      provisionRecruiter(button);
    }, true);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, {once: true});
  else install();
})();
