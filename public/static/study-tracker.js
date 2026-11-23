/* Private, resource-linked study goals. No AI calls or account data in public assets. */
(() => {
  'use strict';
  let ctx, catalog, overview, epoch=0, pending=null;
  const quotes=[
    'A small concept understood well is useful progress.',
    'Return to one difficult idea. Clarity grows through practice.',
    'Build a rhythm you can sustain, one focused session at a time.',
    'You do not need a perfect day to take the next useful step.',
    'Use an example, explain it aloud, then try it yourself.',
    'Consistency is a practice. Start again whenever you need to.'
  ];
  let quoteIndex=0;
  try { quoteIndex=(Number(localStorage.getItem('placeai.study.welcome.v2'))||0)%quotes.length; } catch {}
  window.PlaceAIStudy={selectResource(kind,id){pending={kind,id};}};
  const e=v=>ctx.esc(String(v??''));
  const active=v=>v===epoch&&ctx?.state.view==='study-tracker'&&document.querySelector('#study-tracker');
  const notebookIllustration='<svg class="study-illustration" viewBox="0 0 200 140" role="img" aria-label="Illustration of a friendly study notebook and a growing path"><ellipse cx="100" cy="124" rx="70" ry="8" fill="#e1d7e6"/><path d="M26 116h145" stroke="#b49263" stroke-width="3"/><g class="study-book"><rect x="55" y="21" width="82" height="98" rx="12" fill="#fdfaf5" stroke="#624563" stroke-width="3"/><path d="M70 24v91M57 43h10M57 60h10M57 77h10M57 94h10" stroke="#b49263" stroke-width="3"/><circle cx="91" cy="64" r="3" fill="#342b38"/><circle cx="116" cy="64" r="3" fill="#342b38"/><path d="M94 81q10 9 20 0" fill="none" stroke="#624563" stroke-width="3" stroke-linecap="round"/><path d="m82 105 8-5m31 5-8-5" stroke="#624563" stroke-width="3"/></g><path d="M151 106V65m0 18q-20-2-15-18 17 1 15 18m0-6q19-3 18-17-19 0-18 17" stroke="#9a7149" fill="#e4cc9c" stroke-width="2"/><path d="m33 39 3 6 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1z" fill="#c4a169"/></svg>';
  const welcomeArt = [notebookIllustration,
    '<svg class="study-illustration" viewBox="0 0 200 140" role="img" aria-label="Illustration of a study desk and an open book"><rect x="19" y="114" width="166" height="7" rx="3" fill="#896145"/><path d="M35 106V55q32-14 65 2 33-16 65-2v51q-32-13-65 0-33-13-65 0Z" fill="#fffaf1" stroke="#694c69" stroke-width="3"/><path d="M100 57v49M47 70h34m-34 12h34m38-12h31m-31 12h31" stroke="#b69b78" stroke-width="3"/><path d="M145 40v-9h25v39m-12-39-17 11h34Z" fill="#e2bba9" stroke="#896145" stroke-width="3"/><circle cx="40" cy="30" r="12" fill="#e9d9ac"/></svg>',
    '<svg class="study-illustration" viewBox="0 0 200 140" role="img" aria-label="Illustration of learning milestones on a growing path"><path d="M25 116h150M38 113V88h32v25m10 0V65h32v48m10 0V39h32v74" fill="#e9d9ac" stroke="#896145" stroke-width="3"/><path d="m39 64 44-25 39 9 38-28m-17 0h17v17" fill="none" stroke="#694c69" stroke-width="4" stroke-linecap="round"/><circle cx="38" cy="64" r="6" fill="#c58774"/><circle cx="83" cy="39" r="6" fill="#c58774"/><circle cx="122" cy="48" r="6" fill="#c58774"/></svg>'
  ];
  const options=(items,selected='')=>items.map(x=>`<option value="${e(x.id||x.key)}" ${(x.id||x.key)===selected?'selected':''}>${e(x.title)}</option>`).join('');
  function goalForm(plan){return `<details class="study-add-goal"><summary>Add a goal</summary><form data-study-goal-form data-plan="${e(plan.id)}"><label>Activity<select name="kind"><option value="notes">Read notes</option><option value="video">Complete a video course</option><option value="mock">Mock interview practice</option>${plan.roadmap_id?'<option value="milestone">Roadmap outcome</option>':''}<option value="task">My own study task</option></select></label><label data-study-resource-label>Notebook<select name="resource_id">${options(catalog.notes)}</select></label><label data-study-title-label hidden>Task description<input name="title" maxlength="240"></label><label data-study-target-label hidden>Target sessions or units<input name="target" type="number" min="1" max="1000" value="15" required></label><button class="button button-primary" type="submit">Add goal</button><p role="status"></p></form></details>`;}
  function goalCard(goal){return `<article class="study-goal" data-goal="${e(goal.id)}"><div><small>${e({notes:'Notes',video:'Video + quiz',mock:'Completed interviews',milestone:'Roadmap outcome',task:'Self-reported task'}[goal.kind])}</small><h3>${e(goal.title)}</h3><p>${goal.unavailable?'Resource unavailable. Restore deleted notes to continue.':`${goal.completed} of ${goal.target} ${goal.kind==='notes'?'sections':goal.kind==='mock'?'sessions':'units'} complete`}</p>${goal.kind==='notes'&&goal.resume?.section?`<p>Last opened: section ${e(goal.resume.section)}</p>`:''}<progress max="100" value="${goal.percent}" aria-label="${e(goal.title)} completion"></progress><span>${goal.percent}% complete</span></div><div class="study-goal-actions">${goal.resume&&!goal.unavailable?`<button class="button button-secondary" data-study-resume="${e(goal.id)}">${goal.kind==='mock'?'Practise':'Continue'}</button>`:''}${goal.kind==='notes'&&!goal.unavailable?`<button class="button button-secondary" data-study-offline="${e(goal.resource_id)}">Update PDF reading</button>`:''}${goal.manual?`<form data-study-manual-form data-goal="${e(goal.id)}"><label>Completed units<input name="completed" type="number" min="0" max="${goal.target}" value="${goal.completed}" required></label><button class="button button-secondary" type="submit">Save</button></form>`:''}<button class="study-text-button" data-study-remove="${e(goal.id)}">Remove goal</button></div></article>`;}
  const metrics = {
    minutes: { label:'Study time', unit:'min', singular:'min', limit:3360, view:'learning-hub', action:'Open Learning Hub' },
    notes: { label:'Note sections', unit:'sections', singular:'section', limit:500, view:'learning-hub', action:'Open notes' },
    lessons: { label:'Video lessons + quizzes', unit:'lessons', singular:'lesson', limit:500, view:'learning-hub', action:'Open video learning' },
    mocks: { label:'Mock interviews', unit:'interviews', singular:'interview', limit:100, view:'mock-interview', action:'Open interview coach' }
  };

  function activityPeriod(label, entries) {
    const planned = Object.values(entries).filter(item => item.target);
    const allMet = planned.length && planned.every(item => !item.left);
    return `<section class="study-period" aria-label="${label}">
      <div class="study-period-heading"><h3>${label}</h3>${allMet ? '<strong>All targets met</strong>' : ''}</div>
      <ul>${Object.entries(entries).map(([key, item]) => {
        const metric = metrics[key];
        const unit = count => count === 1 ? metric.singular : metric.unit;
        return `<li>
          <div class="study-progress-label"><span>${metric.label}</span><strong>${item.done}${item.target ? ' / ' + item.target : ''} ${unit(item.target || item.done)}</strong></div>
          ${item.target ? `<progress aria-label="${label}: ${metric.label}" value="${Math.min(item.done,item.target)}" max="${item.target}"></progress>
          <span class="study-target-detail">${item.left ? item.left + ' ' + unit(item.left) + ' left' : 'Target met'}${item.left ? ` · <button type="button" class="study-text-button" data-study-open="${key}">${metric.action}</button>` : ''}</span>` : ''}
        </li>`;
      }).join('')}</ul>
    </section>`;
  }

  function nextTarget(targets) {
    for (const [period, label] of [['daily','today'], ['weekly','this week']]) {
      const key = ['notes','lessons','mocks','minutes'].find(metric => targets[period][metric].left);
      if (!key) continue;
      const left = targets[period][key].left;
      const actions = {
        notes: 'Read one more note section',
        lessons: 'Finish one video lesson and its quiz',
        mocks: 'Complete one practice interview',
        minutes: `Study for ${Math.min(left, 15)} more minutes`
      };
      return `<div class="study-next-target"><p><strong>Next ${label}</strong><span>${actions[key]}</span></p>
        <button type="button" class="button button-secondary" data-study-open="${key}">${metrics[key].action}</button></div>`;
    }
    return '';
  }

  function targetPanel(targets) {
    const hasTargets = ['daily','weekly'].some(period => Object.values(targets[period]).some(item => item.target));
    const dateLabel = value => new Intl.DateTimeFormat(undefined,{day:'numeric',month:'short',timeZone:'UTC'}).format(new Date(value));
    return `<section class="panel study-targets" aria-labelledby="study-target-heading">
      <div class="panel-head"><div><h2 id="study-target-heading">Your study targets</h2>
        <p>${dateLabel(targets.day)} · Week of ${dateLabel(targets.week_start)}–${dateLabel(targets.week_end)} · ${e(overview.timezone)}</p></div></div>
      ${nextTarget(targets)}
      <div class="study-target-periods">${activityPeriod('Today', targets.daily)}${activityPeriod('This week', targets.weekly)}</div>
      <details class="study-target-settings" ${hasTargets ? '' : 'open'}>
        <summary>${hasTargets ? 'Edit daily and weekly targets' : 'Set daily and weekly targets'}</summary>
        <form id="study-target-form">
          <p>Targets repeat each day or Monday–Sunday week. Leave a target blank to skip it.</p>
          <div class="study-target-inputs">${['daily','weekly'].map(period => `<fieldset><legend>${period === 'daily' ? 'Daily targets' : 'Weekly targets'}</legend>
            ${Object.entries(metrics).map(([key, metric]) => `<label>${metric.label}${key === 'minutes' ? ' (minutes)' : ''}
              <input name="${period}-${key}" type="number" inputmode="numeric" min="0" max="${metric.limit}" value="${targets[period][key].target || ''}">
            </label>`).join('')}
          </fieldset>`).join('')}</div>
          <label class="study-check"><input name="reminders" type="checkbox" ${targets.reminders ? 'checked' : ''}> Send an evening recap to Notifications</label>
          <p>See what you finished and what is left at about 8:00 p.m. in your study time zone.</p>
          <button type="submit" class="button button-primary">Save study targets</button>
          <p role="status"></p>
        </form>
      </details>
    </section>`;
  }

  function renderContent(){
    const p=overview.plans;
    const pendingRoad=pending?.kind==='roadmap'?catalog.roadmaps.find(r=>r.id===pending.id):null;
    const todayTasks=p.filter(x=>!x.paused).flatMap(x=>(x.today_steps||[]).map(step=>({...x.goals.find(g=>g.id===step.goal_id),plan:x.title,step}))).slice(0,3);
    document.querySelector('#study-tracker').innerHTML=`<section class="study-welcome" data-welcome-theme="${quoteIndex % welcomeArt.length}"><div><span class="section-kicker">Your learning, connected</span><h2>Make the next session count.</h2><p id="study-reminder">${e(quotes[quoteIndex])}</p></div>${welcomeArt[quoteIndex % welcomeArt.length]}</section>${targetPanel(overview.targets)}<div class="study-metrics"><article><span>Today</span><strong>${overview.today_minutes} min</strong><small>Recorded study time</small></article><article><span>Daily average</span><strong>${overview.average_daily_minutes} min</strong><small>Across the last 7 days</small></article><article><span>Study rhythm</span><strong>${overview.streak_days} ${overview.streak_days===1?'day':'days'}</strong><small>Current activity streak</small></article><article><span>Interview practice</span><strong>${overview.completed_mock_sessions}</strong><small>Completed assessments</small></article></div><section class="panel"><div class="panel-head"><h2>Your next steps</h2><button class="button button-secondary" data-study-refresh>Refresh progress</button></div>${todayTasks.length?`<div class="study-next">${todayTasks.map(g=>`<article><small>${e(g.plan)}</small><h3>${e(g.title)}</h3><p>Today: ${g.step.units} ${g.kind==='notes'?'sections':g.kind==='mock'?'sessions':'units'} · approximately ${g.step.minutes} minutes</p>${g.resume?`<button class="button button-primary" data-study-resume="${e(g.id)}">Start next session</button>`:'<p>Update this task in your plan below.</p>'}</article>`).join('')}</div>`:`<p>${!p.length?'Create a plan and add the notes, courses or practice goals you want to follow.':p.every(plan=>plan.paused)?'Your plans are paused. Resume a plan when you are ready.':p.some(plan=>!plan.goals.length)?'Add a goal to your plan to choose your next session.':'Your current goals are complete. Choose another goal when you are ready.'}</p>`}</section><details class="panel study-create" ${!p.length||pendingRoad?'open':''}><summary>Start a study plan</summary><form id="study-plan-form"><label>Plan name<input name="title" required minlength="3" maxlength="180" value="${e(pendingRoad?.title||'')}" placeholder="For example, Data engineering preparation"></label><label>Link a saved roadmap (optional)<select name="roadmap_id"><option value="">My own plan</option>${options(catalog.roadmaps,pendingRoad?.id)}</select></label><div class="study-form-grid"><label>Daily study target (minutes)<input name="daily_minutes" type="number" min="5" max="480" required value="${Math.min(480,Math.max(5,Math.round((pendingRoad?.weekly_hours||5)*60/7)))}"></label><label>Target date (optional)<input name="target_date" type="date"></label></div><button class="button button-primary" type="submit">Create study plan</button><p role="status"></p></form></details><section aria-label="Your study plans" class="study-plans">${p.map(plan=>`<article class="panel study-plan" data-plan="${e(plan.id)}"><div class="panel-head"><div><small>${plan.roadmap_id?'Linked to your career roadmap':'Personal study plan'}${plan.paused?' · Paused':''}</small><h2>${e(plan.title)}</h2></div><strong>${plan.percent}%</strong></div><progress max="100" value="${plan.percent}" aria-label="${e(plan.title)} overall completion"></progress><p class="study-basis">${e(plan.progress_basis)}</p>${plan.goals.length?`<p>${plan.estimated_days_remaining} estimated study days remaining at ${plan.daily_minutes} minutes a day.${plan.target_date?` Target: ${e(plan.target_date)}.`:''} Estimated finish: ${e(plan.estimated_finish)}.</p>${plan.required_daily_minutes>plan.daily_minutes?`<p class="study-schedule-note">To meet that date, plan for approximately ${plan.required_daily_minutes} minutes a day or adjust your target.</p>`:''}`:'<p>Add your first goal to build a practical learning schedule.</p>'}<details><summary>Adjust pace and schedule</summary><form data-study-pace-form data-plan="${e(plan.id)}" class="study-form-grid"><label>Minutes per day<input name="daily_minutes" type="number" min="5" max="480" value="${plan.daily_minutes}" required></label><label>Target date<input name="target_date" type="date" value="${e(plan.target_date||'')}"></label><label class="study-check"><input name="paused" type="checkbox" ${plan.paused?'checked':''}>Pause this plan</label><button class="button button-secondary" type="submit">Save schedule</button></form><p>${e(plan.pace_notice)}</p></details><div class="study-goals">${plan.goals.map(goalCard).join('')}</div>${goalForm(plan)}</article>`).join('')}</section><section class="panel study-activity"><h2>Your study rhythm</h2><p>Last 28 days · ${e(overview.timezone)} · ${overview.active_days} active ${overview.active_days===1?'day':'days'}</p><ol class="study-days" aria-label="Activity over the last 28 days">${overview.daily.map(d=>`<li class="${d.minutes||d.sections_completed||d.mock_sessions||d.lessons_completed?'active':''}" title="${e(d.date)}: ${d.minutes} minutes, ${d.sections_completed} sections, ${d.lessons_completed} lessons, ${d.mock_sessions} interviews"><span class="sr-only">${e(d.date)}: ${d.minutes} minutes, ${d.sections_completed} sections, ${d.lessons_completed} lessons, ${d.mock_sessions} interviews</span></li>`).join('')}</ol><p class="study-basis">${e(overview.activity_basis)}</p><details><summary>View study log</summary><div class="study-table-wrap"><table><caption>Daily activity</caption><thead><tr><th scope="col">Date</th><th scope="col">Minutes</th><th scope="col">Sections</th><th scope="col">Video + quiz</th><th scope="col">Interviews</th></tr></thead><tbody>${overview.daily.slice().reverse().map(d=>`<tr><td>${e(d.date)}</td><td>${d.minutes}</td><td>${d.sections_completed}</td><td>${d.lessons_completed}</td><td>${d.mock_sessions}</td></tr>`).join('')}</tbody></table></div></details></section><div id="study-offline-panel"></div><p id="study-status" role="status" aria-live="polite"></p>`;
    if(pending&&pending.kind!=='roadmap'&&p.length){const form=document.querySelector('.study-add-goal form');if(form){form.closest('details').open=true;form.elements.kind.value=pending.kind;updateGoalForm(form);form.elements.resource_id.value=pending.id;}}
    if (pending?.kind === 'roadmap' || overview.plans.length) pending=null;
  }
  function updateGoalForm(form){const kind=form.elements.kind.value,plan=overview.plans.find(p=>p.id===form.dataset.plan),road=catalog.roadmaps.find(r=>r.id===plan.roadmap_id);const label=form.querySelector('[data-study-resource-label]');label.hidden=['mock','task'].includes(kind);form.querySelector('[data-study-title-label]').hidden=kind!=='task';form.querySelector('[data-study-target-label]').hidden=!['mock','task'].includes(kind);const items=kind==='notes'?catalog.notes:kind==='video'?catalog.videos:road?.milestones||[];label.firstChild.textContent=kind==='notes'?'Notebook':kind==='video'?'Course':'Roadmap outcome';form.elements.resource_id.innerHTML=options(items);}
  async function reload(){const v=epoch;const data=await Promise.all([ctx.api('/study-tracker'),ctx.api('/study-tracker/resources')]);if(!active(v))return;[overview,catalog]=data;renderContent();}
  async function render(context){ctx=context;epoch++;quoteIndex=(quoteIndex+1)%quotes.length;try{localStorage.setItem('placeai.study.welcome.v2',String(quoteIndex));}catch{}ctx.setPage('Study tracker');ctx.setContextAction();document.querySelector('#app-content').innerHTML='<div class="workspace-feature-heading">'+ctx.pageHead('Study tracker','Set your goals. Read, practise and follow your progress in one place.')+'<img class="workspace-feature-photo" src="/static/workspace-study-tracker.webp" alt="" width="800" height="533" decoding="async"></div>'+'<div id="study-tracker"><p role="status">Loading your study plans…</p></div>';await reload();}
  function register(){return window.PlaceAIStudentViews?.register('study-tracker',render);}if(!register())window.addEventListener('placeai:student-views-ready',register,{once:true});
  document.addEventListener('change',event=>{if(event.target.matches('[data-study-goal-form] [name=kind]'))updateGoalForm(event.target.form);if(event.target.matches('#study-plan-form [name=roadmap_id]')){const road=catalog.roadmaps.find(r=>r.id===event.target.value);if(road){event.target.form.elements.title.value=road.title;event.target.form.elements.daily_minutes.value=Math.min(480,Math.max(5,Math.round((road.weekly_hours||5)*60/7)));}}});
  document.addEventListener('submit',async event=>{
    const form=event.target;if(!form.matches('#study-target-form,#study-plan-form,[data-study-goal-form],[data-study-manual-form],[data-study-pace-form],#study-offline-form')||!active(epoch))return;event.preventDefault();const button=form.querySelector('[type=submit]');if(button.disabled)return;button.disabled=true;const v=epoch,data=Object.fromEntries(new FormData(form));
    try{
      if(form.id==='study-target-form'){
        const counts = period => Object.fromEntries(Object.keys(metrics).map(key => [key,Number(data[`${period}-${key}`] || 0)]));
        await ctx.api('/study-tracker/targets',{
          method:'PUT', body:JSON.stringify({daily:counts('daily'),weekly:counts('weekly'),
            reminders:data.reminders==='on',timezone:Intl.DateTimeFormat().resolvedOptions().timeZone||'Asia/Kolkata'})
        });
      }
      else if(form.id==='study-plan-form'){const fingerprint=JSON.stringify(data); if(form.dataset.fingerprint!==fingerprint){form.dataset.fingerprint=fingerprint;form.dataset.requestId=crypto.randomUUID();} await ctx.api('/study-tracker/plans',{method:'POST',body:JSON.stringify({request_id:form.dataset.requestId,title:data.title,roadmap_id:data.roadmap_id||null,daily_minutes:Number(data.daily_minutes),target_date:data.target_date||null,timezone:Intl.DateTimeFormat().resolvedOptions().timeZone||'Asia/Kolkata'})});}
      else if(form.matches('[data-study-goal-form]'))await ctx.api(`/study-tracker/plans/${encodeURIComponent(form.dataset.plan)}/goals`,{method:'POST',body:JSON.stringify({kind:data.kind,resource_id:data.resource_id||'',title:data.title||'',target:Number(data.target||1)})});
      else if(form.matches('[data-study-manual-form]'))await ctx.api(`/study-tracker/goals/${encodeURIComponent(form.dataset.goal)}`,{method:'PATCH',body:JSON.stringify({completed:Number(data.completed)})});
      else if(form.matches('[data-study-pace-form]'))await ctx.api(`/study-tracker/plans/${encodeURIComponent(form.dataset.plan)}`,{method:'PATCH',body:JSON.stringify({daily_minutes:Number(data.daily_minutes),target_date:data.target_date||null,paused:data.paused==='on'})});
      else await ctx.api(`/study-tracker/notes/${encodeURIComponent(form.dataset.notebook)}`,{method:'PUT',body:JSON.stringify({section_key:data.section_key,completed:true,through:true,source:'offline',event_id:crypto.randomUUID()})});
      if(active(v)){await reload();const notice = document.querySelector('#study-status');
        notice.textContent = form.id==='study-target-form' ? 'Study targets saved.' : 'Study progress saved.';
        if (form.id==='study-target-form') document.querySelector('.study-target-settings summary')?.focus();}
    }catch(error){if(active(v))(form.querySelector('[role=status]')||document.querySelector('#study-status')).textContent=error.message;}finally{if(button.isConnected)button.disabled=false;}
  });
  document.addEventListener('click',async event=>{
    const button=event.target.closest('[data-study-open],[data-study-refresh],[data-study-resume],[data-study-offline],[data-study-remove]');if(!button||!active(epoch)||button.disabled)return;const v=epoch;button.disabled=true;
    try{
      if(button.dataset.studyOpen){
        if (button.dataset.studyOpen === 'lessons') window.PlaceAIStudySelection = {kind:'video'};
        await ctx.navigate(metrics[button.dataset.studyOpen].view);
      }
      else if(button.hasAttribute('data-study-refresh'))await reload();

      else if(button.dataset.studyResume){const goal=overview.plans.flatMap(p=>p.goals).find(g=>g.id===button.dataset.studyResume);if(goal?.resume){if(goal.kind==='notes'||goal.kind==='video')window.PlaceAIStudySelection={kind:goal.kind,id:goal.resource_id,section:goal.resume.section};await ctx.navigate(goal.resume.view);}}
      else if(button.dataset.studyOffline){const data=await ctx.api(`/study-tracker/notes/${encodeURIComponent(button.dataset.studyOffline)}`);if(active(v)){const panel=document.querySelector('#study-offline-panel');panel.innerHTML=`<section class="panel"><h2>Update your PDF reading</h2><p>Select the last section you have finished. This marks it and all earlier sections complete. Offline study time is not recorded.</p><form id="study-offline-form" data-notebook="${e(button.dataset.studyOffline)}"><label>Finished through section<select name="section_key">${data.sections.map(s=>`<option value="${e(s.key)}">${e(s.key+' · '+s.title)}</option>`).join('')}</select></label><button class="button button-primary" type="submit">Mark through this section</button><p role="status"></p></form></section>`;panel.scrollIntoView({block:'center',behavior:'auto'});panel.querySelector('select').focus();}}
      else if(button.dataset.studyRemove){await ctx.api(`/study-tracker/goals/${encodeURIComponent(button.dataset.studyRemove)}`,{method:'DELETE'});if(active(v)){await reload();document.querySelector('#study-status').textContent='Goal removed. Your notes, course and learning progress are unchanged.';}}
    }catch(error){if(active(v))document.querySelector('#study-status').textContent=error.message;}finally{if(button.isConnected)button.disabled=false;}
  });
})();
