(() => {
  'use strict';

  let workspace = null;

  const root = () => document.querySelector('#app-content');
  const splitList = value => String(value || '').split(',').map(item => item.trim()).filter(Boolean);
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
    return '<section class="form-panel">' +
      '<div class="panel-head"><div><h2>Build your market-aligned roadmap</h2><p>Tell PlaceAI what you want to become. Current market research is performed when you generate the roadmap.</p></div></div>' +
      '<form id="career-roadmap-form" class="form-stack">' +
        '<div class="form-two">' +
          '<label>Career roles you are interested in<input name="target_roles" required maxlength="800" placeholder="Data Engineer, ML Engineer" value="' + esc(join(input.target_roles)) + '"></label>' +
          '<label>Fields / domains<input name="target_fields" maxlength="800" placeholder="AI, Data, Cloud" value="' + esc(join(input.target_fields)) + '"></label>' +
        '</div>' +
        '<label>Your interests<input name="interests" maxlength="1000" placeholder="Building data products, automation, analytics" value="' + esc(join(input.interests)) + '"></label>' +
        '<label>Skills you already know<input name="current_skills" maxlength="2000" placeholder="Python, SQL, React" value="' + esc(join(input.current_skills)) + '"></label>' +
        '<div class="form-three">' +
          '<label>Current level<select name="experience_level"><option value="beginner">Beginner</option><option value="intermediate">Intermediate</option><option value="advanced">Advanced</option></select></label>' +
          '<label>Market region<input name="market_region" required maxlength="120" value="' + esc(input.market_region || 'India') + '"></label>' +
          '<label>Hours per week<input name="hours_per_week" type="number" min="1" max="80" value="' + esc(input.hours_per_week || 10) + '"></label>' +
        '</div>' +
        '<div class="form-two">' +
          '<label>Preferred timeline in days <span class="optional">optional</span><input name="desired_timeline_days" type="number" min="14" max="730" value="' + esc(input.desired_timeline_days || '') + '" placeholder="120"></label>' +
          '<label>Learning style <span class="optional">optional</span><input name="learning_style" maxlength="500" value="' + esc(input.learning_style || '') + '" placeholder="Project-first, visual, structured"></label>' +
        '</div>' +
        '<label>Goals or constraints <span class="optional">optional</span><textarea name="goals_constraints" rows="3" maxlength="2000" placeholder="College schedule, placement deadline, weak areas...">' + esc(input.goals_constraints || '') + '</textarea></label>' +
        '<div class="note-box"><strong>Current-market mode</strong><p>PlaceAI will research the live market for your selected region and cite the sources used. If current research is unavailable, it will not silently generate a stale-market roadmap.</p></div>' +
        '<button class="button button-primary button-full" type="submit">' + (latest ? 'Regenerate with current market' : 'Generate my career roadmap') + '</button>' +
      '</form>' +
    '</section>';
  }

  function roadmapHtml(data, esc, fmtDate) {
    if (!data) return '';
    const roadmap = data.roadmap || {};
    const market = data.market_snapshot || {};
    const pattern = roadmap.learning_pattern || {};
    const phases = Array.isArray(roadmap.phases) ? roadmap.phases : [];
    const sources = Array.isArray(data.sources) ? data.sources : [];
    return '<section class="panel">' +
      '<div class="panel-head"><div><span class="section-kicker">PERSONALIZED ROADMAP</span><h2>' + esc(data.title || 'Career Roadmap') + '</h2><p>Generated ' + esc(fmtDate(data.created_at)) + ' · Market snapshot ' + esc(market.as_of || '') + '</p></div></div>' +
      '<div class="metric-grid">' +
        '<article class="metric-card"><small>Estimated duration</small><strong>' + esc(data.estimated_days || '—') + '</strong><span>days</span></article>' +
        '<article class="metric-card"><small>Weekly commitment</small><strong>' + esc(data.weekly_hours || '—') + '</strong><span>hours/week</span></article>' +
        '<article class="metric-card"><small>Market</small><strong>' + esc(data.market_region || market.region || 'India') + '</strong><span>current research region</span></article>' +
        '<article class="metric-card"><small>Evidence</small><strong>' + esc(sources.length) + '</strong><span>current web sources</span></article>' +
      '</div>' +
      '<div class="two-panel">' +
        '<div class="ai-box"><div class="ai-box-head"><span>MARKET SIGNALS</span></div>' + listHtml(market.demand_signals, esc) + '</div>' +
        '<div class="ai-box"><div class="ai-box-head"><span>IN-DEMAND SKILLS</span></div>' + listHtml(market.in_demand_skills, esc) + '</div>' +
      '</div>' +
      '<div class="two-panel">' +
        '<div class="ai-box"><div class="ai-box-head"><span>TOOLS & TECHNOLOGIES</span></div>' + listHtml(market.tools_and_technologies, esc) + '</div>' +
        '<div class="ai-box"><div class="ai-box-head"><span>ENTRY-LEVEL EXPECTATIONS</span></div>' + listHtml(market.entry_level_expectations, esc) + '</div>' +
      '</div>' +
      '<div class="ai-box"><div class="ai-box-head"><span>LEARNING PATTERN</span></div>' +
        '<p><strong>Recommended style:</strong> ' + esc(pattern.recommended_style || 'Structured project-based learning') + '</p>' +
        '<p><strong>Weekly cycle:</strong> ' + esc(pattern.weekly_cycle || '—') + '</p>' +
        '<p><strong>Daily session:</strong> ' + esc(pattern.daily_session || '—') + '</p>' +
        '<p><strong>Revision:</strong> ' + esc(pattern.revision_strategy || '—') + '</p>' +
      '</div>' +
    '</section>' +
    phases.map(phase => phaseHtml(phase, esc)).join('') +
    '<div class="two-panel">' +
      '<section class="panel"><h2>Advanced next steps</h2>' + listHtml(roadmap.advanced_next_steps, esc) + '<h2>Portfolio plan</h2>' + listHtml(roadmap.portfolio_plan, esc) + '</section>' +
      '<section class="panel"><h2>Interview preparation</h2>' + listHtml(roadmap.interview_preparation, esc) + '<div class="note-box"><strong>Guidance, not a guarantee</strong><p>' + esc(data.disclaimer || roadmap.disclaimer || '') + '</p></div></section>' +
    '</div>' +
    '<section class="panel"><div class="panel-head"><div><h2>Current-market sources</h2><p>Open these sources to validate the market evidence used for this roadmap.</p></div></div><div class="card-grid">' + sources.map(source => sourceHtml(source, esc)).join('') + '</div></section>';
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
        '<div class="note-box"><strong>Access is enforced on the server.</strong><p>Changing browser code cannot bypass the free-trial restriction.</p></div>' +
      '</section>';
      return;
    }

    let latest = null;
    if (status.latest_available) latest = await api('/roadmap/latest');
    root().innerHTML = pageHead(
      'AI Career Roadmap',
      'Choose a destination. PlaceAI researches the current market, compares it with your profile, and builds a phased skills-and-project plan.'
    ) +
    '<div class="metric-grid">' +
      '<article class="metric-card"><small>Access</small><strong>' + esc(String(status.access_source || '').replaceAll('_', ' ')) + '</strong><span>Roadmap generation unlocked</span></article>' +
      '<article class="metric-card"><small>Market research</small><strong>Live</strong><span>Fresh web research is required per generation</span></article>' +
      '<article class="metric-card"><small>Roadmap history</small><strong>' + (status.latest_available ? 'Saved' : 'New') + '</strong><span>Your latest roadmap is stored securely</span></article>' +
      '<article class="metric-card"><small>Price for your access</small><strong>' + (status.access_source === 'one_time_purchase' ? '₹20 paid' : 'Included') + '</strong><span>' + (status.access_source === 'institution' ? 'Institution-sponsored' : status.access_source === 'premium' ? 'Premium plan' : 'Roadmap-only unlock') + '</span></article>' +
    '</div>' +
    builderForm(esc, latest) +
    roadmapHtml(latest, esc, fmtDate);

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
      toast('Roadmap generation failed', error.message, 'error');
      if (submit) {
        submit.disabled = false;
        submit.textContent = original;
      }
    }
  });

  document.addEventListener('click', async event => {
    const button = event.target.closest('[data-action="roadmap-checkout"]');
    if (!button || !workspace) return;
    try {
      await workspace.api('/billing/roadmap-checkout', { method: 'POST' });
    } catch (error) {
      workspace.toast('Roadmap checkout unavailable', error.message, 'error');
    }
  });
})();
