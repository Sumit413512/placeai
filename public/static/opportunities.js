(() => {
  'use strict';
  let serial = 0;
  const banner = '/static/opportunity-workplace.webp';
  function demoCard() {
    return `<section class="panel opportunity-demo-card" aria-labelledby="opportunity-demo-title"><img src="/static/technova-demo.svg" alt="" width="64" height="64"><div><span class="section-kicker">Fictional demonstration</span><h2 id="opportunity-demo-title">Explore a TechNova opportunity</h2><p>Preview the role, registration and company layout. This is sample data, not a real vacancy.</p></div><button class="button button-secondary" data-action="preview-opportunity" type="button">View TechNova demo</button></section>`;
  }
  const website = value => {
    try { const url = new URL(value); return ['https:','http:'].includes(url.protocol) && !url.username && !url.password ? url.href : ''; }
    catch { return ''; }
  };
  function render(job, ctx) {
    const e = value => ctx.esc(String(value ?? ''));
    const paragraphs = value => String(value || '').split(/\n\s*\n/).filter(Boolean).map(text => `<p>${e(text).replace(/\n/g,'<br>')}</p>`).join('');
    const date = value => {
      if (!value || Number.isNaN(Date.parse(value))) return 'Not specified';
      const normalized = /(?:Z|[+-]\d\d:\d\d)$/.test(value) ? value : value + 'Z';
      return new Intl.DateTimeFormat('en-IN',{dateStyle:'medium',timeStyle:'short',timeZone:'Asia/Kolkata'}).format(new Date(normalized)) + ' IST';
    };
    const company = job.company || {}, site = website(company.website), eligibility = job.eligibility;
    const logo = job.logo_url === '/static/technova-demo.svg' ? `<img src="${job.logo_url}" alt="TechNova fictional demo logo" width="80" height="80">` : `<span aria-hidden="true">${e((job.company_name || 'Company').split(/\s+/).map(word=>word[0]).slice(0,2).join('').toUpperCase())}</span>`;
    const reasons = [...(eligibility && !eligibility.eligible ? eligibility.reasons || [] : []), ...(job.policy && !job.policy.allowed ? job.policy.reasons || [] : [])];
    const apply = job.is_preview ? `<button class="button button-primary button-full" data-action="demo-opportunity-info" type="button">Preview demo application</button><p class="opportunity-note">Demonstration only. No application is sent.</p>` : `<button class="button button-primary button-full" type="button" ${job.can_apply ? `data-action="apply-job" data-id="${e(job.id)}"` : 'disabled'}>${job.already_applied ? 'Applied' : job.can_apply ? (job.is_demo ? 'Register for demo' : 'Apply now') : 'Application unavailable'}</button>${reasons.length ? `<ul class="opportunity-note">${reasons.map(reason=>`<li>${e(reason)}</li>`).join('')}</ul>` : ''}`;
    return `<article class="opportunity-detail"><header class="opportunity-hero"><img src="${banner}" alt="" width="2172" height="724" fetchpriority="high"><button class="opportunity-back" type="button" data-action="opportunity-list"><span aria-hidden="true">←</span> Opportunity list</button><span class="opportunity-image-label">Illustrative workplace</span></header><div class="opportunity-detail-grid"><div class="opportunity-main"><section class="panel opportunity-identity"><div class="opportunity-heading"><div class="opportunity-logo">${logo}</div><div><div class="opportunity-badges">${job.is_demo ? '<span class="opportunity-demo-badge">Fictional demo</span>' : ''}<span>${job.visibility === 'campus' ? 'Campus opportunity' : 'Public opportunity'}</span>${eligibility ? `<span>${eligibility.eligible ? 'Meets drive criteria' : 'Check eligibility'}</span>` : ''}</div><h1 tabindex="-1">${e(job.title)}</h1><p class="opportunity-company-name">${e(job.company_name || 'Company name not provided')}</p></div></div><dl class="opportunity-facts"><div><dt>Employment type</dt><dd>${e(job.job_type || 'Not provided')}</dd></div><div><dt>Location</dt><dd>${e(job.location || 'Not provided')}</dd></div><div><dt>Compensation / CTC</dt><dd>${e(job.salary_range || 'Not provided')}</dd></div>${job.experience_required ? `<div><dt>Experience</dt><dd>${e(job.experience_required)}</dd></div>` : ''}</dl></section><div class="opportunity-mobile-apply">${apply}</div>${job.is_demo ? '<p class="opportunity-demo-notice" role="note">TechNova is a fictional PlaceAI demonstration. Company details, eligibility and compensation are illustrative, not an employment offer.</p>' : ''}<section class="panel opportunity-section"><h2>Role description</h2><div class="opportunity-description">${paragraphs(job.description || 'The recruiter has not provided a description.')}</div>${job.required_skills?.length ? `<h3>Required skills</h3><ul class="opportunity-skills-list">${job.required_skills.map(skill=>`<li>${e(skill)}</li>`).join('')}</ul>` : ''}${job.preferred_roles?.length ? `<h3>Preferred role interests</h3>${paragraphs(job.preferred_roles.join(', '))}` : ''}</section><section class="panel opportunity-section"><h2>Eligibility criteria</h2>${job.criteria?.length ? `<dl class="opportunity-criteria">${job.criteria.map(rule=>`<div><dt>${e(rule.label)}</dt><dd>${e(rule.value)}</dd></div>`).join('')}</dl>` : '<p>No additional academic criteria have been published. Your institution’s placement policies are checked when you apply.</p>'}${eligibility?.summary ? paragraphs(eligibility.summary) : ''}</section><section class="panel opportunity-section"><h2>Selection process</h2>${job.selection_process?.length ? `<ol class="opportunity-process">${job.selection_process.map(stage=>`<li>${e(stage)}</li>`).join('')}</ol>` : '<p>The recruiter or placement office has not published the selection stages yet.</p>'}</section></div><aside class="opportunity-sidebar" aria-label="Registration and organization details"><div class="panel opportunity-apply">${apply}</div><section class="panel opportunity-section"><h2>Registration schedule</h2>${job.is_preview ? '<p>Preview available anytime</p>' : `<dl class="opportunity-schedule"><div><dt>Published</dt><dd>${e(date(job.created_at))}</dd></div><div><dt>Closes</dt><dd>${e(date(job.deadline))}</dd></div></dl>`}${job.registration_notes ? `<details class="opportunity-registration"><summary>Registration details</summary>${paragraphs(job.registration_notes)}</details>` : ''}</section><section class="panel opportunity-section"><h2>About the organization</h2><h3>${e(company.name || job.company_name || 'Organization')}</h3>${company.about ? paragraphs(company.about) : ''}<dl class="opportunity-schedule">${company.industry ? `<div><dt>Industry</dt><dd>${e(company.industry)}</dd></div>` : ''}${company.size ? `<div><dt>Organization size</dt><dd>${e(company.size)}</dd></div>` : ''}${site ? `<div><dt>Website</dt><dd><a href="${e(site)}" target="_blank" rel="noopener noreferrer">${e(new URL(site).hostname)}<span class="sr-only"> (opens in new tab)</span></a></dd></div>` : ''}</dl></section><section class="panel opportunity-section"><h2>Contact</h2><p>${e(company.contact || 'Contact your placement office.')}</p></section></aside></div></article>`;
  }
  async function open(ctx, id, preview = false) {
    const version = ++serial;
    const panel = document.querySelector('#app-content');
    ctx.state.opportunityFilters = {search:document.querySelector('#job-search')?.value || '', type:document.querySelector('#job-type-filter')?.value || ''};
    ctx.setPage('Opportunity details','Student workspace'); ctx.setContextAction();
    panel.innerHTML = `<div data-opportunity-loading="${version}" class="panel" role="status">Loading opportunity…</div>`;
    const loading = panel.firstElementChild;
    try {
      const job = await ctx.api(preview ? '/students/opportunity-demo' : `/students/jobs/${encodeURIComponent(id)}`);
      if (version !== serial || ctx.state.view !== 'opportunities' || !panel.contains(loading)) return;
      panel.innerHTML = render(job, ctx);
      panel.querySelector('h1')?.focus({preventScroll:true});
      window.scrollTo({top:0,behavior:'instant'});
    } catch (error) {
      if (version !== serial || ctx.state.view !== 'opportunities' || !panel.contains(loading)) return;
      panel.innerHTML = `<section class="panel"><h1>Opportunity unavailable</h1><p role="alert">${ctx.esc(error.message)}</p><button class="button button-secondary" data-action="opportunity-list">Back to opportunities</button></section>`;
    }
  }
  window.PlaceAIOpportunities = Object.freeze({open, demoCard, cancel:()=>{serial += 1;}});
})();
