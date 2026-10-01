(() => {
  'use strict';

  const ROLE_META = {
    student: {label: 'Student workspace', short: 'Student'},
    recruiter: {label: 'Recruiter workspace', short: 'Recruiter'},
    institution_admin: {label: 'Placement office', short: 'Institution'},
    platform_admin: {label: 'Platform operations', short: 'Platform Admin'}
  };

  let scheduled = false;

  function normalizedRole() {
    const raw = String(document.querySelector('#sidebar-user-role')?.textContent || '')
      .trim()
      .toLowerCase()
      .replaceAll(' ', '_');
    return ROLE_META[raw] ? raw : '';
  }

  function ensureRoleContext(role) {
    const shell = document.querySelector('#app-shell');
    const context = document.querySelector('.topbar-context');
    if (!shell || !context || !role) return;

    shell.dataset.placeaiRole = role;

    let chip = context.querySelector('.workspace-role-chip');
    if (!chip) {
      chip = document.createElement('span');
      chip.className = 'workspace-role-chip';
      context.appendChild(chip);
    }
    chip.textContent = ROLE_META[role].short;
    chip.title = ROLE_META[role].label;
  }

  function decorateNavigation() {
    const shell = document.querySelector('#app-shell');
    const active = document.querySelector('#app-nav button.active');
    const role = normalizedRole();
    if (shell && active?.dataset.view) shell.dataset.placeaiView = active.dataset.view;

    document.querySelectorAll('#app-nav button[data-view]').forEach(button => {
      const selected = button.classList.contains('active');
      if (selected) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');

      const label = button.querySelector('.nav-label')?.textContent?.trim();
      if (label && !button.title) button.title = label;
    });

    ensureRoleContext(role);
  }

  function decorateTables(root = document) {
    const tables = [];
    if (root instanceof HTMLTableElement) tables.push(root);
    root.querySelectorAll?.('.data-table').forEach(table => tables.push(table));

    for (const table of tables) {
      if (table.dataset.placeaiTableEnhanced === '1') continue;
      const headers = [...table.querySelectorAll('thead th')].map(th => th.textContent.trim());
      if (!headers.length) continue;

      table.dataset.placeaiResponsive = 'true';
      table.querySelectorAll('tbody tr').forEach(row => {
        [...row.children].forEach((cell, index) => {
          if (!(cell instanceof HTMLTableCellElement)) return;
          cell.dataset.label = headers[index] || 'Details';
        });
      });
      table.dataset.placeaiTableEnhanced = '1';
    }
  }

  function humanizeStatuses(root = document) {
    const badges = [];
    if (root instanceof Element && root.matches('.status-badge,.status-pill')) badges.push(root);
    root.querySelectorAll?.('.status-badge,.status-pill').forEach(node => badges.push(node));

    for (const badge of badges) {
      if (badge.dataset.placeaiStatusEnhanced === '1') continue;
      const current = badge.textContent.trim();
      if (current.includes('_')) {
        badge.textContent = current
          .replaceAll('_', ' ')
          .replace(/\b\w/g, char => char.toUpperCase());
      }
      badge.dataset.placeaiStatusEnhanced = '1';
    }
  }

  function professionalizeAiUnavailable(root = document) {
    const role = normalizedRole();
    if (!role || role === 'platform_admin') return;

    const notes = [];
    if (root instanceof Element && root.matches('.placeai-ai-unavailable-note')) notes.push(root);
    root.querySelectorAll?.('.placeai-ai-unavailable-note').forEach(note => notes.push(note));

    for (const note of notes) {
      const title = note.querySelector('strong');
      const copy = note.querySelector('p');
      if (title) title.textContent = 'AI tool temporarily unavailable';
      if (copy) copy.textContent = 'You can continue using the rest of your PlaceAI workspace. Try this feature again later.';
    }
  }

  function standardizeControls(root = document) {
    const buttons = [];
    if (root instanceof HTMLButtonElement) buttons.push(root);
    root.querySelectorAll?.('button').forEach(button => buttons.push(button));

    for (const button of buttons) {
      if (!button.hasAttribute('type') && !button.closest('form')) button.type = 'button';
    }

    const searches = [];
    if (root instanceof HTMLInputElement && root.type === 'search') searches.push(root);
    root.querySelectorAll?.('input[type="search"],.search-box').forEach(input => searches.push(input));
    for (const input of searches) {
      if (!input.getAttribute('autocomplete')) input.setAttribute('autocomplete', 'off');
      if (!input.getAttribute('spellcheck')) input.setAttribute('spellcheck', 'false');
    }
  }

  function enhance(root = document) {
    decorateNavigation();
    decorateTables(root);
    humanizeStatuses(root);
    professionalizeAiUnavailable(root);
    standardizeControls(root);
  }

  function schedule(root = document) {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      enhance(root);
    });
  }

  function install() {
    enhance(document);

    const observer = new MutationObserver(records => {
      const hasElementChanges = records.some(record =>
        [...record.addedNodes].some(node => node instanceof Element)
      );
      if (hasElementChanges) schedule(document);
    });

    observer.observe(document.body, {childList: true, subtree: true});

    document.addEventListener('click', event => {
      if (event.target.closest?.('#app-nav button[data-view]')) schedule(document);
    });

    window.PlaceAIWorkspaceExperience = Object.freeze({
      refresh: () => enhance(document),
      role: normalizedRole
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', install, {once: true});
  } else {
    install();
  }
})();
