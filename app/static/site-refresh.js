(() => {
  'use strict';
  if (window.__PLACEAI_SITE_REFRESH_LOADED__) return;
  window.__PLACEAI_SITE_REFRESH_LOADED__ = true;

  const LINKEDIN_URL = 'https://www.linkedin.com/company/placeai-in/';
  const EMAIL = 'sumitjagtap@placeai.in';
  const WEBSITE = 'https://www.placeai.in/';

  function ensureStyles() {
    if (document.querySelector('link[data-placeai-site-refresh]')) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = '/static/site-refresh.css';
    link.dataset.placeaiSiteRefresh = '';
    document.head.appendChild(link);
  }

  function updateBrandAssets() {
    document.querySelectorAll('.brand .brand-mark').forEach(mark => {
      mark.setAttribute('aria-hidden', 'true');
      mark.style.backgroundImage = "url('/static/placeai-logo.webp')";
    });
    const icon = document.querySelector('link[rel="icon"]');
    if (icon) {
      icon.href = '/static/placeai-logo.webp';
      icon.type = 'image/webp';
    }
  }

  function addPreparationNavigation() {
    const nav = document.querySelector('#marketing-site .marketing-nav');
    if (!nav || nav.querySelector('a[href="#preparation-lab"]')) return;
    const link = document.createElement('a');
    link.href = '#preparation-lab';
    link.textContent = 'Preparation Lab';
    const security = nav.querySelector('a[href="#security"]');
    nav.insertBefore(link, security || null);
  }

  function preparationSection() {
    const section = document.createElement('section');
    section.id = 'preparation-lab';
    section.className = 'prep-lab-section';
    section.innerHTML = `
      <div class="prep-lab-shell">
        <div class="prep-lab-intro">
          <div>
            <span class="prep-lab-kicker">Placement Preparation Lab</span>
            <h2>Preparation that adapts to each placement role.</h2>
          </div>
          <p>PlaceAI extends placement operations into structured preparation: courses, role-based tests, interview practice and readiness signals that institutions can connect to real placement workflows.</p>
        </div>
        <div class="prep-lab-grid">
          <article class="prep-role-card">
            <span class="prep-role-badge">STUDENT</span>
            <h3>Build job-ready skills and prove readiness.</h3>
            <p>A guided preparation workspace designed around the student's target roles and active placement opportunities.</p>
            <ul class="prep-feature-list">
              <li>Aptitude, reasoning and communication courses</li>
              <li>Role-specific technical learning tracks</li>
              <li>Timed tests and diagnostic assessments</li>
              <li>Mock interviews with structured feedback</li>
              <li>Readiness progress tied to placement activity</li>
            </ul>
            <div class="prep-card-action"><button class="button button-primary" data-open-auth="login" type="button">Student workspace</button></div>
          </article>
          <article class="prep-role-card">
            <span class="prep-role-badge">RECRUITER</span>
            <h3>Define the skills and assessment signals a role needs.</h3>
            <p>Hiring teams can align role expectations with campus preparation while keeping candidate access controlled.</p>
            <ul class="prep-feature-list">
              <li>Role competency and skill expectations</li>
              <li>Structured screening and assessment criteria</li>
              <li>Interview preparation topics for candidates</li>
              <li>Hiring-stage feedback signals</li>
              <li>Alignment with approved campus opportunities</li>
            </ul>
            <div class="prep-card-action"><button class="button button-secondary" data-open-auth="login" type="button">Recruiter workspace</button></div>
          </article>
          <article class="prep-role-card">
            <span class="prep-role-badge">INSTITUTION</span>
            <h3>Run preparation programs across cohorts.</h3>
            <p>Placement teams can organize readiness initiatives around batches, target roles and upcoming drives.</p>
            <ul class="prep-feature-list">
              <li>Cohort preparation plans and course pathways</li>
              <li>Campus test campaigns and readiness diagnostics</li>
              <li>Role- and company-focused preparation tracks</li>
              <li>Mock interview and participation monitoring</li>
              <li>Preparation insights for placement planning</li>
            </ul>
            <div class="prep-card-action"><button class="button button-secondary" data-open-access="request" type="button">Request institution access</button></div>
          </article>
        </div>
        <div class="prep-lab-note"><strong>Preparation Lab concept:</strong> learning and assessment features support placement readiness; actual hiring, eligibility and final decisions remain governed by authorized institution and recruiter workflows.</div>
      </div>`;
    return section;
  }

  function ensurePreparationLab() {
    const marketing = document.querySelector('#marketing-site main');
    if (!marketing || document.querySelector('#preparation-lab')) return;
    const security = marketing.querySelector('#security');
    marketing.insertBefore(preparationSection(), security || marketing.lastElementChild);
  }

  function linkedinIcon() {
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4.98 3.5A2.49 2.49 0 1 1 0 3.5a2.49 2.49 0 0 1 4.98 0ZM.43 8.02h4.1V21.2H.43V8.02Zm6.74 0h3.93v1.8h.06c.55-1.04 1.88-2.14 3.88-2.14 4.15 0 4.92 2.73 4.92 6.29v7.23h-4.1v-6.41c0-1.53-.03-3.5-2.13-3.5-2.14 0-2.47 1.67-2.47 3.39v6.52h-4.1V8.02Z"/></svg>';
  }

  function buildFooter() {
    const footer = document.createElement('footer');
    footer.className = 'placeai-footer';
    footer.innerHTML = `
      <div class="placeai-footer-shell">
        <div class="placeai-footer-main">
          <div class="placeai-footer-brand">
            <a class="brand brand-light" href="#top" aria-label="PlaceAI home"><span class="brand-mark" aria-hidden="true"></span><span>PlaceAI</span></a>
            <p>AI-assisted campus placement operations and preparation for institutions, recruiters and students.</p>
          </div>
          <div>
            <h3>Explore</h3>
            <div class="placeai-footer-links">
              <a href="#platform">Platform</a>
              <a href="#institutions">Institutions</a>
              <a href="#recruiters">Recruiters</a>
              <a href="#preparation-lab">Preparation Lab</a>
              <a href="#security">Security</a>
            </div>
          </div>
          <div>
            <h3>Contact PlaceAI</h3>
            <div class="placeai-footer-links">
              <a class="placeai-contact-link" href="mailto:${EMAIL}" aria-label="Email PlaceAI at ${EMAIL}"><span>✉</span><span>${EMAIL}</span></a>
              <a class="placeai-contact-link" href="${WEBSITE}" target="_self"><span>↗</span><span>www.placeai.in</span></a>
              <a class="placeai-social-button" href="${LINKEDIN_URL}" target="_blank" rel="noopener noreferrer" aria-label="Open PlaceAI on LinkedIn">${linkedinIcon()}<span>Follow PlaceAI on LinkedIn</span></a>
            </div>
          </div>
        </div>
        <div class="placeai-footer-bottom">
          <span>© 2026 PlaceAI · Privacy-first campus hiring and preparation.</span>
          <span><a href="/privacy">Privacy</a> · <a href="/terms">Terms</a> · <a href="/acceptable-use">Acceptable use</a></span>
        </div>
      </div>`;
    return footer;
  }

  function ensureFooter() {
    const marketing = document.querySelector('#marketing-site');
    if (!marketing) return;
    const existing = marketing.querySelector('footer');
    if (existing?.classList.contains('placeai-footer')) return;
    const replacement = buildFooter();
    if (existing) existing.replaceWith(replacement);
    else marketing.appendChild(replacement);
  }

  function install() {
    ensureStyles();
    updateBrandAssets();
    addPreparationNavigation();
    ensurePreparationLab();
    ensureFooter();
    const observer = new MutationObserver(() => updateBrandAssets());
    observer.observe(document.documentElement, {childList:true, subtree:true});
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, {once:true});
  else install();
})();
