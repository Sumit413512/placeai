(() => {
  'use strict';

  const productionBase = 'https://placeai-rxpp.vercel.app/workspace';
  const portalLabels = {
    student: 'Student workspace',
    recruiter: 'Employer / recruiter workspace',
    institution: 'Institution / TPO workspace',
    admin: 'Platform admin workspace'
  };

  const modal = document.querySelector('#portal-modal');
  const modalTitle = document.querySelector('#portal-modal-title');
  const modalCopy = document.querySelector('#portal-modal-copy');
  const menu = document.querySelector('#mobile-menu');
  const nav = document.querySelector('.nav');

  function normalizeIndianEnglishResumeCopy() {
    const replacements = new Map([
      ['Scattered résumés', 'Scattered resumes'],
      ['résumé parsing', 'resume parsing'],
      ['Résumé parsing', 'Resume parsing'],
    ]);
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      const parent = node.parentElement;
      if (!parent || ['SCRIPT', 'STYLE', 'TEXTAREA', 'INPUT'].includes(parent.tagName)) continue;
      let value = node.nodeValue || '';
      for (const [from, to] of replacements.entries()) value = value.replaceAll(from, to);
      node.nodeValue = value;
    }
  }

  function portalUrl(role) {
    const url = new URL(productionBase);
    url.searchParams.set('portal', role);
    return url.toString();
  }

  function openPortalModal(preferredRole = '') {
    if (!modal) return;
    if (preferredRole && portalLabels[preferredRole]) {
      modalTitle.textContent = portalLabels[preferredRole];
      modalCopy.textContent = 'Continue to the secure PlaceAI application. Your actual permissions are always determined by the authenticated account on the server.';
    } else {
      modalTitle.textContent = 'Choose your PlaceAI workspace';
      modalCopy.textContent = 'All role portals use the same secure application. Server-side authorization determines the workspace you receive after sign-in.';
    }
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    const preferred = preferredRole ? modal.querySelector(`[data-portal-link="${preferredRole}"]`) : modal.querySelector('[data-portal-link]');
    preferred?.focus();
  }

  function closePortalModal() {
    modal?.classList.add('hidden');
    document.body.style.overflow = '';
  }

  normalizeIndianEnglishResumeCopy();

  document.querySelectorAll('[data-portal-link]').forEach(link => {
    link.setAttribute('href', portalUrl(link.dataset.portalLink));
  });

  document.addEventListener('click', event => {
    const opener = event.target.closest('[data-open-portals]');
    if (opener) {
      event.preventDefault();
      openPortalModal(opener.dataset.openPortals || '');
      return;
    }
    if (event.target.closest('[data-close-portals]') || event.target === modal) closePortalModal();
  });

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && modal && !modal.classList.contains('hidden')) closePortalModal();
  });

  menu?.addEventListener('click', () => {
    const open = nav.classList.toggle('mobile-open');
    menu.setAttribute('aria-expanded', String(open));
    menu.textContent = open ? 'Close' : 'Menu';
  });

  document.querySelectorAll('.nav-links a').forEach(link => link.addEventListener('click', () => {
    nav?.classList.remove('mobile-open');
    if (menu) {
      menu.setAttribute('aria-expanded', 'false');
      menu.textContent = 'Menu';
    }
  }));

  const capabilityCount = document.querySelector('#capability-count');
  const capabilityItems = document.querySelectorAll('.capability');
  if (capabilityCount) capabilityCount.textContent = `${capabilityItems.length} controlled workflows and platform capabilities represented on this public surface.`;
})();
