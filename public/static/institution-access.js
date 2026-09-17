(() => {
  'use strict';
  if (window.__PLACEAI_INSTITUTION_ACCESS_LOADED__) return;
  window.__PLACEAI_INSTITUTION_ACCESS_LOADED__ = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const esc = (value = '') => String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  const MANUAL_STATUSES = ['new', 'under_review', 'approved', 'rejected'];
  let customOpen = false;
  let rendering = false;

  function institutionAdminVisible() {
    const shell = $('#app-shell');
    const role = ($('#sidebar-user-role')?.textContent || '').trim().toLowerCase().replaceAll('_', ' ');
    return Boolean(shell && !shell.classList.contains('hidden') && role === 'institution admin');
  }

  function toast(title, message = '', type = 'success') {
    const region = $('#toast-region');
    if (!region) return;
    const node = document.createElement('div');
    node.className = `toast ${type}`;
    node.innerHTML = `<div><strong>${esc(title)}</strong>${message ? `<span>${esc(message)}</span>` : ''}</div>`;
    region.appendChild(node);
    setTimeout(() => node.remove(), 3800);
  }

  async function accessToken() {
    const response = await fetch('/auth/refresh', {
      method: 'POST',
      credentials: 'include',
      headers: {'Content-Type': 'application/json'},
      body: '{}',
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.access_token) {
      throw new Error(payload.detail || 'Your Institution Admin session expired. Sign in again.');
    }
    return payload.access_token;
  }

  async function requestJson(path, options = {}) {
    const token = await accessToken();
    const headers = new Headers(options.headers || {});
    headers.set('Authorization', `Bearer ${token}`);
    if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }
    const response = await fetch(path, {...options, headers, credentials: 'include'});
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || 'Request failed.');
    return payload;
  }

  function navIcon() {
    return '<span class="nav-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h16v16H4zM4 9h16M8 13h8M8 17h5"/></svg></span>';
  }

  function ensureNavigation() {
    if (!institutionAdminVisible()) return;
    const nav = $('#app-nav');
    if (!nav || nav.querySelector('[data-institution-access-requests]')) return;

    const group = document.createElement('div');
    group.className = 'nav-group-label';
    group.dataset.institutionAccessGroup = '';
    group.textContent = 'Access';

    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.institutionAccessRequests = '';
    button.innerHTML = `${navIcon()}<span class="nav-label">Access requests</span>`;
    button.setAttribute('aria-label', 'Access requests');

    const trustGroup = [...nav.querySelectorAll('.nav-group-label')]
      .find(node => (node.textContent || '').trim().toLowerCase() === 'trust');
    if (trustGroup) {
      nav.insertBefore(group, trustGroup);
      nav.insertBefore(button, trustGroup);
    } else {
      nav.append(group, button);
    }
    if (customOpen) markActive(button);
  }

  function markActive(button = $('[data-institution-access-requests]')) {
    const nav = $('#app-nav');
    nav?.querySelectorAll('button.active').forEach(item => item.classList.remove('active'));
    button?.classList.add('active');
    button?.setAttribute('aria-current', 'page');
  }

  function clearCustomActive() {
    const button = $('[data-institution-access-requests]');
    button?.classList.remove('active');
    button?.removeAttribute('aria-current');
  }

  function formatDate(value) {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '—';
    return new Intl.DateTimeFormat('en-IN', {day:'2-digit', month:'short', year:'numeric'}).format(date);
  }

  function statusSelect(row) {
    if (row.status === 'provisioned') {
      return '<span class="status-badge status-approved">provisioned</span><span class="table-secondary">Account already provisioned</span>';
    }
    return `<select class="filter-select" data-institution-access-status data-id="${esc(row.id)}" data-current-status="${esc(row.status)}" aria-label="Access request status for ${esc(row.full_name)}">${MANUAL_STATUSES.map(status => `<option value="${status}" ${status === row.status ? 'selected' : ''}>${esc(status.replaceAll('_',' '))}</option>`).join('')}</select>`;
  }

  function renderRows(rows) {
    if (!rows.length) {
      return '<div class="empty-state"><div class="empty-icon">AR</div><h3>No recruiter access requests</h3><p>Recruiter requests linked to this institution will appear here for placement-office review.</p></div>';
    }
    return `<div class="data-panel"><div class="data-toolbar"><span class="table-secondary">${rows.length} institution-scoped request${rows.length === 1 ? '' : 's'}</span></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Requester</th><th>Organization</th><th>Context</th><th>Received</th><th>Status / action</th></tr></thead><tbody>${rows.map(row => `<tr><td><span class="table-primary">${esc(row.full_name)}</span><span class="table-secondary">${esc(row.work_email)}</span>${row.phone ? `<span class="table-secondary">${esc(row.phone)}</span>` : ''}</td><td>${esc(row.organization_name || '—')}</td><td>${esc(row.message || 'No access context provided.')}</td><td>${formatDate(row.created_at)}</td><td>${statusSelect(row)}</td></tr>`).join('')}</tbody></table></div></div>`;
  }

  async function renderAccessRequests() {
    if (!institutionAdminVisible() || rendering) return;
    rendering = true;
    customOpen = true;
    ensureNavigation();
    markActive();

    const title = $('#page-title');
    const eyebrow = $('#page-eyebrow');
    const content = $('#app-content');
    const contextAction = $('#context-action');
    if (title) title.textContent = 'Access requests';
    if (eyebrow) eyebrow.textContent = 'Institution access';
    if (contextAction) contextAction.classList.add('hidden');
    if (content) content.innerHTML = '<div class="loading-state"><span class="loader"></span><p>Loading institution access requests…</p></div>';

    try {
      const rows = await requestJson('/institutions/access-requests');
      if (!customOpen || !content) return;
      content.innerHTML = `<div class="page-head"><div><h1>Recruiter access requests</h1><p>Review recruiter workspace requests linked only to your institution. Platform and Institution Admin requests remain under Platform Admin control.</p></div></div>${renderRows(rows)}`;
      markActive();
    } catch (error) {
      if (content && customOpen) {
        content.innerHTML = `<div class="page-head"><div><h1>Access requests</h1><p>${esc(error.message || 'Unable to load this view.')}</p></div></div><div class="empty-state"><div class="empty-icon">!</div><h3>Unable to load access requests</h3><p>${esc(error.message || 'Try again.')}</p><button class="button button-secondary" type="button" data-institution-access-retry>Try again</button></div>`;
      }
    } finally {
      rendering = false;
    }
  }

  async function updateStatus(select) {
    const requestId = select.dataset.id;
    const previous = select.dataset.currentStatus || select.value;
    const next = select.value;
    if (!requestId || next === previous) return;
    select.disabled = true;
    try {
      const row = await requestJson(`/institutions/access-requests/${encodeURIComponent(requestId)}`, {
        method: 'PATCH',
        body: JSON.stringify({status: next, review_note: null}),
      });
      select.dataset.currentStatus = row.status;
      select.value = row.status;
      toast('Access request updated', `Status changed to ${String(row.status).replaceAll('_',' ')}.`);
    } catch (error) {
      select.value = previous;
      toast('Update failed', error.message || 'Could not update the access request.', 'error');
    } finally {
      select.disabled = false;
    }
  }

  function install() {
    ensureNavigation();
    const observer = new MutationObserver(() => ensureNavigation());
    observer.observe(document.documentElement, {childList:true, subtree:true, attributes:true, attributeFilter:['class']});

    document.addEventListener('click', event => {
      const custom = event.target.closest?.('[data-institution-access-requests]');
      if (custom) {
        event.preventDefault();
        event.stopImmediatePropagation();
        renderAccessRequests();
        return;
      }
      if (event.target.closest?.('[data-institution-access-retry]')) {
        event.preventDefault();
        renderAccessRequests();
        return;
      }
      if (event.target.closest?.('#app-nav button[data-view]')) {
        customOpen = false;
        clearCustomActive();
      }
    }, true);

    document.addEventListener('change', event => {
      const select = event.target.closest?.('[data-institution-access-status]');
      if (!select) return;
      updateStatus(select);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, {once:true});
  else install();
})();
