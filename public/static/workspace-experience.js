(() => {
  'use strict';

  const ROLE_META = {
    student: {label: 'Student workspace', short: 'Student'},
    recruiter: {label: 'Recruiter workspace', short: 'Recruiter'},
    institution_admin: {label: 'Placement office', short: 'Institution'},
    platform_admin: {label: 'Platform operations', short: 'Platform Admin'}
  };

  const ROLE_SECONDARY_VIEWS = Object.freeze({
    student: new Set(['documents','assistant','calendar','announcements','notifications','incidents','approvals','profile']),
    recruiter: new Set(['communications','analytics','assistant','notifications','profile']),
    institution_admin: new Set(['institution-access-requests','verification','attendance','calendar','announcements','communications','policies','custom-fields','incidents','reports','notifications','audit']),
    platform_admin: new Set()
  });

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

    // The sidebar already identifies the role. Do not add a second role badge
    // beside the page title when views or account roles change.
    context.querySelector('.workspace-role-chip')?.remove();
  }

  function navPreferenceKey(role) {
    return 'placeai_nav_more_' + role;
  }

  function readNavPreference(role) {
    try { return sessionStorage.getItem(navPreferenceKey(role)) === '1'; }
    catch { return false; }
  }

  function writeNavPreference(role, expanded) {
    try { sessionStorage.setItem(navPreferenceKey(role), expanded ? '1' : '0'); }
    catch {}
  }

  function setMoreButtonLabel(button, expanded) {
    const label = expanded ? 'Show fewer' : 'More tools';
    if (!button.firstChild) button.appendChild(document.createTextNode(label));
    else if (button.firstChild.nodeType === Node.TEXT_NODE && button.firstChild.nodeValue !== label) button.firstChild.nodeValue = label;
    button.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    button.title = expanded ? 'Show fewer workspace tools' : 'Show all workspace tools';
  }

  function decorateNavigation() {
    const shell = document.querySelector('#app-shell');
    const nav = document.querySelector('#app-nav');
    const active = nav?.querySelector('button.active[data-view]');
    const role = normalizedRole();
    if (shell && active?.dataset.view) shell.dataset.placeaiView = active.dataset.view;
    if (!nav || !role) {
      ensureRoleContext(role);
      return;
    }

    const secondaryViews = ROLE_SECONDARY_VIEWS[role] || new Set();
    const buttons = [...nav.querySelectorAll('button[data-view]')];
    for (const button of buttons) {
      const selected = button.classList.contains('active');
      if (selected) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');

      const label = button.querySelector('.nav-label')?.textContent?.trim();
      if (label && !button.title) button.title = label;
      button.dataset.placeaiSecondary = secondaryViews.has(button.dataset.view) ? 'true' : 'false';
    }

    let currentLabel = null;
    let currentButtons = [];
    const finishGroup = () => {
      if (!currentLabel) return;
      const allSecondary = currentButtons.length > 0 && currentButtons.every(button => button.dataset.placeaiSecondary === 'true');
      currentLabel.dataset.placeaiSecondary = allSecondary ? 'true' : 'false';
    };
    for (const child of [...nav.children]) {
      if (child.classList?.contains('placeai-nav-more')) continue;
      if (child.classList?.contains('nav-group-label')) {
        finishGroup();
        currentLabel = child;
        currentButtons = [];
      } else if (child.matches?.('button[data-view]')) {
        currentButtons.push(child);
      }
    }
    finishGroup();

    const secondaryCount = buttons.filter(button => button.dataset.placeaiSecondary === 'true').length;
    let moreButton = nav.querySelector('.placeai-nav-more');
    if (secondaryCount && role !== 'platform_admin') {
      if (!moreButton) {
        moreButton = document.createElement('button');
        moreButton.type = 'button';
        moreButton.className = 'placeai-nav-more';
        moreButton.dataset.action = 'toggle-placeai-nav-more';
        nav.appendChild(moreButton);
      }
      const expanded = readNavPreference(role);
      nav.dataset.placeaiMoreOpen = expanded ? 'true' : 'false';
      setMoreButtonLabel(moreButton, expanded);
    } else {
      nav.dataset.placeaiMoreOpen = 'true';
      if (moreButton) moreButton.remove();
    }

    ensureRoleContext(role);
  }

  function toggleNavigationMore(button) {
    const nav = button?.closest?.('#app-nav');
    const role = normalizedRole();
    if (!nav || !role || role === 'platform_admin') return;
    const expanded = nav.dataset.placeaiMoreOpen !== 'true';
    nav.dataset.placeaiMoreOpen = expanded ? 'true' : 'false';
    writeNavPreference(role, expanded);
    setMoreButtonLabel(button, expanded);
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

  function decorateDashboard() {
    const content = document.querySelector('#app-content');
    if (!content) return;
    const toneFor = label => /due|rescue|requests|opportunit/i.test(label) ? 'amber'
      : /offers|hires|placement rate|applications|students/i.test(label) ? 'mint'
      : /interview|recruiter|gemini/i.test(label) ? 'violet' : 'blue';
    const metricIcon = label => {
      if (/profile|verified/i.test(label)) return '<circle cx="12" cy="8" r="3"/><path d="M5 21v-2a7 7 0 0 1 14 0v2"/>';
      if (/interview/i.test(label)) return '<rect x="3" y="5" width="13" height="14" rx="2"/><path d="m16 10 5-3v10l-5-3"/>';
      if (/offers|hires|placement rate/i.test(label)) return '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>';
      if (/jobs|opportunit|drives/i.test(label)) return '<rect x="3" y="7" width="18" height="14" rx="2"/><path d="M8 7V3h8v4M3 12h18"/>';
      if (/students|recruiter|organizations/i.test(label)) return '<circle cx="9" cy="8" r="3"/><path d="M3 21v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6m1 4a5 5 0 0 1 4 5"/>';
      return '<path d="M6 3h8l4 4v14H6zM14 3v5h4M9 12h6M9 16h4"/>';
    };
    for (const card of content.querySelectorAll('.metric-card')) {
      const label = card.querySelector('small')?.textContent || '';
      card.dataset.metricTone = toneFor(label);
      if (card.querySelector('.metric-symbol')) continue;
      const symbol = document.createElement('span');
      symbol.className = 'metric-symbol'; symbol.setAttribute('aria-hidden', 'true');
      symbol.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" focusable="false">' + metricIcon(label) + '</svg>';
      card.append(symbol);
    }
    if (!document.querySelector('#app-nav button.active[data-view="dashboard"]') || content.querySelector('.workspace-shortcuts')) return;
    const metrics = content.querySelector('.metric-grid');
    if (!metrics) return;
    const shortcuts = {
      student: ['learning-hub', 'mock-interview', 'roadmap', 'opportunities'],
      recruiter: ['jobs', 'candidates', 'interviews', 'offers'],
      institution_admin: ['students', 'drives', 'attention', 'reports'],
      platform_admin: ['organizations', 'registrations', 'leads', 'integrations']
    };
    const descriptions = {
      'learning-hub': 'Notes, diagrams and PDFs', 'mock-interview': 'Practice and get feedback',
      roadmap: 'Plan your next skills', opportunities: 'Explore campus openings',
      jobs: 'Manage open positions', candidates: 'Review your applicants',
      interviews: 'Coordinate interviews', offers: 'Track offer decisions',
      students: 'Manage student records', drives: 'Coordinate campus hiring',
      attention: 'Review pending actions', reports: 'View placement reports',
      organizations: 'Manage institutions', registrations: 'Review access requests',
      leads: 'Review enquiries', integrations: 'Check connected services'
    };
    const section = document.createElement('section');
    section.className = 'panel workspace-shortcuts'; section.setAttribute('aria-label', 'Quick actions');
    const title = document.createElement('h2'); title.textContent = 'Quick actions'; section.append(title);
    const grid = document.createElement('div'); grid.className = 'workspace-shortcut-grid';
    for (const view of shortcuts[normalizedRole()] || []) {
      const source = document.querySelector(`#app-nav button[data-view="${view}"]`);
      if (!source) continue;
      const button = document.createElement('button'); button.type = 'button'; button.className = 'workspace-shortcut'; button.dataset.view = view;
      const icon = source.querySelector('.nav-icon'); if (icon) { const copy = icon.cloneNode(true); copy.setAttribute('aria-hidden', 'true'); button.append(copy); }
      const label = document.createElement('span'); label.textContent = source.querySelector('.nav-label')?.textContent || source.textContent;
      label.className = 'workspace-shortcut-label';
      const copy = document.createElement('span'); copy.className = 'workspace-shortcut-copy';
      copy.append(label);
      const hint = document.createElement('small'); hint.className = 'workspace-shortcut-hint';
      hint.textContent = descriptions[view] || 'Open workspace'; copy.append(hint);
      button.append(copy); grid.append(button);
    }
    if (grid.childElementCount) { section.append(grid); metrics.after(section); }
  }

  function enhance(root = document) {
    decorateNavigation();
    decorateDashboard();
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
      const moreButton = event.target.closest?.('[data-action="toggle-placeai-nav-more"]');
      if (moreButton) {
        event.preventDefault();
        toggleNavigationMore(moreButton);
        return;
      }
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
