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

  function randomChars(length, alphabet) {
    const bytes = new Uint8Array(length);
    crypto.getRandomValues(bytes);
    return [...bytes].map(value => alphabet[value % alphabet.length]).join('');
  }

  function secureTemporaryPassword() {
    const lower = 'abcdefghijkmnopqrstuvwxyz';
    const upper = 'ABCDEFGHJKLMNPQRSTUVWXYZ';
    const digits = '23456789';
    const symbols = '!@#$%^&*_-+=';
    const all = lower + upper + digits + symbols;
    const chars = [
      randomChars(1, lower),
      randomChars(1, upper),
      randomChars(1, digits),
      randomChars(1, symbols),
      ...randomChars(20, all),
    ].join('').split('');
    for (let i = chars.length - 1; i > 0; i -= 1) {
      const byte = new Uint8Array(1);
      crypto.getRandomValues(byte);
      const j = byte[0] % (i + 1);
      [chars[i], chars[j]] = [chars[j], chars[i]];
    }
    return chars.join('');
  }

  function recruiterUsername(email) {
    const local = String(email || '').split('@')[0].replace(/[^A-Za-z0-9._-]+/g, '_').replace(/^[._-]+|[._-]+$/g, '') || 'recruiter';
    const suffix = randomChars(6, 'abcdefghijkmnopqrstuvwxyz23456789');
    return `${local.slice(0, 72)}_${suffix}`;
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
      button.title = 'Creates the approved Recruiter account with an inaccessible one-time credential, then emails the recruiter a password setup link. No administrator chooses the permanent password.';
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
    const name = row?.children[0]?.querySelector('strong')?.textContent?.trim() || '';
    const emailText = row?.children[0]?.querySelector('span')?.textContent?.trim() || '';
    const email = emailText.split(' · ')[0].trim();
    const companyText = row?.children[2]?.textContent?.trim() || '';
    const company = companyText === '—' ? null : companyText;
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
      if (!resend) {
        const temporaryPassword = secureTemporaryPassword();
        await requestJson('/platform/recruiters', {
          method: 'POST',
          headers: {'Content-Type': 'application/json', Authorization: `Bearer ${token}`},
          body: JSON.stringify({
            email,
            username: recruiterUsername(email),
            full_name: name || null,
            company_name: company,
            temporary_password: temporaryPassword,
            organization_slug: null,
          }),
        });
        await requestJson(`/platform/access-requests/${encodeURIComponent(requestId)}`, {
          method: 'PATCH',
          headers: {'Content-Type': 'application/json', Authorization: `Bearer ${token}`},
          body: JSON.stringify({
            status: 'provisioned',
            review_note: 'Recruiter account provisioned. Permanent password is set by the recruiter through the one-time email setup link.',
          }),
        });
        if (select) select.value = 'provisioned';
      }

      await requestJson('/auth/forgot-password', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({email}),
      });
      statusMessage(cell, 'Recruiter account ready. A one-time password setup link was sent to the approved work email.');
      decorateAccessRows(row || document);
    } catch (error) {
      statusMessage(cell, error?.message || 'Recruiter provisioning failed.', 'error');
      button.disabled = false;
      button.textContent = original;
    } finally {
      provisioning = false;
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
      queueMicrotask(() => decorateAccessRows(select.closest('tr') || document));
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
