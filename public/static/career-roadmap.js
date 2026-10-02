(() => {
  'use strict';

  let workspace = null;

  const root = () => document.querySelector('#app-content');
  const splitList = value => String(value || '').split(',').map(item => item.trim()).filter(Boolean);

  function roadmapFailureMessage(error) {
    const code = String(error?.code || '');
    if ([
      'CURRENT_MARKET_PROVIDER_BUSY',
      'CURRENT_MARKET_PROVIDER_QUOTA',
      'CURRENT_MARKET_FALLBACK_BUSY',
      'CURRENT_MARKET_FALLBACK_QUOTA'
    ].includes(code) || Number(error?.status) === 429) {
      return 'Current-market research providers are temporarily at capacity. Please try again shortly.';
    }
    if (['CURRENT_MARKET_PROVIDER_TIMEOUT', 'CURRENT_MARKET_PROVIDER_NETWORK'].includes(code)) {
      return 'Current-market research could not connect reliably. Please try again in a moment.';
    }
    if ([
      'CURRENT_MARKET_PROVIDER_AUTH',
      'CURRENT_MARKET_PROVIDER_REJECTED',
      'CURRENT_MARKET_EMPTY_RESPONSE',
      'CURRENT_MARKET_SOURCES_MISSING',
      'CURRENT_MARKET_RESPONSE_INVALID',
      'CURRENT_MARKET_RESPONSE_INCOMPLETE',
      'CURRENT_MARKET_SEARCH_UNAVAILABLE',
      'CURRENT_MARKET_FALLBACK_UNAVAILABLE'
    ].includes(code)) {
      return 'Current-market research could not complete right now. Your roadmap was not generated from stale assumptions. Please try again shortly.';
    }
    if (code === 'DATABASE_UNAVAILABLE') {
      return 'PlaceAI could not save your roadmap right now. Please try again shortly.';
    }
    return error?.message || 'PlaceAI could not complete the roadmap request. Please try again.';
  }
  const safeUrl = value => {
    try {
      const url = new URL(String(value || ''));
      return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : '';
    } catch {
      return '';
    }
  };

  function listHtml(items, esc) {
    const values = Array.isArray(items) ? items.filter(Boolean) : [];
    if (!values.length) return '<p class="muted-copy">No additional items were returned for this section.</p>';
    return '<ul class="check-list">' + values.map(item => '<li>' + esc(item) + '</li>').join('') + '</ul>';
  }

  function sourceHtml(source, esc) {
    const url = safeUrl(source && source.url);
    if (!url) return '';
    const title = esc((source && source.title) || url);
    return '<a class="operation-card" href="' + esc(url) + '" target="_blank" rel="noopener noreferrer"><h3>' + title + '</h3><p>' + esc(url) + '</p></a>';
  }

  function phaseHtml(phase, esc) {
    const skills = Array.isArray(phase.skills) ? phase.skills : [];
    const projects = Array.isArray(phase.projects) ? phase.projects : [];
    return '<article class="panel">' +
      '<div class="panel-head"><div><span class="section-kicker">Phase ' + esc(phase.phase || '') + '</span><h2>' + esc(phase.name || 'Learning phase') + '</h2></div><span class="status-badge status-approved">' + esc(phase.days || 0) + ' days</span></div>' +
      '<div class="two-panel">' +
        '<div><h3>Outcomes</h3>' + listHtml(phase.outcomes, esc) + '<h3>Practice pattern</h3>' + listHtml(phase.practice, esc) + '</div>' +
        '<div><h3>Skills to learn</h3><div class="activity-list">' + (skills.length ? skills.map(skill =>
          '<div class="activity-item"><span class="activity-icon">SK</span><div><strong>' + esc(skill.name || '') + '</strong><small>' + esc(skill.level || 'working') + (skill.why ? ' · ' + esc(skill.why) : '') + '</small></div></div>'
        ).join('') : '<p class="muted-copy">No skills listed.</p>') + '</div></div>' +
      '</div>' +
      (projects.length ? '<div class="card-grid">' + projects.map(project =>
        '<article class="operation-card"><div class="operation-card-top"><span class="status-pill">PROJECT</span></div><h3>' + esc(project.title || 'Portfolio project') + '</h3><p>' + esc(project.scope || '') + '</p><strong>Deliverables</strong>' + listHtml(project.deliverables, esc) + (project.portfolio_proof ? '<div class="note-box"><strong>Portfolio proof</strong><p>' + esc(project.portfolio_proof) + '</p></div>' : '') + '</article>'
      ).join('') + '</div>' : '') +
      (phase.milestone ? '<div class="note-box"><strong>Completion milestone</strong><p>' + esc(phase.milestone) + '</p></div>' : '') +
    '</article>';
  }

  function builderForm(esc, latest) {
    const input = latest && latest.input ? latest.input : {};
    const join = values => Array.isArray(values) ? values.join(', ') : '';
    return '<section class="form-panel roadmap-builder">' +
      '<div class="panel-head"><div><span class="section-kicker">BUILD YOUR PLAN</span><h2>Create a roadmap around the role you actually want</h2><p>PlaceAI combines your current skills, available time and current market evidence into one practical learning path.</p></div></div>' +
      '<form id="career-roadmap-form" class="form-stack">' +
        '<div class="roadmap-form-section"><div class="roadmap-form-step"><span>1</span><div><strong>Choose your direction</strong><small>Tell us the role and domain you want to prepare for.</small></div></div>' +
          '<div class="form-two">' +
            '<label>Target roles<input name="target_roles" required maxlength="800" placeholder="Data Engineer, ML Engineer" value="' + esc(join(input.target_roles)) + '"></label>' +
            '<label>Fields or domains<input name="target_fields" maxlength="800" placeholder="AI, Data, Cloud" value="' + esc(join(input.target_fields)) + '"></label>' +
          '</div>' +
          '<label>What interests you most?<input name="interests" maxlength="1000" placeholder="Building data products, automation, analytics" value="' + esc(join(input.interests)) + '"></label>' +
        '</div>' +
        '<div class="roadmap-form-section"><div class="roadmap-form-step"><span>2</span><div><strong>Set your starting point</strong><small>We use this to avoid recommending things you already know.</small></div></div>' +
          '<label>Skills you already know<input name="current_skills" maxlength="2000" placeholder="Python, SQL, React" value="' + esc(join(input.current_skills)) + '"></label>' +
          '<div class="form-two">' +
            '<label>Current level<select name="experience_level"><option value="beginner">Beginner</option><option value="intermediate">Intermediate</option><option value="advanced">Advanced</option></select></label>' +
            '<label>Target job market<input name="market_region" required maxlength="120" value="' + esc(input.market_region || 'India') + '"></label>' +
          '</div>' +
        '</div>' +
        '<div class="roadmap-form-section"><div class="roadmap-form-step"><span>3</span><div><strong>Make the plan realistic</strong><small>Choose a pace that fits around classes, exams and placement preparation.</small></div></div>' +
          '<div class="form-three">' +
            '<label>Hours per week<input name="hours_per_week" type="number" min="1" max="80" value="' + esc(input.hours_per_week || 10) + '"></label>' +
            '<label>Preferred timeline <span class="optional">optional</span><input name="desired_timeline_days" type="number" min="14" max="730" value="' + esc(input.desired_timeline_days || '') + '" placeholder="120 days"></label>' +
            '<label>Learning style <span class="optional">optional</span><input name="learning_style" maxlength="500" value="' + esc(input.learning_style || '') + '" placeholder="Project-first, visual, structured"></label>' +
          '</div>' +
          '<label>Goals or constraints <span class="optional">optional</span><textarea name="goals_constraints" rows="3" maxlength="2000" placeholder="Placement deadline, college schedule, weak areas, internship target...">' + esc(input.goals_constraints || '') + '</textarea></label>' +
        '</div>' +
        '<div class="roadmap-builder-footer"><p><strong>Market-aware by default.</strong> Your roadmap uses fresh evidence for the selected region and can be regenerated whenever your target changes.</p>' +
        '<button class="button button-primary" type="submit">' + (latest ? 'Update my roadmap' : 'Build my roadmap') + '</button></div>' +
      '</form>' +
    '</section>';
  }

  function normalizeSkill(value) {
    return String(value || '').trim().toLowerCase().replace(/[^a-z0-9+#.]+/g, ' ');
  }

  function roadmapHtml(data, esc, fmtDate) {
    if (!data) return '';
    const roadmap = data.roadmap || {};
    const market = data.market_snapshot || {};
    const input = data.input || {};
    const pattern = roadmap.learning_pattern || {};
    const phases = Array.isArray(roadmap.phases) ? roadmap.phases : [];
    const sources = Array.isArray(data.sources) ? data.sources : [];
    const targets = Array.isArray(market.target_roles) && market.target_roles.length ? market.target_roles : (Array.isArray(input.target_roles) ? input.target_roles : []);
    const target = targets[0] || data.title || 'Your target role';
    const currentSkills = new Set((Array.isArray(input.current_skills) ? input.current_skills : []).map(normalizeSkill));
    const priorityGaps = (Array.isArray(market.in_demand_skills) ? market.in_demand_skills : [])
      .filter(skill => !currentSkills.has(normalizeSkill(skill)))
      .slice(0, 8);
    const firstPhase = phases[0] || {};
    const firstProject = Array.isArray(firstPhase.projects) ? firstPhase.projects[0] : null;
    const marketSignals = Array.isArray(market.demand_signals) ? market.demand_signals.slice(0, 5) : [];
    const marketNotes = Array.isArray(market.market_notes) ? market.market_notes.slice(0, 4) : [];

    return '<section class="roadmap-focus-panel">' +
      '<div class="roadmap-focus-copy"><span class="section-kicker">YOUR NEXT MOVE</span><h2>' + esc(firstPhase.name || 'Start with your first learning phase') + '</h2>' +
      '<p>' + esc(firstPhase.milestone || 'Follow the first phase, complete the practice tasks, and move forward only after you can demonstrate the milestone.') + '</p>' +
      '<div class="roadmap-focus-actions"><span><strong>' + esc(firstPhase.days || '—') + '</strong> days in this phase</span>' +
      (firstProject ? '<span><strong>1st project</strong> ' + esc(firstProject.title || 'Portfolio project') + '</span>' : '') + '</div></div>' +
      '<div class="roadmap-target-card"><small>Target</small><strong>' + esc(target) + '</strong><span>' + esc(market.region || data.market_region || 'India') + '</span></div>' +
    '</section>' +

    '<div class="metric-grid roadmap-summary-grid">' +
      '<article class="metric-card"><small>Total plan</small><strong>' + esc(data.estimated_days || '—') + '</strong><span>estimated days</span></article>' +
      '<article class="metric-card"><small>Weekly pace</small><strong>' + esc(data.weekly_hours || '—') + '</strong><span>hours per week</span></article>' +
      '<article class="metric-card"><small>Learning phases</small><strong>' + esc(phases.length) + '</strong><span>ordered milestones</span></article>' +
      '<article class="metric-card"><small>Updated for market</small><strong>' + esc(market.as_of || 'Current') + '</strong><span>' + esc(market.region || data.market_region || 'selected region') + '</span></article>' +
    '</div>' +

    '<div class="two-panel roadmap-priority-grid">' +
      '<section class="panel"><div class="panel-head"><div><span class="section-kicker">PRIORITY GAPS</span><h2>Skills to focus on next</h2><p>These market-relevant skills were not listed in your current skills.</p></div></div>' +
        (priorityGaps.length ? '<div class="roadmap-chip-list">' + priorityGaps.map(skill => '<span>' + esc(skill) + '</span>').join('') + '</div>' : '<div class="note-box"><strong>You already cover the main listed skills.</strong><p>Use the project milestones below to prove depth and production ability.</p></div>') +
      '</section>' +
      '<section class="panel"><div class="panel-head"><div><span class="section-kicker">MARKET SNAPSHOT</span><h2>What employers are signalling</h2><p>Use these signals to understand why the plan prioritises certain skills and projects.</p></div></div>' +
        listHtml(marketSignals, esc) +
        (marketNotes.length ? '<div class="roadmap-market-notes"><strong>Worth knowing</strong>' + listHtml(marketNotes, esc) + '</div>' : '') +
      '</section>' +
    '</div>' +

    '<section class="panel roadmap-learning-pattern"><div class="panel-head"><div><span class="section-kicker">HOW TO LEARN</span><h2>Your recommended learning rhythm</h2></div></div>' +
      '<div class="roadmap-rhythm-grid">' +
        '<div><small>Style</small><strong>' + esc(pattern.recommended_style || 'Structured project-based learning') + '</strong></div>' +
        '<div><small>Weekly cycle</small><span>' + esc(pattern.weekly_cycle || 'Learn, practise, build and review every week.') + '</span></div>' +
        '<div><small>Daily session</small><span>' + esc(pattern.daily_session || 'Use focused study blocks with hands-on practice.') + '</span></div>' +
        '<div><small>Revision</small><span>' + esc(pattern.revision_strategy || 'Revisit weak skills through spaced practice and project refinement.') + '</span></div>' +
      '</div>' +
    '</section>' +

    '<section class="roadmap-path-head"><div><span class="section-kicker">YOUR ROADMAP</span><h2>' + esc(data.title || 'Career Roadmap') + '</h2><p>Complete each phase in order. Every phase ends with something you can demonstrate, not just something you have watched or read.</p></div><span class="roadmap-generated">Updated ' + esc(fmtDate(data.created_at)) + '</span></section>' +
    '<div class="roadmap-phase-stack">' + phases.map(phase => phaseHtml(phase, esc)).join('') + '</div>' +

    '<div class="two-panel">' +
      '<section class="panel"><h2>Portfolio plan</h2>' + listHtml(roadmap.portfolio_plan, esc) + '<h2>Advanced next steps</h2>' + listHtml(roadmap.advanced_next_steps, esc) + '</section>' +
      '<section class="panel"><h2>Interview preparation</h2>' + listHtml(roadmap.interview_preparation, esc) + '<div class="note-box"><strong>Keep the roadmap adaptive</strong><p>' + esc(data.disclaimer || roadmap.disclaimer || '') + '</p></div></section>' +
    '</div>' +

    '<details class="roadmap-evidence panel"><summary><span><strong>Market evidence used for this roadmap</strong><small>View the current sources behind the recommendations</small></span><span aria-hidden="true">+</span></summary>' +
      '<div class="card-grid roadmap-source-grid">' + (sources.length ? sources.map(source => sourceHtml(source, esc)).join('') : '<p class="muted-copy">No source links are available for this saved roadmap.</p>') + '</div>' +
    '</details>';
  }

  async function render(context) {
    workspace = context;
    const { api, esc, setPage, setContextAction, pageHead, fmtDate } = context;
    setPage('AI Career Roadmap', 'Career intelligence');
    setContextAction();

    const status = await api('/roadmap/status');
    if (!status.allowed) {
      root().innerHTML = pageHead(
        'AI Career Roadmap',
        'A personalized, current-market learning plan built from your interests, target roles, existing skills and time commitment.'
      ) +
      '<div class="metric-grid">' +
        '<article class="metric-card"><small>Roadmap-only unlock</small><strong>₹' + esc(status.price_inr || 20) + '</strong><span>one-time feature access</span></article>' +
        '<article class="metric-card"><small>Free trial</small><strong>Not included</strong><span>The 3-day free trial cannot generate Career Roadmaps</span></article>' +
        '<article class="metric-card"><small>PlaceAI Premium</small><strong>Included</strong><span>Active paid individual plan</span></article>' +
        '<article class="metric-card"><small>University students</small><strong>Included</strong><span>Institution-sponsored access</span></article>' +
      '</div>' +
      '<section class="panel"><div class="panel-head"><div><h2>Unlock Career Roadmap</h2><p>' + esc(status.message || '') + '</p></div></div>' +
        '<div class="two-panel"><div class="ai-box"><div class="ai-box-head"><span>₹20 ONE-TIME</span></div><p>Unlock only Career Roadmap on this student account. This does not unlock other PlaceAI Premium features.</p>' +
        (status.checkout_enabled ? '<button class="button button-primary" data-action="roadmap-checkout">Unlock for ₹20</button>' : '<button class="button button-primary" disabled aria-disabled="true">₹20 checkout awaiting payment gateway activation</button>') +
        '</div><div class="ai-box"><div class="ai-box-head"><span>PLACEAI PREMIUM</span></div><p>Career Roadmap is included with an active PlaceAI Premium student plan.</p><button class="button button-secondary" data-view="billing">View plan & billing</button></div></div>' +
        '<div class="note-box"><strong>Choose the access that fits you.</strong><p>University-sponsored and paid student access include Career Roadmap. The free trial does not include roadmap generation.</p></div>' +
      '</section>';
      return;
    }

    let latest = null;
    if (status.latest_available) latest = await api('/roadmap/latest');
    const page = pageHead(
      'AI Career Roadmap',
      'Turn your target role into a clear sequence of skills, projects and milestones based on your profile and the current market.'
    );
    const editor = builderForm(esc, latest);

    if (latest) {
      root().innerHTML = page +
        '<section class="roadmap-plan-toolbar" aria-label="Saved roadmap actions">' +
          '<div class="roadmap-plan-toolbar-copy"><span class="section-kicker">YOUR SAVED PLAN</span><strong>Continue from the next move below</strong><small>Adjust the plan when your target role, skills, available time or market changes. Last updated ' + esc(fmtDate(latest.created_at)) + '.</small></div>' +
          '<div class="roadmap-plan-toolbar-actions"><button class="button button-secondary" type="button" data-action="roadmap-adjust">Adjust roadmap</button><button class="button button-secondary" type="button" data-action="roadmap-print">Print / save PDF</button></div>' +
        '</section>' +
        roadmapHtml(latest, esc, fmtDate) +
        '<details class="roadmap-adjust-panel panel"><summary><span><strong>Adjust roadmap inputs</strong><small>Change your target, starting point or weekly pace, then rebuild with current market evidence.</small></span><span aria-hidden="true">+</span></summary><div class="roadmap-adjust-body">' + editor + '</div></details>';
    } else {
      root().innerHTML = page + editor;
    }

    const level = root().querySelector('#career-roadmap-form select[name="experience_level"]');
    if (level && latest && latest.input && latest.input.experience_level) level.value = latest.input.experience_level;
  }

  function register() {
    if (!window.PlaceAIStudentViews || typeof window.PlaceAIStudentViews.register !== 'function') return false;
    window.PlaceAIStudentViews.register('roadmap', render);
    return true;
  }

  if (!register()) {
    window.addEventListener('placeai:student-views-ready', register, { once: true });
  }

  document.addEventListener('submit', async event => {
    const form = event.target;
    if (!form || form.id !== 'career-roadmap-form') return;
    event.preventDefault();
    event.stopImmediatePropagation();
    if (!workspace) return;

    const { api, toast, navigate } = workspace;
    const data = Object.fromEntries(new FormData(form).entries());
    const submit = form.querySelector('button[type="submit"]');
    const original = submit ? submit.textContent : '';
    if (submit) {
      submit.disabled = true;
      submit.textContent = 'Researching current market and building roadmap…';
    }

    const payload = {
      interests: splitList(data.interests),
      target_roles: splitList(data.target_roles),
      target_fields: splitList(data.target_fields),
      current_skills: splitList(data.current_skills),
      experience_level: data.experience_level || 'beginner',
      market_region: data.market_region || 'India',
      hours_per_week: Number(data.hours_per_week || 10),
      desired_timeline_days: data.desired_timeline_days ? Number(data.desired_timeline_days) : null,
      learning_style: data.learning_style || null,
      goals_constraints: data.goals_constraints || null
    };

    try {
      await api('/roadmap/generate', { method: 'POST', body: JSON.stringify(payload) });
      toast('Career roadmap created', 'Your current-market roadmap is ready and saved to your account.');
      await navigate('roadmap');
    } catch (error) {
      toast('Roadmap generation failed', roadmapFailureMessage(error), 'error');
      if (submit) {
        submit.disabled = false;
        submit.textContent = original;
      }
    }
  });

  document.addEventListener('click', async event => {
    const actionButton = event.target.closest?.('[data-action]');
    const action = actionButton?.dataset.action || '';
    if (!action || !workspace) return;

    if (action === 'roadmap-adjust') {
      event.preventDefault();
      const panel = root()?.querySelector('.roadmap-adjust-panel');
      if (!panel) return;
      panel.open = true;
      requestAnimationFrame(() => {
        panel.scrollIntoView({ behavior:'smooth', block:'start' });
        panel.querySelector('input[name="target_roles"]')?.focus({ preventScroll:true });
      });
      return;
    }

    if (action === 'roadmap-print') {
      event.preventDefault();
      window.print();
      return;
    }

    if (action !== 'roadmap-checkout') return;
    try {
      await workspace.api('/billing/roadmap-checkout', { method: 'POST' });
    } catch (error) {
      workspace.toast('Roadmap checkout unavailable', error.message, 'error');
    }
  });
})();
