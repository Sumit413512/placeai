(() => {
  'use strict';
  if (window.__PLACEAI_HOMEPAGE_ENHANCEMENTS_LOADED__) return;
  window.__PLACEAI_HOMEPAGE_ENHANCEMENTS_LOADED__ = true;

  const linkedinIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4.98 3.5C4.98 4.88 3.86 6 2.48 6S0 4.88 0 3.5 1.12 1 2.48 1s2.5 1.12 2.5 2.5ZM.36 8h4.24v13H.36V8Zm6.86 0h4.07v1.78h.06c.57-1.08 1.95-2.22 4.02-2.22 4.3 0 5.09 2.83 5.09 6.51V21h-4.24v-6.15c0-1.47-.03-3.36-2.05-3.36-2.05 0-2.36 1.6-2.36 3.25V21H7.22V8Z"/></svg>';
  const mailIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 5h18a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Zm9 7.1L20.2 7H3.8L12 12.1Zm0 2.35L3 8.9V17h18V8.9l-9 5.55Z"/></svg>';
  const webIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm6.92 6h-3.04a15.3 15.3 0 0 0-1.3-3.18A8.05 8.05 0 0 1 18.92 8ZM12 4c.84 1.03 1.5 2.4 1.88 4h-3.76C10.5 6.4 11.16 5.03 12 4ZM4.26 14a8.21 8.21 0 0 1 0-4h3.4a17.2 17.2 0 0 0 0 4h-3.4Zm.82 2h3.04c.3 1.15.74 2.22 1.3 3.18A8.05 8.05 0 0 1 5.08 16Zm3.04-8H5.08a8.05 8.05 0 0 1 4.34-3.18A15.3 15.3 0 0 0 8.12 8ZM12 20c-.84-1.03-1.5-2.4-1.88-4h3.76c-.38 1.6-1.04 2.97-1.88 4Zm2.25-6h-4.5a14.92 14.92 0 0 1 0-4h4.5a14.92 14.92 0 0 1 0 4Zm.33 5.18c.56-.96 1-2.03 1.3-3.18h3.04a8.05 8.05 0 0 1-4.34 3.18ZM16.34 14a17.2 17.2 0 0 0 0-4h3.4a8.21 8.21 0 0 1 0 4h-3.4Z"/></svg>';

  function addPreparationNav() {
    const nav = document.querySelector('#marketing-site .marketing-nav');
    if (!nav || nav.querySelector('.placeai-nav-prep')) return;
    const link = document.createElement('a');
    link.href = '#preparation-lab';
    link.className = 'placeai-nav-prep';
    link.textContent = 'Preparation Lab';
    const security = [...nav.querySelectorAll('a')].find(item => item.getAttribute('href') === '#security');
    if (security) nav.insertBefore(link, security);
    else nav.appendChild(link);
  }

  function addPreparationLab() {
    if (document.querySelector('#preparation-lab')) return;
    const before = document.querySelector('#institutions');
    if (!before) return;
    const section = document.createElement('section');
    section.id = 'preparation-lab';
    section.className = 'section-shell placeai-prep-lab';
    section.innerHTML = `
      <div class="placeai-prep-shell">
        <div class="placeai-prep-intro">
          <div><span class="placeai-prep-kicker">Placement Preparation Lab</span><h2>Preparation, courses and tests aligned to each placement role.</h2></div>
          <p>PlaceAI extends placement operations with a role-aware preparation layer. Students practise for recruitment, recruiters standardise assessment, and placement teams build repeatable readiness programmes from one operating system.</p>
        </div>
        <div class="placeai-prep-modules" aria-label="Preparation Lab modules">
          <article class="placeai-prep-module"><span>01 · Assess</span><strong>Aptitude & reasoning tests</strong><small>Quantitative, logical and verbal assessment tracks with progressive difficulty.</small></article>
          <article class="placeai-prep-module"><span>02 · Build</span><strong>Technical & role courses</strong><small>Role-linked learning paths for coding, domain fundamentals and job-specific knowledge.</small></article>
          <article class="placeai-prep-module"><span>03 · Practise</span><strong>Communication & interview lab</strong><small>GD, HR, behavioural and technical interview preparation with structured practice.</small></article>
          <article class="placeai-prep-module"><span>04 · Improve</span><strong>Readiness diagnostics</strong><small>Practice history, weak-topic signals and targeted next-step recommendations.</small></article>
        </div>
        <div class="placeai-role-paths">
          <article class="placeai-role-card"><span class="role-tag">Student path</span><h3>Prepare for the actual placement process</h3><p>Move from fundamentals to company- and role-specific practice.</p><ul><li>Aptitude, coding and domain tests</li><li>Resume and interview preparation</li><li>Role-specific course tracks</li><li>Mock interview and readiness feedback</li></ul><button class="button button-primary" type="button" data-prep-role="student">Open Student preparation</button></article>
          <article class="placeai-role-card"><span class="role-tag">Recruiter path</span><h3>Run more consistent candidate assessment</h3><p>Use structured screening and evaluation patterns across hiring teams.</p><ul><li>Structured interview calibration</li><li>Screening-test design guidance</li><li>Role competency frameworks</li><li>Human-reviewed assessment workflow</li></ul><button class="button button-secondary" type="button" data-prep-role="recruiter">Open Recruiter workspace</button></article>
          <article class="placeai-role-card"><span class="role-tag">Placement team path</span><h3>Build a campus readiness programme</h3><p>Organise preparation around batches, drives and placement priorities.</p><ul><li>Batch-level readiness planning</li><li>Placement training programmes</li><li>Assessment scheduling and review</li><li>Drive-linked preparation strategy</li></ul><button class="button button-secondary" type="button" data-prep-role="institution_admin">Open Institution workspace</button></article>
        </div>
        <p class="placeai-prep-footnote">Placement Preparation Lab is designed as a controlled preparation and assessment layer. Final academic, hiring and placement decisions remain with authorised people and institutions.</p>
      </div>`;
    before.parentNode.insertBefore(section, before);
  }

  function addFooterLinks() {
    const footer = document.querySelector('#marketing-site .site-footer');
    if (!footer || footer.querySelector('.placeai-footer-connect')) return;
    footer.classList.add('placeai-footer-upgraded');
    const links = document.createElement('div');
    links.className = 'placeai-footer-connect';
    links.setAttribute('aria-label', 'PlaceAI contact links');
    links.innerHTML = `
      <a href="https://www.linkedin.com/company/placeai-in/" target="_blank" rel="noopener noreferrer" aria-label="PlaceAI on LinkedIn">${linkedinIcon}<span>LinkedIn</span></a>
      <a href="mailto:sumitjagtap@placeai.in" aria-label="Email PlaceAI">${mailIcon}<span>sumitjagtap@placeai.in</span></a>
      <a href="https://www.placeai.in/" aria-label="PlaceAI website">${webIcon}<span>www.placeai.in</span></a>`;
    footer.appendChild(links);
  }

  function openRoleLogin(role) {
    const trigger = document.querySelector('[data-open-auth="login"]');
    trigger?.click();
    window.setTimeout(() => {
      const roleButton = document.querySelector(`#login-view [data-access-role="${role}"]`);
      roleButton?.click();
      roleButton?.focus?.({preventScroll:true});
    }, 60);
  }

  function install() {
    addPreparationNav();
    addPreparationLab();
    addFooterLinks();
    document.addEventListener('click', event => {
      const roleButton = event.target.closest?.('[data-prep-role]');
      if (!roleButton) return;
      event.preventDefault();
      openRoleLogin(roleButton.dataset.prepRole);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, {once:true});
  else install();
})();
