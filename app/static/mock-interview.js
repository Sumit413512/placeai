(() => {
  'use strict';
  // Legacy static-mirror regression marker: Resilient role-grounded practice / resilient_baseline

  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const esc = (value = '') => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const apiErrors = window.PlaceAIApiErrors || {createError:()=>new Error('Request failed'),applyToForm:()=>{}};
  const previewMode = location.hostname.endsWith('.onrender.com') || new URLSearchParams(location.search).get('preview') === '1';

  const BLUEPRINT = [
    {key:'quantitative', label:'Quantitative Aptitude', count:8, minutes:12, kind:'mcq'},
    {key:'logical', label:'Logical & Analytical Reasoning', count:8, minutes:12, kind:'mcq'},
    {key:'communication', label:'Verbal & Communication', count:6, minutes:10, kind:'mcq'},
    {key:'technical', label:'Technical Fundamentals', count:8, minutes:14, kind:'mixed'},
    {key:'programming', label:'Programming & Debugging', count:6, minutes:14, kind:'mixed'},
    {key:'coding', label:'Coding Challenges', count:2, minutes:24, kind:'text'},
    {key:'resume', label:'Resume & Project Defence', count:4, minutes:10, kind:'text'},
    {key:'behavioral', label:'Behavioural & HR', count:4, minutes:10, kind:'text'},
    {key:'role', label:'Role / JD / Company', count:2, minutes:5, kind:'text'},
    {key:'situational', label:'Situational & Decision', count:2, minutes:5, kind:'text'}
  ];
  const TOTAL_QUESTIONS = BLUEPRINT.reduce((sum, item) => sum + item.count, 0);
  const TOTAL_SECONDS = BLUEPRINT.reduce((sum, item) => sum + item.minutes * 60, 0);

  const state = {
    token:'',
    me:null,
    jobs:[],
    session:null,
    questions:[],
    answers:[],
    current:0,
    selectedOption:null,
    mediaStream:null,
    assessmentActive:false,
    finishing:false,
    livenessPassed:false,
    systemReady:false,
    integrityEvents:[],
    totalRemaining:TOTAL_SECONDS,
    sectionRemaining:0,
    timerId:null,
    faceTimer:null,
    candidateLabel:'Candidate',
    ignoreFullscreen:false,
    lastResult:null,
    reviewFilter:'all',
    analysisTimers:[],
    integrityWarnings:0,
    integrityWarningLimit:4,
    lastWarningAt:0,
    autoSubmittedIntegrity:false,
    integrityTerminationReason:'',
    proctorVisionTimer:null,
    proctorVisionBusy:false,
    faceMissStreak:0,
    multipleFaceStreak:0,
    phoneDetectionStreak:0
  };

  function toast(message, type='') {
    const node = $('#toast');
    if (!node) return;
    node.textContent = message;
    node.className = `toast ${type}`.trim();
    node.classList.remove('hidden');
    clearTimeout(node._hideTimer);
    node._hideTimer = setTimeout(() => node.classList.add('hidden'), 4200);
  }

  function renderBlueprint() {
    const list = $('#blueprint-list');
    if (!list) return;
    list.innerHTML = BLUEPRINT.map((item,index)=>`
      <div class="blueprint-row">
        <span class="blueprint-index">${String(index+1).padStart(2,'0')}</span>
        <div><strong>${esc(item.label)}</strong><small>${item.minutes} min · ${item.kind === 'mcq' ? 'Objective' : item.kind === 'mixed' ? 'Objective + applied' : 'Applied response'}</small></div>
        <b>${item.count}</b>
      </div>`).join('');
  }

  function previewJobs() {
    return [
      {id:'demo-swe',title:'Graduate Software Engineer',company_name:'Campus Technology Partner',required_skills:['Python','SQL','Data Structures','APIs']},
      {id:'demo-analyst',title:'Graduate Data Analyst',company_name:'Campus Analytics Partner',required_skills:['SQL','Excel','Statistics','Data Interpretation']}
    ];
  }

  function setCheck(name, status, text) {
    const row = document.querySelector(`.check-row[data-check="${name}"]`);
    if (!row) return;
    row.classList.remove('pass','fail');
    if (status === 'pass') row.classList.add('pass');
    if (status === 'fail') row.classList.add('fail');
    const b = row.querySelector('b');
    if (b) b.textContent = text;
  }

  let refreshPromise = null;
  async function refreshToken() {
    if (previewMode) return true;
    if (refreshPromise) return refreshPromise;
    refreshPromise = (async () => {
      const response = await fetch('/auth/refresh', {method:'POST',headers:{'Content-Type':'application/json'},credentials:'include',body:'{}'});
      if (!response.ok) return false;
      const data = await response.json();
      state.token = data.access_token || '';
      return Boolean(state.token);
    })().finally(() => { refreshPromise = null; });
    return refreshPromise;
  }

  async function api(path, options={}) {
    if (previewMode) throw new Error('Preview mode does not call production APIs.');
    if (!state.token && !(await refreshToken())) throw new Error('Your PlaceAI session has expired. Sign in as a student and try again.');
    const headers = new Headers(options.headers || {});
    headers.set('Authorization', `Bearer ${state.token}`);
    if (options.body && !headers.has('Content-Type')) headers.set('Content-Type','application/json');
    let response = await fetch(path, {...options,headers,credentials:'include'});
    if (response.status === 401 && await refreshToken()) {
      headers.set('Authorization', `Bearer ${state.token}`);
      response = await fetch(path, {...options,headers,credentials:'include'});
    }
    const contentType = response.headers.get('content-type') || '';
    const data = contentType.includes('application/json') ? await response.json().catch(()=>({})) : {};
    if (!response.ok) throw apiErrors.createError(data || {}, response.status);
    return data;
  }

  async function loadJobs() {
    const jobs = previewMode ? previewJobs() : await api('/mock-interview/jobs');
    state.jobs = jobs;
    const select = $('#job-select');
    select.innerHTML = `<option value="">Select an opportunity…</option>${jobs.map(j=>`<option value="${esc(j.id)}">${esc(j.title)}${j.company_name ? ` · ${esc(j.company_name)}` : ''}</option>`).join('')}`;
    if (!jobs.length) select.innerHTML = '<option value="">No approved opportunities available</option>';
  }

  async function loadHistory() {
    const panel = $('#history-panel');
    try {
      const rows = previewMode ? [
        {job_title:'Graduate Software Engineer',company_name:'Campus Technology Partner',overall_score:78,created_at:new Date(Date.now()-86400000*3).toISOString()},
        {job_title:'Graduate Software Engineer',company_name:'Campus Technology Partner',overall_score:71,created_at:new Date(Date.now()-86400000*9).toISOString()}
      ] : await api('/mock-interview/history');
      panel.classList.remove('hidden');
      $('#history-list').innerHTML = rows.length ? rows.map(row=>`<article class="history-item"><div><strong>${esc(row.job_title)}</strong><span>${esc(row.company_name || 'Company')} · ${row.created_at ? new Date(row.created_at).toLocaleString('en-IN') : 'Saved attempt'}</span></div><div class="history-score">${row.overall_score ?? '—'}</div></article>`).join('') : '<p class="disclaimer">No saved attempts yet.</p>';
    } catch (_) {}
  }

  const sampleBank = {
    quantitative:[
      ['A campus recruiter shortlists 72 of 120 applicants. What percentage of applicants were shortlisted?',['50%','55%','60%','65%'],'60%'],
      ['A test has 80 questions. A candidate answers 68. What fraction of the test was attempted?',['75%','80%','85%','90%'],'85%'],
      ['An internship stipend increases from 20,000 to 23,000. What is the percentage increase?',['10%','12%','15%','18%'],'15%'],
      ['Five students complete a task in 12 hours at the same rate. How many student-hours are required?',['17','48','60','72'],'60%'],
      ['The ratio of technical to HR questions is 3:2. If there are 30 technical questions, how many HR questions are there?',['12','18','20','24'],'20'],
      ['A score rises from 64 to 80. What is the absolute increase?',['12','14','16','20'],'16'],
      ['If 3 out of 8 applicants clear a round, what is the approximate clearance percentage?',['27.5%','32.5%','37.5%','42.5%'],'37.5%'],
      ['The average of 72, 78, 84 and 86 is:',['78','79','80','81'],'80']
    ],
    logical:[
      ['All backend engineers in a team know APIs. Some API engineers know SQL. Which statement is definitely true?',['All SQL engineers are backend engineers','All backend engineers know APIs','No API engineer knows SQL','All API engineers are backend engineers'],'All backend engineers know APIs'],
      ['Sequence: 3, 6, 12, 24, ?',['30','36','42','48'],'48'],
      ['If interview A is before B, and B is before C, which must be true?',['C is before A','A is before C','B is after C','A and C are simultaneous'],'A is before C'],
      ['A candidate can choose exactly one of Python or Java, and must also choose SQL. Which combination is valid?',['Python + Java','SQL only','Python + SQL','Java only'],'Python + SQL'],
      ['Find the odd one out: API, Database, Operating System, Resume',['API','Database','Operating System','Resume'],'Resume'],
      ['If every passed coding test implies technical eligibility, and Priya passed coding, what follows?',['Priya is technically eligible','Priya is hired','Priya passed HR','Nothing follows'],'Priya is technically eligible'],
      ['Arrange from smallest to largest: 0.25, 1/2, 40%, 0.75',['0.25,40%,1/2,0.75','40%,0.25,1/2,0.75','0.25,1/2,40%,0.75','1/2,0.25,40%,0.75'],'0.25,40%,1/2,0.75'],
      ['If X is greater than Y and Y equals Z, which is true?',['X < Z','X = Z','X > Z','Cannot compare'],'X > Z']
    ],
    communication:[
      ['Choose the most professional sentence.',['Send me the file ASAP.','Could you please share the file by 3 PM so I can complete the review?','Need file now.','You forgot the file.'],'Could you please share the file by 3 PM so I can complete the review?'],
      ['Which response best demonstrates active listening?',['Changing the topic','Repeating the question word-for-word','Summarising the concern before responding','Speaking for longer'],'Summarising the concern before responding'],
      ['Choose the grammatically correct sentence.',['The data is useful for this analysis.','The data are useful for this analysis.','The data be useful.','Data useful analysis.'],'The data is useful for this analysis.'],
      ['In an interview, the strongest concise answer usually begins with:',['A direct response to the question','A long personal history','An unrelated example','An apology'],'A direct response to the question'],
      ['Which phrase is clearest for uncertainty?',['I definitely know, maybe.','Based on the information available, my current assumption is…','Whatever works.','I guess so.'],'Based on the information available, my current assumption is…'],
      ['Which structure is most useful for behavioural answers?',['STAR','FIFO','HTTP','CRUD'],'STAR']
    ]
  };

  function makeDemoQuestions(job) {
    const questions = [];
    let id = 1;
    for (const section of BLUEPRINT) {
      const bank = sampleBank[section.key] || [];
      for (let i=0;i<section.count;i++) {
        if (bank[i]) {
          const [question,options,correct] = bank[i];
          questions.push({question_id:id++,section:section.key,category:section.label,difficulty:i < Math.ceil(section.count*.4)?'Foundation':i < Math.ceil(section.count*.8)?'Intermediate':'Advanced',question,answer_type:'mcq',options,correct});
          continue;
        }
        const skill = (job.required_skills || ['role fundamentals'])[i % Math.max(1,(job.required_skills || []).length)] || 'role fundamentals';
        const templates = {
          technical:`For a ${job.title} role, explain how you would apply ${skill} to solve a production-relevant problem and validate the result.`,
          programming:`A ${skill} implementation produces the correct result for normal inputs but fails on edge cases. Describe a disciplined debugging approach.`,
          coding:`Design an algorithm for a role-relevant data-processing task. Explain the data structure, time complexity, edge cases and how you would test it.`,
          resume:`Defend one project or skill from your resume that is directly relevant to ${job.title}. Explain your personal contribution, a difficult decision and the evidence of the outcome.`,
          behavioral:`Describe a specific situation where you received difficult feedback. What action did you take and what changed as a result?`,
          role:`Based on the known requirements of the ${job.title} opportunity, which capability would you prioritise in your first 30 days and why?`,
          situational:`A deadline is close and you discover a defect that could affect users. What would you do next, and how would you communicate the trade-off?`
        };
        questions.push({question_id:id++,section:section.key,category:section.label,difficulty:i < Math.ceil(section.count*.4)?'Foundation':i < Math.ceil(section.count*.8)?'Intermediate':'Advanced',question:templates[section.key] || `Explain a role-relevant approach for ${skill}.`,answer_type:'text'});
      }
    }
    return questions;
  }

  function normalizeQuestions(data, job) {
    if (previewMode) return makeDemoQuestions(job);
    const raw = Array.isArray(data.questions) ? data.questions : [];
    return raw.map((q,index)=>({
      ...q,
      question_id:Number(q.question_id || index+1),
      section:q.section || q.category || 'technical',
      category:q.category || q.section || 'Interview',
      difficulty:q.difficulty || 'mixed',
      answer_type:Array.isArray(q.options) && q.options.length ? 'mcq' : (q.answer_type || 'text'),
      options:Array.isArray(q.options) ? q.options : []
    }));
  }

  function wrapText(ctx, text, maxWidth) {
    const words = String(text).split(/\s+/);
    const lines=[]; let line='';
    for(const word of words){
      const test=line ? `${line} ${word}` : word;
      if(ctx.measureText(test).width > maxWidth && line){ lines.push(line); line=word; }
      else line=test;
    }
    if(line) lines.push(line);
    return lines;
  }

  function drawTextCanvas(canvas, text, watermark, {fontSize=34,padding=54,lineHeight=48,minHeight=250}={}) {
    if (!canvas) return;
    const width = Math.max(700, canvas.parentElement?.clientWidth ? canvas.parentElement.clientWidth * 2 : 1200);
    const ctx = canvas.getContext('2d');
    ctx.font = `600 ${fontSize}px "DM Sans", Arial, sans-serif`;
    const lines = wrapText(ctx,text,width-padding*2);
    const height = Math.max(minHeight*2,padding*2 + lines.length*lineHeight + 90);
    canvas.width = width;
    canvas.height = height;
    ctx.fillStyle='#ffffff'; ctx.fillRect(0,0,width,height);
    ctx.save();
    ctx.translate(width*.1,height*.72); ctx.rotate(-0.16);
    ctx.font='800 24px "DM Sans", Arial, sans-serif'; ctx.fillStyle='rgba(28,80,150,.08)';
    const mark = `${watermark} · PLACEAI SECURE`;
    for(let x=0;x<width*1.2;x+=420) ctx.fillText(mark,x,0);
    ctx.restore();
    ctx.fillStyle='#17263d'; ctx.font=`600 ${fontSize}px "DM Sans", Arial, sans-serif`;
    let y=padding+fontSize;
    lines.forEach(line=>{ctx.fillText(line,padding,y);y+=lineHeight;});
    ctx.font='700 18px "DM Sans", Arial, sans-serif'; ctx.fillStyle='#718096';
    ctx.fillText(`Protected assessment item · ${watermark}`,padding,height-34);
  }

  function drawOptionCanvas(canvas, text, watermark) {
    if (!canvas) return;
    const width = Math.max(620, canvas.parentElement?.clientWidth ? (canvas.parentElement.clientWidth - 70) * 2 : 900);
    const ctx = canvas.getContext('2d');
    ctx.font='500 25px "DM Sans", Arial, sans-serif';
    const lines=wrapText(ctx,text,width-40);
    const height=Math.max(90,lines.length*34+30);
    canvas.width=width;canvas.height=height;
    ctx.fillStyle='#ffffff';ctx.fillRect(0,0,width,height);
    ctx.fillStyle='#27364c';ctx.font='500 25px "DM Sans", Arial, sans-serif';
    let y=31;lines.forEach(line=>{ctx.fillText(line,12,y);y+=34;});
    ctx.font='700 12px "DM Sans", Arial, sans-serif';ctx.fillStyle='rgba(40,91,160,.13)';
    ctx.fillText(watermark,width-ctx.measureText(watermark).width-10,height-10);
  }

  function currentSectionInfo(question) {
    return BLUEPRINT.find(x=>x.key===question?.section) || BLUEPRINT[0];
  }

  function isAttemptedAnswer(answer) {
    return Boolean(answer && answer.answer && !String(answer.answer).startsWith('['));
  }

  function renderSectionNav() {
    const nav=$('#section-nav');
    const attemptedCount=state.answers.filter(isAttemptedAnswer).length;
    if($('#palette-progress')) $('#palette-progress').textContent=attemptedCount+' / '+state.questions.length;
    nav.innerHTML=BLUEPRINT.map(function(section){
      const rows=state.questions.map(function(q,index){return {q:q,index:index};}).filter(function(row){return row.q.section===section.key;});
      if(!rows.length)return '';
      const chips=rows.map(function(row){
        const isCurrent=row.index===state.current;
        const attempted=isAttemptedAnswer(state.answers[row.q.question_id-1]);
        const status=isCurrent?'current':attempted?'attempted':'unattempted';
        const label='Question '+row.q.question_id+' · '+status;
        return '<span class="palette-question '+status+' locked" aria-label="'+esc(label)+'" title="'+esc(label)+'">'+row.q.question_id+'</span>';
      }).join('');
      const done=rows.filter(function(row){return isAttemptedAnswer(state.answers[row.q.question_id-1]);}).length;
      return '<section class="palette-section"><div class="palette-section-title"><strong>'+esc(section.label)+'</strong><span>'+done+'/'+rows.length+'</span></div><div class="palette-question-grid">'+chips+'</div></section>';
    }).join('');
  }

  function renderAnswerArea(question) {
    const area=$('#answer-area');
    state.selectedOption=null;
    const existing=state.answers[question.question_id-1];
    if (question.answer_type==='mcq' && question.options?.length) {
      if(existing?.answer) {
        const existingIndex=question.options.findIndex(function(option){return option===existing.answer;});
        if(existingIndex>=0) state.selectedOption=existingIndex;
      }
      area.innerHTML=`<div class="answer-options">${question.options.map((_,i)=>`<button class="option-button" type="button" data-option-index="${i}"><span class="option-key">${String.fromCharCode(65+i)}</span><canvas class="option-canvas"></canvas></button>`).join('')}</div>`;
      $$('.option-button',area).forEach((button,i)=>{
        drawOptionCanvas(button.querySelector('canvas'),question.options[i],state.candidateLabel);
        if(state.selectedOption===i) button.classList.add('selected');
        button.addEventListener('click',()=>{
          $$('.option-button',area).forEach(x=>x.classList.remove('selected'));
          button.classList.add('selected'); state.selectedOption=i;
        });
      });
    } else {
      area.innerHTML='<label class="answer-field">Your response<textarea id="current-answer" class="secure-textarea" maxlength="5000" autocomplete="off" spellcheck="true" placeholder="Write a concise, evidence-based response."></textarea></label>';
      if(existing?.answer) $('#current-answer').value=existing.answer;
    }
  }

  function renderQuestion() {
    const q=state.questions[state.current];
    if(!q) return;
    const info=currentSectionInfo(q);
    $('#section-label').textContent=info.label;
    $('#question-progress').textContent=`Question ${state.current+1} of ${state.questions.length}`;
    $('#question-section').textContent=info.label;
    $('#question-difficulty').textContent=q.difficulty || 'Mixed';
    $('#question-guidance').textContent=q.answer_type==='mcq'
      ? 'Select one option, then submit. Question and option content is rendered to canvas and cannot be selected as page text.'
      : 'Respond using clear reasoning and evidence. After submission this question is permanently closed.';
    drawTextCanvas($('#question-canvas'),q.question,`${state.candidateLabel} · Q${state.current+1}`);
    renderAnswerArea(q);
    renderSectionNav();
    $('#autosave-state').textContent=isAttemptedAnswer(state.answers[q.question_id-1])?'Answer saved':'Response not saved';
    $('#next-question').textContent=state.current===state.questions.length-1?'Save & Submit':'Save & Next';
    const sectionFirst=state.questions.findIndex(x=>x.section===q.section);
    if(state.current===sectionFirst || state.sectionRemaining<=0) state.sectionRemaining=info.minutes*60;
    updateTimers();
  }

  function answerCurrentQuestion() {
    const q=state.questions[state.current];
    let answer='';
    if(q.answer_type==='mcq') {
      if(state.selectedOption===null) { toast('Select an option before continuing.','error'); return false; }
      answer=q.options[state.selectedOption];
    } else {
      answer=($('#current-answer')?.value || '').trim();
      if(!answer) { toast('Enter your response before continuing.','error'); return false; }
    }
    state.answers[q.question_id-1]={question_id:q.question_id,answer};
    $('#autosave-state').textContent='Answer saved';
    renderSectionNav();
    return true;
  }

  function formatTime(seconds) {
    const s=Math.max(0,seconds|0); const h=Math.floor(s/3600); const m=Math.floor((s%3600)/60); const sec=s%60;
    return h>0?`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`:`${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;
  }

  function updateTimers() {
    $('#total-timer').textContent=formatTime(state.totalRemaining);
    $('#section-timer').textContent=formatTime(state.sectionRemaining);
    const pct=Math.max(0,Math.min(100,state.totalRemaining/TOTAL_SECONDS*100));
    $('#total-progress').style.width=`${pct}%`;
  }

  function markQuestionUnanswered(index, reason) {
    const q=state.questions[index];
    if(!q || state.answers[q.question_id-1]) return;
    state.answers[q.question_id-1]={question_id:q.question_id,answer:reason||'[No response submitted]'};
  }

  function expireCurrentSection() {
    const currentQuestion=state.questions[state.current];
    if(!currentQuestion){finishAssessment(true);return;}
    const section=currentQuestion.section;
    while(state.current<state.questions.length && state.questions[state.current].section===section){
      markQuestionUnanswered(state.current,'[No response submitted before section time expired]');
      state.current++;
    }
    if(state.current<state.questions.length){
      state.sectionRemaining=0;
      renderQuestion();
    }else{
      finishAssessment(true);
    }
  }

  function fillUnansweredResponses(reason) {
    state.questions.forEach(function(_,index){markQuestionUnanswered(index,reason||'[No response submitted before assessment ended]');});
  }

  function startTimer() {
    clearInterval(state.timerId);
    state.timerId=setInterval(()=>{
      if(!state.assessmentActive || !$('#integrity-overlay').classList.contains('hidden')) return;
      state.totalRemaining--; state.sectionRemaining--; updateTimers();
      if(state.totalRemaining<=0){
        fillUnansweredResponses('[No response submitted before total assessment time expired]');
        finishAssessment(true);
        return;
      }
      if(state.sectionRemaining<=0){
        logIntegrity('section_time_expired','Section time expired; remaining unanswered items in this section were closed automatically.');
        expireCurrentSection();
      }
    },1000);
  }

  function updateIntegrityWarningUI() {
    const text=state.integrityWarnings+' / '+state.integrityWarningLimit+' warnings';
    if($('#integrity-warning-badge')) $('#integrity-warning-badge').textContent=text;
    if($('#overlay-warning-number')) $('#overlay-warning-number').textContent=String(Math.max(1,state.integrityWarnings));
    if(state.integrityWarnings>=Math.max(1,state.integrityWarningLimit-1)) document.body.classList.add('integrity-critical');
  }

  function persistIntegrityEvent(event) {
    if(previewMode || !state.session?.interview_id) return;
    api('/mock-interview/integrity-event',{
      method:'POST',
      body:JSON.stringify({interview_id:state.session.interview_id,event:event})
    }).catch(function(){});
  }

  function logIntegrity(type,detail,source,warningNumber) {
    const event={
      event_type:type,
      detail:detail||'',
      at:new Date().toISOString(),
      question:Math.min(state.questions.length||TOTAL_QUESTIONS,state.current+1),
      warning_number:warningNumber||null,
      source:source||'system'
    };
    state.integrityEvents.push(event);
    $('#integrity-count').textContent=state.integrityEvents.length+' integrity event'+(state.integrityEvents.length===1?'':'s');
    persistIntegrityEvent(event);
    return event;
  }

  function showIntegrityPause(title,text) {
    if(!state.assessmentActive || state.finishing || state.autoSubmittedIntegrity) return;
    $('#integrity-overlay-title').textContent=title;
    $('#integrity-overlay-text').textContent=text;
    $('#restore-secure-mode').disabled=false;
    $('#restore-secure-mode').textContent='Restore secure mode';
    updateIntegrityWarningUI();
    $('#integrity-overlay').classList.remove('hidden');
  }

  function autoTerminateForIntegrity(reason) {
    if(state.autoSubmittedIntegrity || state.finishing) return;
    state.autoSubmittedIntegrity=true;
    state.integrityTerminationReason=reason||'Integrity warning limit reached.';
    state.integrityWarnings=Math.max(state.integrityWarnings,state.integrityWarningLimit);
    updateIntegrityWarningUI();
    document.body.classList.add('integrity-critical');
    logIntegrity('integrity_auto_submit',state.integrityTerminationReason,'system',state.integrityWarnings);
    fillUnansweredResponses('[No response submitted — assessment auto-submitted after integrity warning limit]');
    $('#integrity-overlay-title').textContent='Assessment auto-submitted';
    $('#integrity-overlay-text').textContent='The secure assessment reached the configured integrity-warning limit. Your attempt is being submitted with an institutional review flag.';
    $('#restore-secure-mode').disabled=true;
    $('#restore-secure-mode').textContent='Submitting…';
    $('#integrity-overlay').classList.remove('hidden');
    toast('Integrity warning limit reached. Assessment is being submitted for review.','error');
    setTimeout(function(){finishAssessment(true);},650);
  }

  function registerIntegrityWarning(type,detail,source,title,pause) {
    if(!state.assessmentActive || state.finishing || state.autoSubmittedIntegrity) return;
    const now=Date.now();
    if(now-state.lastWarningAt<2500){
      logIntegrity(type,detail+' (correlated with the current warning)','system',null);
      return;
    }
    state.lastWarningAt=now;
    state.integrityWarnings+=1;
    logIntegrity(type,detail,source||'browser',state.integrityWarnings);
    updateIntegrityWarningUI();
    if(state.integrityWarnings>=state.integrityWarningLimit){
      autoTerminateForIntegrity(detail);
      return;
    }
    if(pause!==false){
      showIntegrityPause(
        title||'Integrity warning',
        detail+' Warning '+state.integrityWarnings+' of '+state.integrityWarningLimit+'. Restore the secure environment to continue.'
      );
    }else{
      toast('Integrity warning '+state.integrityWarnings+' of '+state.integrityWarningLimit+': '+detail,'error');
    }
  }

  async function restoreSecureMode() {
    if(state.autoSubmittedIntegrity)return;
    try {
      await $('#interview-panel').requestFullscreen();
      $('#integrity-overlay').classList.add('hidden');
    } catch {
      toast('Full-screen access is required to continue this secure assessment.','error');
    }
  }

  function installSecureGuards() {
    document.addEventListener('copy',blockClipboard,true);
    document.addEventListener('cut',blockClipboard,true);
    document.addEventListener('paste',blockClipboard,true);
    document.addEventListener('contextmenu',blockContext,true);
    document.addEventListener('keydown',blockKeys,true);
    window.addEventListener('beforeunload',beforeUnload);
    window.addEventListener('popstate',blockBack);
    document.addEventListener('visibilitychange',visibilityGuard);
    document.addEventListener('fullscreenchange',fullscreenGuard);
    window.addEventListener('blur',blurGuard);
  }

  function uninstallSecureGuards() {
    document.removeEventListener('copy',blockClipboard,true);
    document.removeEventListener('cut',blockClipboard,true);
    document.removeEventListener('paste',blockClipboard,true);
    document.removeEventListener('contextmenu',blockContext,true);
    document.removeEventListener('keydown',blockKeys,true);
    window.removeEventListener('beforeunload',beforeUnload);
    window.removeEventListener('popstate',blockBack);
    document.removeEventListener('visibilitychange',visibilityGuard);
    document.removeEventListener('fullscreenchange',fullscreenGuard);
    window.removeEventListener('blur',blurGuard);
  }

  function blockClipboard(event){
    if(!state.assessmentActive)return;
    event.preventDefault();
    logIntegrity('clipboard_blocked',event.type+' attempt blocked.','browser',null);
    toast('Clipboard actions are disabled in secure mode.','error');
  }
  function blockContext(event){
    if(!state.assessmentActive)return;
    event.preventDefault();
    logIntegrity('context_menu_blocked','Context menu attempt blocked.','browser',null);
  }
  function blockKeys(event){
    if(!state.assessmentActive)return;
    const key=event.key.toLowerCase();
    if((event.ctrlKey||event.metaKey)&&['c','v','x','p','s','u','a'].includes(key)){
      event.preventDefault();
      logIntegrity('shortcut_blocked','Blocked keyboard shortcut: '+key,'browser',null);
    }
    if(event.key==='F12'){
      event.preventDefault();
      logIntegrity('developer_shortcut','Developer-tools shortcut attempted.','browser',null);
    }
  }
  function beforeUnload(event){if(!state.assessmentActive)return;event.preventDefault();event.returnValue='';}
  function blockBack(){
    if(!state.assessmentActive)return;
    history.pushState({placeaiSecure:true},'',location.href);
    registerIntegrityWarning('back_navigation','Browser back navigation was attempted.','browser','Navigation attempt detected',true);
  }
  function visibilityGuard(){
    if(!state.assessmentActive||state.finishing)return;
    if(document.hidden){
      registerIntegrityWarning('tab_hidden','The assessment tab lost visibility.','browser','Tab switch detected',true);
    }
  }
  function blurGuard(){
    if(!state.assessmentActive||state.finishing)return;
    logIntegrity('window_blur','Browser window lost focus.','browser',null);
  }
  function fullscreenGuard(){
    if(!state.assessmentActive||state.finishing||state.ignoreFullscreen)return;
    if(!document.fullscreenElement){
      registerIntegrityWarning('fullscreen_exit','Secure full-screen mode was exited.','browser','Full-screen interruption detected',true);
    }
  }

  async function runSystemCheck() {
    setCheck('browser','pass','Ready');
    setCheck('clipboard','pass','Enabled');
    setCheck('visibility','pass','Enabled');
    setCheck('fullscreen',document.fullscreenEnabled?'pass':'fail',document.fullscreenEnabled?'Supported':'Unavailable');

    try {
      if(state.mediaStream) state.mediaStream.getTracks().forEach(t=>t.stop());
      state.mediaStream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'user',width:{ideal:1280},height:{ideal:720}},audio:true});
      const video=$('#camera-preview'); video.srcObject=state.mediaStream; await video.play();
      $('#assessment-camera').srcObject=state.mediaStream; $('#assessment-camera').play().catch(()=>{});
      $('#camera-placeholder').classList.add('hidden'); $('#camera-live').classList.remove('hidden');
      const videoTrack=state.mediaStream.getVideoTracks()[0], audioTrack=state.mediaStream.getAudioTracks()[0];
      $('#device-label').textContent=videoTrack?.label || 'Camera connected';
      setCheck('camera',videoTrack?'pass':'fail',videoTrack?'Connected':'Missing');
      setCheck('microphone',audioTrack?'pass':'fail',audioTrack?'Connected':'Missing');
      $('#run-liveness').disabled=!videoTrack;
      $('#system-status-pill').textContent='Media ready';
      $('#system-status-pill').classList.remove('neutral');
      if(previewMode) {
        $('#liveness-help').textContent='Preview mode can simulate the liveness workflow for UI review. No biometric verification is performed or stored.';
      } else if('FaceDetector' in window) {
        $('#liveness-help').textContent='Compatible face detection is available. Run the active movement challenge to continue.';
      } else {
        $('#liveness-help').textContent='Native face detection is unavailable; PlaceAI will use the active motion + AI person-presence fallback.';
        setCheck('liveness',null,'Pending');
      }
    } catch (error) {
      setCheck('camera','fail','Denied');
      setCheck('microphone','fail','Denied');
      $('#system-status-pill').textContent='Permission required';
      toast('Camera and microphone permission are required for secure mode.','error');
    }
    updateStartEligibility();
  }

  function motionSignature(video) {
    const canvas=document.createElement('canvas');
    canvas.width=64;canvas.height=48;
    const ctx=canvas.getContext('2d',{willReadFrequently:true});
    ctx.drawImage(video,0,0,64,48);
    const data=ctx.getImageData(0,0,64,48).data;
    const values=[];
    for(let i=0;i<data.length;i+=16){
      values.push((data[i]+data[i+1]+data[i+2])/3);
    }
    return values;
  }

  function motionDelta(a,b) {
    if(!a||!b||a.length!==b.length)return 0;
    let total=0;
    for(let i=0;i<a.length;i++)total+=Math.abs(a[i]-b[i]);
    return total/(a.length*255);
  }

  async function runLiveness() {
    if(!state.mediaStream){toast('Run the system check first.','error');return;}
    $('#run-liveness').disabled=true;
    $('#liveness-title').textContent='Checking active presence…';

    if(previewMode) {
      await new Promise(r=>setTimeout(r,900));
      state.livenessPassed=true;
      $('#liveness-title').textContent='Preview workflow passed';
      $('#liveness-help').textContent='UI preview only — no biometric or ML liveness conclusion has been made.';
      setCheck('liveness','pass','Preview flow');
      updateStartEligibility();
      return;
    }

    const video=$('#camera-preview');
    try {
      if('FaceDetector' in window) {
        const detector=new FaceDetector({fastMode:true,maxDetectedFaces:2});
        const samples=[];
        $('#liveness-help').textContent='Keep one face visible, then slowly move your head left and right.';
        for(let i=0;i<14;i++){
          await new Promise(r=>setTimeout(r,220));
          const faces=await detector.detect(video);
          if(faces.length!==1){samples.push(null);continue;}
          const box=faces[0].boundingBox;
          samples.push((box.x+box.width/2)/Math.max(1,video.videoWidth));
        }
        const valid=samples.filter(x=>typeof x==='number');
        const movement=valid.length?Math.max(...valid)-Math.min(...valid):0;
        if(valid.length>=9 && movement>=0.08){
          state.livenessPassed=true;
          $('#liveness-title').textContent='Active liveness signal passed';
          $('#liveness-help').textContent='One face remained visible and sufficient head movement was observed during the challenge.';
          setCheck('liveness','pass','Passed');
        }else{
          state.livenessPassed=false;
          $('#liveness-title').textContent='Liveness not verified';
          $('#liveness-help').textContent='Keep one face visible and repeat the left/right movement challenge.';
          setCheck('liveness','fail','Retry');
          $('#run-liveness').disabled=false;
        }
      } else {
        $('#liveness-help').textContent='Slowly move your head left and right. PlaceAI will combine visible motion with an AI person-presence check.';
        const first=motionSignature(video);
        await new Promise(r=>setTimeout(r,1100));
        const second=motionSignature(video);
        await new Promise(r=>setTimeout(r,1100));
        const third=motionSignature(video);
        const movement=Math.max(motionDelta(first,second),motionDelta(second,third),motionDelta(first,third));
        const image=captureProctorFrame();
        if(!image) throw new Error('Camera frame unavailable');
        const vision=await api('/mock-interview/proctor-frame',{method:'POST',body:JSON.stringify({interview_id:state.session.interview_id,image_data_url:image})});
        if(vision.candidate_visible && Number(vision.person_count||0)===1 && movement>=0.025){
          state.livenessPassed=true;
          $('#liveness-title').textContent='Active presence challenge passed';
          $('#liveness-help').textContent='One person was visible and sufficient live camera motion was observed. This is an integrity signal, not biometric identity verification.';
          setCheck('liveness','pass','Passed');
        }else{
          state.livenessPassed=false;
          $('#liveness-title').textContent='Active presence not verified';
          $('#liveness-help').textContent='Keep one person centered in the camera and repeat the head-movement challenge.';
          setCheck('liveness','fail','Retry');
          $('#run-liveness').disabled=false;
        }
      }
    } catch {
      state.livenessPassed=false;
      $('#liveness-title').textContent='Liveness check unavailable';
      $('#liveness-help').textContent='The active presence check could not be completed. Verify camera/network access and retry.';
      setCheck('liveness','fail','Retry');
      $('#run-liveness').disabled=false;
    }
    updateStartEligibility();
  }


  function updateStartEligibility() {
    const consent=$('#consent-check').checked;
    const media=Boolean(state.mediaStream?.getVideoTracks().length && state.mediaStream?.getAudioTracks().length);
    state.systemReady=media && state.livenessPassed && document.fullscreenEnabled;
    $('#start-assessment').disabled=!(state.systemReady && consent);
    if(state.systemReady) $('#system-status-pill').textContent='Ready for secure mode';
  }

  async function prepareAssessment(event) {
    event.preventDefault();
    const jobId=$('#job-select').value;
    if(!jobId){toast('Select a target opportunity.','error');return;}
    const job=state.jobs.find(j=>String(j.id)===String(jobId));
    const button=event.currentTarget.querySelector('button[type="submit"]');
    button.disabled=true; button.textContent='Building standardized assessment…';
    try {
      if(previewMode){
        state.session={interview_id:'preview-session',job_title:job.title,company_name:job.company_name,mode:'assessment'};
        state.questions=makeDemoQuestions(job);
      } else {
        const data=await api('/mock-interview/start',{method:'POST',body:JSON.stringify({job_id:jobId,mode:'assessment',question_count:50,focus:'balanced',difficulty:'mixed'})});
        state.session=data; state.questions=normalizeQuestions(data,job);
        if(state.questions.length<50) throw new Error('Secure full mock requires at least 50 primary assessment items.');
      }
      state.answers=new Array(state.questions.length);
      $('#interview-title').textContent=`${job.title} placement simulation`;
      $('#interview-context').textContent=`${job.company_name || 'Opportunity'} · ${state.questions.length} primary items · secure forward-only mode`;
      $('#setup-panel').classList.add('hidden'); $('#system-panel').classList.remove('hidden');
      $('#system-panel').scrollIntoView({behavior:'smooth',block:'start'});
    } catch(error){
      const form = event.currentTarget;
      apiErrors.applyToForm(form, error);
      toast(error.message,'error');
    }
    finally{button.disabled=false;button.textContent='Continue to secure system check';}
  }

  async function startAssessment() {
    if(!state.systemReady || !$('#consent-check').checked){toast('Complete all required secure checks first.','error');return;}
    try {
      await $('#interview-panel').requestFullscreen();
    } catch {
      toast('Full-screen permission is required to start the assessment.','error');
      return;
    }
    state.assessmentActive=true;state.finishing=false;state.current=0;state.totalRemaining=TOTAL_SECONDS;state.sectionRemaining=0;state.integrityEvents=[];state.integrityWarnings=0;state.lastWarningAt=0;state.autoSubmittedIntegrity=false;state.integrityTerminationReason='';state.proctorVisionBusy=false;state.faceMissStreak=0;state.multipleFaceStreak=0;state.phoneDetectionStreak=0;
    document.body.classList.remove('integrity-critical');
    updateIntegrityWarningUI();
    document.body.classList.add('secure-assessment');
    $('#system-panel').classList.add('hidden'); $('#interview-panel').classList.remove('hidden');
    history.pushState({placeaiSecure:true},'',location.href);
    installSecureGuards();
    renderQuestion(); startTimer(); startPresenceMonitoring();
  }

  function captureProctorFrame() {
    const video=$('#assessment-camera');
    if(!video || video.readyState<2 || !video.videoWidth || !video.videoHeight) return null;
    const canvas=document.createElement('canvas');
    canvas.width=320;canvas.height=240;
    const ctx=canvas.getContext('2d',{alpha:false});
    const scale=Math.max(canvas.width/video.videoWidth,canvas.height/video.videoHeight);
    const width=video.videoWidth*scale,height=video.videoHeight*scale;
    ctx.drawImage(video,(canvas.width-width)/2,(canvas.height-height)/2,width,height);
    return canvas.toDataURL('image/jpeg',0.52);
  }

  async function runVisionProctorCheck() {
    if(previewMode || !state.assessmentActive || state.proctorVisionBusy || document.hidden || !state.session?.interview_id) return;
    const image=captureProctorFrame();
    if(!image)return;
    state.proctorVisionBusy=true;
    try{
      const data=await api('/mock-interview/proctor-frame',{method:'POST',body:JSON.stringify({interview_id:state.session.interview_id,image_data_url:image})});
      $('#camera-proctor-status').textContent=data.mobile_phone_detected?'Phone signal detected':'AI vision active';
      if(data.mobile_phone_detected){
        state.phoneDetectionStreak+=1;
        logIntegrity('phone_visual_signal','AI vision detected a clearly visible mobile-phone object in the webcam frame.','vision',null);
        if(state.phoneDetectionStreak>=2){
          state.phoneDetectionStreak=0;
          registerIntegrityWarning('mobile_phone_detected','A mobile phone was detected in two consecutive AI-vision checks.','vision','Mobile-phone warning',false);
        }
      }else{
        state.phoneDetectionStreak=0;
      }

      if(!('FaceDetector' in window)){
        if(!data.candidate_visible || Number(data.person_count||0)===0){
          state.faceMissStreak+=1;
          if(state.faceMissStreak>=2){
            state.faceMissStreak=0;
            registerIntegrityWarning('candidate_not_visible','The candidate was not visible in consecutive webcam checks.','vision','Candidate not visible',false);
          }
        }else state.faceMissStreak=0;

        if(Number(data.person_count||0)>1){
          state.multipleFaceStreak+=1;
          if(state.multipleFaceStreak>=2){
            state.multipleFaceStreak=0;
            registerIntegrityWarning('multiple_people','More than one person was visible in consecutive webcam checks.','vision','Multiple people detected',false);
          }
        }else state.multipleFaceStreak=0;
      }
    }catch(error){
      $('#camera-proctor-status').textContent='Vision check unavailable';
    }finally{
      state.proctorVisionBusy=false;
    }
  }

  async function startPresenceMonitoring() {
    clearInterval(state.faceTimer);
    clearInterval(state.proctorVisionTimer);
    state.faceMissStreak=0;state.multipleFaceStreak=0;state.phoneDetectionStreak=0;
    const video=$('#assessment-camera');
    const track=state.mediaStream?.getVideoTracks?.()[0];
    if(track){
      track.onended=function(){registerIntegrityWarning('camera_stopped','Camera access stopped during the assessment.','camera','Camera stopped',true);};
      track.onmute=function(){logIntegrity('camera_muted','Camera stream was temporarily muted.','camera',null);};
    }

    if('FaceDetector' in window){
      const detector=new FaceDetector({fastMode:true,maxDetectedFaces:3});
      state.faceTimer=setInterval(async function(){
        if(!state.assessmentActive||document.hidden||state.finishing)return;
        try{
          const faces=await detector.detect(video);
          if(faces.length===0){
            state.faceMissStreak+=1;
            $('#camera-proctor-status').textContent='Candidate not visible';
            if(state.faceMissStreak>=2){
              state.faceMissStreak=0;
              registerIntegrityWarning('candidate_not_visible','The candidate was not visible in consecutive liveness checks.','camera','Candidate not visible',false);
            }
          }else{
            state.faceMissStreak=0;
            $('#camera-proctor-status').textContent='Presence verified';
          }
          if(faces.length>1){
            state.multipleFaceStreak+=1;
            if(state.multipleFaceStreak>=2){
              state.multipleFaceStreak=0;
              registerIntegrityWarning('multiple_people',faces.length+' faces were detected in consecutive camera checks.','camera','Multiple people detected',false);
            }
          }else state.multipleFaceStreak=0;
        }catch{}
      },7000);
    }else{
      $('#camera-proctor-status').textContent=previewMode?'Preview camera active':'AI vision presence check';
    }

    if(!previewMode){
      state.proctorVisionTimer=setInterval(runVisionProctorCheck,18000);
      setTimeout(runVisionProctorCheck,4500);
    }
  }

  function saveCurrentAnswerOnly() {
    if(!answerCurrentQuestion())return;
    $('#autosave-state').textContent='Answer saved · use Save & Next to continue';
    toast('Answer saved for the current question.');
  }

  async function submitAndContinue() {
    if(!answerCurrentQuestion()) return;
    if(state.current>=state.questions.length-1){await finishAssessment(false);return;}
    state.current++;
    renderQuestion();
  }



  const RESULT_SECTION_WEIGHTS = {
    quantitative:10, logical:10, communication:10, technical:20, programming:15,
    coding:15, resume:7, behavioral:5, role:5, situational:3
  };

  function verdictBucket(verdict) {
    verdict = verdict || '';
    if (verdict === 'correct' || verdict === 'strong') return 'correct';
    if (verdict === 'partially_correct' || verdict === 'acceptable') return 'partial';
    if (verdict === 'incorrect' || verdict === 'weak') return 'incorrect';
    return 'insufficient';
  }

  function previewTextEvaluation(question, answer) {
    const clean = (answer || '').trim();
    const words = clean.toLowerCase().match(/[a-z0-9+#.-]+/g) || [];
    const unique = new Set(words);
    const obviousJunk = /^(anything|test|testing|asdf+|qwer+|random|abc+|xyz+|hello|nothing|idk|i don't know)[\\s.!?]*$/i.test(clean)
      || (words.length > 2 && unique.size / words.length < 0.25);
    const qTerms = new Set((question.question || '').toLowerCase().match(/[a-z0-9+#.-]{3,}/g) || []);
    const overlap = Array.from(unique).filter(function(token){ return qTerms.has(token); }).length;
    let score = 0;
    if (!clean) score = 0;
    else if (obviousJunk) score = 4;
    else {
      score = 12 + Math.min(28, words.length * 1.15) + Math.min(25, overlap * 7);
      if (words.length >= 35) score += 10;
      if (/[0-9]|because|therefore|first|then|example|validate|test|result|trade.?off/i.test(clean)) score += 8;
      score = Math.min(78, Math.round(score));
      if (overlap === 0 && words.length < 25) score = Math.min(score, 22);
    }
    const behavioral = ['resume','behavioral','role','situational'].includes(question.section);
    let verdict = 'insufficient';
    if (behavioral) verdict = score >= 75 ? 'strong' : score >= 55 ? 'acceptable' : score >= 20 ? 'weak' : 'insufficient';
    else verdict = score >= 75 ? 'correct' : score >= 50 ? 'partially_correct' : score >= 16 ? 'incorrect' : 'insufficient';
    return {
      question_id:question.question_id, question:question.question, section:question.section, category:question.category,
      difficulty:question.difficulty, answer_type:'text', answer:clean, correct_answer:'', score:score, verdict:verdict,
      grading_method:'preview_heuristic',
      rubric:{correctness:score,relevance:Math.min(100,overlap*20),reasoning:Math.min(100,Math.round(words.length*1.7)),completeness:Math.min(100,Math.round(words.length*2)),clarity:words.length?65:0},
      feedback:score<16?'The response does not provide enough relevant evidence to answer the question.':score<50?'The response contains limited relevant material but does not adequately answer the question.':'The response addresses the question, but production AI performs deeper correctness and rubric analysis.',
      strengths:score>=50?['Contains some question-relevant content.']:[],
      issues:score<50?['Insufficient question-specific reasoning or evidence.']:['Static preview cannot validate deep technical correctness.'],
      missing_points:['Give a direct answer, reasoning, concrete evidence and a validation/result step.'],
      key_points:[], better_answer_outline:'Direct answer -> reasoning/method -> evidence/example -> validation/result.',
      ideal_answer:'Static preview only. Production uses the PlaceAI AI evaluator to generate a question-specific strong answer.'
    };
  }

  function buildPreviewResult() {
    if (!state.questions.length) {
      const job = previewJobs()[0];
      state.questions = makeDemoQuestions(job);
      state.answers = state.questions.map(function(q){
        if (q.answer_type === 'mcq') {
          return {question_id:q.question_id, answer:q.question_id % 3 === 0 ? q.options[0] : (q.correct || q.options[0])};
        }
        return {question_id:q.question_id, answer:q.question_id % 4 === 0 ? 'anything' : 'I would first clarify the requirement, apply a structured approach, test edge cases, and validate the result with measurable evidence.'};
      });
    }
    const evaluations = state.questions.map(function(q){
      const answer = state.answers[q.question_id-1] ? state.answers[q.question_id-1].answer : '';
      if (q.answer_type === 'mcq') {
        const correct = q.correct || '';
        const isCorrect = !!correct && answer.trim().toLowerCase() === correct.trim().toLowerCase();
        return {
          question_id:q.question_id,question:q.question,section:q.section,category:q.category,difficulty:q.difficulty,
          answer_type:'mcq',answer:answer,correct_answer:correct,score:isCorrect?100:0,verdict:isCorrect?'correct':'incorrect',
          grading_method:'system',
          rubric:{correctness:isCorrect?100:0,relevance:isCorrect?100:0,reasoning:null,completeness:isCorrect?100:0,clarity:null},
          feedback:isCorrect?'Correct answer.':'Incorrect answer.',
          strengths:isCorrect?['Selected the correct option.']:[],
          issues:isCorrect?[]:['The selected option does not match the answer key.'],
          missing_points:[],key_points:correct?['Correct answer: '+correct]:[],better_answer_outline:'',ideal_answer:correct
        };
      }
      return previewTextEvaluation(q, answer);
    });

    const sectionScores = [];
    const totals = {correct:0,partial:0,incorrect:0,insufficient:0,system_graded:0,ai_graded:0};
    BLUEPRINT.forEach(function(section){
      const items = evaluations.filter(function(x){ return x.section === section.key; });
      if (!items.length) return;
      const counts = {correct:0,partial:0,incorrect:0,insufficient:0};
      items.forEach(function(item){
        counts[verdictBucket(item.verdict)] += 1;
        if (item.grading_method === 'system') totals.system_graded += 1;
        else totals.ai_graded += 1;
      });
      Object.keys(counts).forEach(function(k){ totals[k] += counts[k]; });
      sectionScores.push({key:section.key,label:section.label,score:Math.round(items.reduce(function(a,b){return a+b.score;},0)/items.length),questions:items.length,correct:counts.correct,partial:counts.partial,incorrect:counts.incorrect,insufficient:counts.insufficient});
    });
    let weighted = 0;
    let weight = 0;
    sectionScores.forEach(function(row){ const w=RESULT_SECTION_WEIGHTS[row.key]||0; weighted += row.score*w; weight += w; });
    const objective = evaluations.filter(function(x){ return x.grading_method === 'system'; });
    const subjective = evaluations.filter(function(x){ return x.grading_method !== 'system'; });
    const score = Math.round(weighted/(weight||1));
    return {
      analysis_status:'complete',
      overall_score:score,
      raw_assessment_score:Math.round(evaluations.reduce(function(a,b){return a+b.score;},0)/evaluations.length),
      overall_feedback:'Preview scoring evaluated all '+evaluations.length+' responses question-by-question. '+totals.correct+' were correct/strong, '+totals.partial+' partial/acceptable, '+totals.incorrect+' incorrect/weak, and '+totals.insufficient+' insufficient.',
      score_summary:{
        total_questions:evaluations.length,evaluated_questions:evaluations.length,correct:totals.correct,partial:totals.partial,incorrect:totals.incorrect,insufficient:totals.insufficient,system_graded:totals.system_graded,ai_graded:totals.ai_graded,
        objective_accuracy:objective.length?Math.round(100*objective.filter(function(x){return x.score===100;}).length/objective.length):null,
        subjective_average:subjective.length?Math.round(subjective.reduce(function(a,b){return a+b.score;},0)/subjective.length):null
      },
      section_scores:sectionScores,
      dimensions:Object.fromEntries(sectionScores.map(function(x){return [x.key,x.score];})),
      strengths:sectionScores.slice().sort(function(a,b){return b.score-a.score;}).slice(0,3).map(function(x){return x.label+': '+x.score+'/100.';}),
      improvements:sectionScores.slice().sort(function(a,b){return a.score-b.score;}).slice(0,3).map(function(x){return x.label+': '+x.score+'/100 - review the question-level feedback.';}),
      weak_topics:sectionScores.slice().sort(function(a,b){return a.score-b.score;}).filter(function(x){return x.score<70;}).slice(0,3).map(function(x){return x.label;}),
      next_practice_plan:sectionScores.slice().sort(function(a,b){return a.score-b.score;}).slice(0,3).map(function(x){return 'Complete a targeted '+x.label+' drill before the next full mock.';}),
      evaluations:evaluations,
      grading:{objective:'server-side answer key',subjective:'static preview heuristic - production uses AI',provider:'preview',model:'no live AI'},
      integrity_report:{
        status:state.autoSubmittedIntegrity?'auto_submitted_review_required':(state.integrityEvents.length?'review_required':'clear'),
        warning_count:state.integrityWarnings,
        warning_limit:state.integrityWarningLimit,
        auto_submitted:state.autoSubmittedIntegrity,
        termination_reason:state.integrityTerminationReason||'',
        events:state.integrityEvents,
        institution_name:'Preview Institution',
        note:'Preview integrity signals are for UI review and are not automatic findings of misconduct.'
      },
      disclaimer:'Render preview scoring is deterministic for UI review. Production open-ended responses are evaluated by the PlaceAI AI rubric; integrity signals remain separate.'
    };
  }

  function clearAnalysisTimers() {
    (state.analysisTimers || []).forEach(clearTimeout);
    state.analysisTimers = [];
  }

  function setAnalysisPhase(index) {
    const rows = $$('.analysis-step');
    rows.forEach(function(row,i){
      row.classList.toggle('done', i < index);
      row.classList.toggle('active', i === index);
      const b = row.querySelector('b');
      if (b) b.textContent = i < index ? 'Done' : i === index ? 'Running' : 'Queued';
    });
    const messages = [
      'Checking objective answers against protected server-side answer keys.',
      'AI is evaluating every open-ended answer against the exact question and scoring rubric.',
      'Building section-level accuracy, strengths, gaps and readiness scores from question results.',
      'Generating corrections, ideal approaches and the next-practice plan.'
    ];
    $('#analysis-message').textContent = messages[Math.min(index,3)];
  }

  function showAnalysisPanel() {
    clearAnalysisTimers();
    $('#result-panel').classList.add('hidden');
    $('#analysis-panel').classList.remove('hidden');
    $('#retry-analysis').classList.add('hidden');
    setAnalysisPhase(0);
    state.analysisTimers.push(setTimeout(function(){setAnalysisPhase(1);},700));
    state.analysisTimers.push(setTimeout(function(){setAnalysisPhase(2);},5000));
    state.analysisTimers.push(setTimeout(function(){setAnalysisPhase(3);},10000));
    $('#analysis-panel').scrollIntoView({behavior:'smooth',block:'start'});
  }

  function markAnalysisComplete() {
    clearAnalysisTimers();
    $$('.analysis-step').forEach(function(row){
      row.classList.remove('active');
      row.classList.add('done');
      const b=row.querySelector('b');
      if(b)b.textContent='Done';
    });
  }

  async function runResultAnalysis(auto) {
    showAnalysisPanel();
    try {
      let result;
      if (previewMode) {
        await new Promise(function(resolve){setTimeout(resolve,1400);});
        result = buildPreviewResult();
      } else {
        result = await api('/mock-interview/evaluate',{method:'POST',body:JSON.stringify({
          interview_id:state.session.interview_id,
          answers:state.answers.filter(Boolean),
          integrity_events:state.integrityEvents,
          integrity_warning_count:state.integrityWarnings,
          integrity_auto_submitted:state.autoSubmittedIntegrity,
          integrity_termination_reason:state.integrityTerminationReason||null
        })});
      }
      markAnalysisComplete();
      state.lastResult = result;
      state.finishing = false;
      setTimeout(function(){
        $('#analysis-panel').classList.add('hidden');
        renderResult(result,!!auto);
      },250);
    } catch(error) {
      clearAnalysisTimers();
      state.finishing = false;
      $('#analysis-message').textContent = 'Analysis could not be completed: '+error.message;
      $('#retry-analysis').classList.remove('hidden');
      toast('Question-level analysis did not complete. No final score was fabricated.','error');
    }
  }

  async function finishAssessment(auto) {
    if(state.finishing)return;
    fillUnansweredResponses(auto?'[No response submitted before assessment time expired]':'[No response submitted]');
    state.finishing=true;
    clearInterval(state.timerId);
    clearInterval(state.faceTimer);
    clearInterval(state.proctorVisionTimer);
    state.ignoreFullscreen=true;
    try{if(document.fullscreenElement)await document.exitFullscreen();}catch{}
    state.ignoreFullscreen=false;
    state.assessmentActive=false;
    uninstallSecureGuards();
    document.body.classList.remove('secure-assessment','integrity-critical');
    $('#integrity-overlay').classList.add('hidden');
    $('#interview-panel').classList.add('hidden');
    await runResultAnalysis(!!auto);
  }

  function renderSectionPerformance(rows) {
    rows = rows || [];
    $('#section-performance').innerHTML = rows.map(function(row){
      return '<tr><td><strong>'+esc(row.label||row.key)+'</strong></td><td class="section-score">'+(row.score??'—')+'/100</td><td class="good-count">'+(row.correct??0)+'</td><td class="partial-count">'+(row.partial??0)+'</td><td class="bad-count">'+(row.incorrect??0)+'</td><td>'+(row.insufficient??0)+'</td><td>'+(row.questions??0)+'</td></tr>';
    }).join('') || '<tr><td colspan="7">No section results available.</td></tr>';
  }

  function reviewDetailsList(title,items) {
    items = items || [];
    if(!items.length)return '';
    return '<div class="review-detail-box"><h5>'+esc(title)+'</h5><ul>'+items.map(function(x){return '<li>'+esc(x)+'</li>';}).join('')+'</ul></div>';
  }

  function renderQuestionReviews(filter) {
    filter = filter || 'all';
    state.reviewFilter=filter;
    const result=state.lastResult||{};
    const rows=(result.evaluations||[]).filter(function(item){return filter==='all'||verdictBucket(item.verdict)===filter;});
    $('#answer-feedback').innerHTML=rows.map(function(item){
      const bucket=verdictBucket(item.verdict);
      const rubric=item.rubric||{};
      const rubricEntries=Object.entries(rubric).filter(function(entry){return entry[1]!==null&&entry[1]!==undefined;});
      const expected=item.correct_answer||item.ideal_answer||'';
      let html='<article class="answer-review review-'+bucket+'"><header class="answer-review-header"><div><div class="question-meta-line">';
      html+='<span class="review-chip '+bucket+'">'+esc((item.verdict||bucket).replaceAll('_',' '))+'</span>';
      html+='<span class="review-chip">'+esc((item.section||'interview').replaceAll('_',' '))+'</span>';
      html+='<span class="review-chip">'+esc(item.grading_method==='system'?'System graded':item.grading_method==='ai'?'AI graded':'Preview graded')+'</span>';
      html+='</div><h4>Q'+item.question_id+'. '+esc(item.question||'')+'</h4></div><div class="answer-score-box"><strong>'+(item.score??'—')+'</strong><small>/100</small></div></header>';
      html+='<div class="answer-comparison"><div class="answer-pane"><span>Your answer</span><p>'+esc(item.answer||'No answer')+'</p></div>';
      html+='<div class="answer-pane correct-pane"><span>'+(item.answer_type==='mcq'?'Correct answer':'Strong answer / reference')+'</span><p>'+esc(expected||'See detailed feedback below.')+'</p></div></div>';
      html+='<p class="review-feedback"><strong>Assessment:</strong> '+esc(item.feedback||'No detailed feedback returned.')+'</p>';
      if(rubricEntries.length){
        html+='<div class="rubric-grid">'+rubricEntries.map(function(entry){return '<div class="rubric-item"><span>'+esc(entry[0].replaceAll('_',' '))+'</span><strong>'+entry[1]+'/100</strong></div>';}).join('')+'</div>';
      }
      html+='<div class="review-details">'+reviewDetailsList('What worked',item.strengths||[])+reviewDetailsList('Errors / gaps',[].concat(item.issues||[],item.missing_points||[]))+'</div>';
      if(item.better_answer_outline)html+='<div class="ideal-answer-box"><strong>Better answer structure</strong><p>'+esc(item.better_answer_outline)+'</p></div>';
      html+='</article>';
      return html;
    }).join('') || '<p class="disclaimer">No questions match this filter.</p>';
    $$('.review-filter').forEach(function(button){button.classList.toggle('active',button.dataset.reviewFilter===filter);});
  }

  function renderIntegrityReport(result) {
    const report=result.integrity_report||{
      status:state.autoSubmittedIntegrity?'auto_submitted_review_required':(state.integrityEvents.length?'review_required':'clear'),
      warning_count:state.integrityWarnings,
      warning_limit:state.integrityWarningLimit,
      auto_submitted:state.autoSubmittedIntegrity,
      termination_reason:state.integrityTerminationReason||'',
      events:state.integrityEvents,
      institution_name:result.institution_name||'',
      note:'Integrity signals require human interpretation.'
    };
    const status=report.status||'clear';
    const warnings=Number(report.warning_count||0);
    const limit=Number(report.warning_limit||4);
    $('#result-warning-count').textContent=warnings+' / '+limit;
    $('#integrity-institution-name').textContent=report.institution_name||result.institution_name||'Not linked';
    if(status==='auto_submitted_review_required'){
      $('#integrity-status').textContent='Auto-submitted · review required';
      $('#integrity-summary-text').textContent='The assessment reached the configured integrity-warning limit and was submitted automatically. Academic scoring remains separate from the integrity review.';
    }else if(status==='review_required'){
      $('#integrity-status').textContent='Review recommended';
      $('#integrity-summary-text').textContent='One or more integrity signals were recorded. They require institutional review and do not by themselves establish misconduct.';
    }else{
      $('#integrity-status').textContent='No review events';
      $('#integrity-summary-text').textContent='No integrity warning events were recorded during this assessment.';
    }
    const termination=$('#integrity-termination-note');
    if(report.auto_submitted){
      termination.classList.remove('hidden');
      termination.innerHTML='<strong>Automatic submission:</strong> '+esc(report.termination_reason||'Integrity warning limit reached.')+' The institution should review the event timeline before drawing any conclusion.';
    }else termination.classList.add('hidden');

    const events=Array.isArray(report.events)?report.events:[];
    $('#integrity-event-list').innerHTML=events.length?events.map(function(event){
      const type=event.event_type||event.type||'integrity_signal';
      const warning=event.warning_number?'<b>Warning '+event.warning_number+'</b>':'<b>Logged</b>';
      let time='—';
      try{time=event.at?new Date(event.at).toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit',second:'2-digit'}):'—';}catch{}
      return '<article class="integrity-event-row '+(event.warning_number?'warning':'')+'"><time>'+esc(time)+'</time><div><strong>'+esc(type.replaceAll('_',' '))+'</strong><small>'+esc(event.detail||'Integrity signal recorded.')+'</small></div>'+warning+'</article>';
    }).join(''):'<p class="disclaimer">No integrity events were recorded for this attempt.</p>';
  }

  function renderResult(result,auto) {
    state.lastResult=result;
    const complete=result.analysis_status!=='incomplete';
    const summary=result.score_summary||{};
    $('#overall-score').textContent=result.overall_score??'—';
    $('#report-iri').textContent=result.overall_score===null||result.overall_score===undefined?'Withheld':result.overall_score+'/100';
    $('#overall-feedback').textContent=result.overall_feedback||'Assessment completed.';
    $('#grading-method-label').textContent=previewMode?'Answer key + preview scoring (production uses AI)':'Answer key + question-level AI';
    renderIntegrityReport(result);
    const banner=$('#analysis-status-banner');
    if(!complete){
      banner.classList.remove('hidden');banner.classList.add('error');
      banner.textContent='AI analysis is incomplete. PlaceAI intentionally withheld the final score instead of estimating technical correctness. Retry the analysis to complete the report.';
      $('#retry-analysis-result').classList.remove('hidden');
    } else if(previewMode){
      banner.classList.remove('hidden','error');
      banner.textContent='Render preview: objective answers are graded exactly; open-ended responses use a local UI-review heuristic. Production uses the server-side AI evaluator.';
      $('#retry-analysis-result').classList.add('hidden');
    } else {
      banner.classList.add('hidden');$('#retry-analysis-result').classList.add('hidden');
    }
    $('#summary-total').textContent=summary.total_questions??'—';
    $('#summary-correct').textContent=summary.correct??'—';
    $('#summary-partial').textContent=summary.partial??'—';
    $('#summary-incorrect').textContent=summary.incorrect??'—';
    $('#summary-insufficient').textContent=summary.insufficient??'—';
    $('#summary-objective').textContent=summary.objective_accuracy===null||summary.objective_accuracy===undefined?'—':summary.objective_accuracy+'%';
    $('#summary-subjective').textContent=summary.subjective_average===null||summary.subjective_average===undefined?'—':summary.subjective_average+'/100';
    renderSectionPerformance(result.section_scores||[]);
    $('#dimension-grid').innerHTML=Object.entries(result.dimensions||{}).map(function(entry){
      const score=entry[1];
      return '<article class="dimension"><small>'+esc(entry[0].replaceAll('_',' '))+'</small><strong>'+score+'</strong><div class="meter"><i style="width:'+Math.max(0,Math.min(100,Number(score)||0))+'%"></i></div></article>';
    }).join('');
    const list=function(values,fallback){return (values||[]).map(function(x){return '<li>'+esc(x)+'</li>';}).join('')||'<li>'+esc(fallback)+'</li>';};
    $('#strength-list').innerHTML=list(result.strengths,'No strong area identified yet.');
    $('#improvement-list').innerHTML=list(result.improvements,'No specific improvement returned.');
    $('#weak-topic-list').innerHTML=list(result.weak_topics,'No major weak topic detected.');
    $('#practice-plan-list').innerHTML=list(result.next_practice_plan,'Run another role-specific assessment.');
    $('#result-disclaimer').textContent=result.disclaimer||'';
    renderQuestionReviews('all');
    $('#result-panel').classList.remove('hidden');
    $('#result-panel').scrollIntoView({behavior:'smooth',block:'start'});
    loadHistory();
    if(auto)toast('Assessment submitted automatically when time expired.');
  }

  function resetAssessment() {
    clearInterval(state.timerId);clearInterval(state.faceTimer);clearInterval(state.proctorVisionTimer);
    state.assessmentActive=false;state.finishing=false;state.current=0;state.answers=[];state.questions=[];state.session=null;state.livenessPassed=false;state.systemReady=false;state.lastResult=null;state.reviewFilter='all';state.integrityEvents=[];state.integrityWarnings=0;state.lastWarningAt=0;state.autoSubmittedIntegrity=false;state.integrityTerminationReason='';state.faceMissStreak=0;state.multipleFaceStreak=0;state.phoneDetectionStreak=0;clearAnalysisTimers();
    if(state.mediaStream){state.mediaStream.getTracks().forEach(t=>t.stop());state.mediaStream=null;}
    document.body.classList.remove('secure-assessment');
    $('#result-panel').classList.add('hidden');$('#analysis-panel').classList.add('hidden');$('#system-panel').classList.add('hidden');$('#setup-panel').classList.remove('hidden');
    $('#consent-check').checked=false;$('#start-assessment').disabled=true;$('#run-liveness').disabled=true;
    setCheck('liveness',null,'Required');
    $('#camera-placeholder').classList.remove('hidden');$('#camera-live').classList.add('hidden');
    $('#setup-panel').scrollIntoView({behavior:'smooth',block:'start'});
  }

  $('#setup-form')?.addEventListener('submit',prepareAssessment);
  $('#run-check')?.addEventListener('click',runSystemCheck);
  $('#run-liveness')?.addEventListener('click',runLiveness);
  $('#consent-check')?.addEventListener('change',updateStartEligibility);
  $('#start-assessment')?.addEventListener('click',startAssessment);
  $('#save-question')?.addEventListener('click',saveCurrentAnswerOnly);
  $('#next-question')?.addEventListener('click',submitAndContinue);
  $('#restore-secure-mode')?.addEventListener('click',restoreSecureMode);
  $('#practice-again')?.addEventListener('click',resetAssessment);
  $('#retry-analysis')?.addEventListener('click',function(){if(state.finishing)return;state.finishing=true;runResultAnalysis(false);});
  $('#retry-analysis-result')?.addEventListener('click',function(){if(state.finishing)return;state.finishing=true;runResultAnalysis(false);});
  $('#review-filters')?.addEventListener('click',function(event){const button=event.target.closest('[data-review-filter]');if(button)renderQuestionReviews(button.dataset.reviewFilter);});

  (async()=>{
    renderBlueprint();
    if(previewMode){
      $('#preview-banner').classList.remove('hidden');
      $('#auth-state').classList.add('hidden');
      state.me={role:'student',full_name:'Preview Candidate'};
      state.candidateLabel='PREVIEW CANDIDATE';
      $('#setup-panel').classList.remove('hidden');
      await Promise.all([loadJobs(),loadHistory()]);
      const demo=new URLSearchParams(location.search).get('demo');
      if(demo==='result'||demo==='integrity'){
        if(demo==='integrity'){
          state.integrityWarnings=4;
          state.autoSubmittedIntegrity=true;
          state.integrityTerminationReason='Repeated secure-environment violations reached the configured warning limit.';
          state.integrityEvents=[
            {event_type:'fullscreen_exit',detail:'Secure full-screen mode was exited.',at:new Date(Date.now()-180000).toISOString(),question:8,warning_number:1,source:'browser'},
            {event_type:'tab_hidden',detail:'The assessment tab lost visibility.',at:new Date(Date.now()-120000).toISOString(),question:12,warning_number:2,source:'browser'},
            {event_type:'candidate_not_visible',detail:'The candidate was not visible in consecutive liveness checks.',at:new Date(Date.now()-60000).toISOString(),question:17,warning_number:3,source:'camera'},
            {event_type:'mobile_phone_detected',detail:'A mobile phone was detected in two consecutive AI-vision checks.',at:new Date(Date.now()-30000).toISOString(),question:19,warning_number:4,source:'vision'}
          ];
        }
        $('#setup-panel').classList.add('hidden');
        renderResult(buildPreviewResult(),false);
      }
      return;
    }
    try {
      if(!(await refreshToken())){
        $('#auth-state').innerHTML='No active student session. <a href="/?portal=student">Sign in to PlaceAI</a>, then return to Interview Intelligence.';
        return;
      }
      state.me=await api('/auth/me');
      if(state.me.role!=='student'){ $('#auth-state').textContent='Interview Intelligence is available to student accounts only.'; return; }
      state.candidateLabel=(state.me.full_name || state.me.username || 'Candidate').toUpperCase().slice(0,40);
      $('#auth-state').classList.add('hidden'); $('#setup-panel').classList.remove('hidden');
      await Promise.all([loadJobs(),loadHistory()]);
    } catch(error){ $('#auth-state').textContent=error.message; toast(error.message,'error'); }
  })();
})();