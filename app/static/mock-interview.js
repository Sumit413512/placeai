(() => {
  'use strict';
  // Legacy static-mirror regression marker: Resilient role-grounded practice

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
    ignoreFullscreen:false
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

  function renderSectionNav() {
    const currentQ = state.questions[state.current];
    const nav = $('#section-nav');
    nav.innerHTML = BLUEPRINT.map((item,index)=>{
      const sectionQuestions=state.questions.filter(q=>q.section===item.key);
      const first=sectionQuestions[0]?.question_id || 1;
      const last=sectionQuestions.at(-1)?.question_id || first;
      const done=state.current+1 > last;
      const active=currentQ?.section===item.key;
      return `<div class="section-link ${active?'active':''} ${done?'done':''}"><span>${String(index+1).padStart(2,'0')}</span><strong>${esc(item.label)}</strong><b>${item.count}</b></div>`;
    }).join('');
  }

  function renderAnswerArea(question) {
    const area=$('#answer-area');
    state.selectedOption=null;
    const existing=state.answers[question.question_id-1];
    if (question.answer_type==='mcq' && question.options?.length) {
      area.innerHTML=`<div class="answer-options">${question.options.map((_,i)=>`<button class="option-button" type="button" data-option-index="${i}"><span class="option-key">${String.fromCharCode(65+i)}</span><canvas class="option-canvas"></canvas></button>`).join('')}</div>`;
      $$('.option-button',area).forEach((button,i)=>{
        drawOptionCanvas(button.querySelector('canvas'),question.options[i],state.candidateLabel);
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
    $('#autosave-state').textContent='Response not submitted';
    $('#next-question').textContent=state.current===state.questions.length-1?'Submit final response':'Submit & continue';
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
    $('#autosave-state').textContent='Response submitted';
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

  function startTimer() {
    clearInterval(state.timerId);
    state.timerId=setInterval(()=>{
      if(!state.assessmentActive || !$('#integrity-overlay').classList.contains('hidden')) return;
      state.totalRemaining--; state.sectionRemaining--; updateTimers();
      if(state.totalRemaining<=0){finishAssessment(true);return;}
      if(state.sectionRemaining<=0){
        logIntegrity('section_time_expired','Section time expired; assessment advanced automatically.');
        if(state.current<state.questions.length-1){state.current++;renderQuestion();}else finishAssessment(true);
      }
    },1000);
  }

  function logIntegrity(type,detail) {
    state.integrityEvents.push({type,detail,at:new Date().toISOString(),question:state.current+1});
    $('#integrity-count').textContent=`${state.integrityEvents.length} review event${state.integrityEvents.length===1?'':'s'}`;
  }

  function showIntegrityPause(title,text) {
    if(!state.assessmentActive || state.finishing) return;
    $('#integrity-overlay-title').textContent=title;
    $('#integrity-overlay-text').textContent=text;
    $('#integrity-overlay').classList.remove('hidden');
  }

  async function restoreSecureMode() {
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

  function blockClipboard(event){if(!state.assessmentActive)return;event.preventDefault();logIntegrity('clipboard_blocked',`${event.type} attempt blocked.`);toast('Clipboard actions are disabled in secure mode.','error');}
  function blockContext(event){if(!state.assessmentActive)return;event.preventDefault();logIntegrity('context_menu_blocked','Context menu attempt blocked.');}
  function blockKeys(event){
    if(!state.assessmentActive)return;
    const key=event.key.toLowerCase();
    if((event.ctrlKey||event.metaKey)&&['c','v','x','p','s','u','a'].includes(key)){event.preventDefault();logIntegrity('shortcut_blocked',`Blocked keyboard shortcut: ${key}`);}
    if(event.key==='F12'){event.preventDefault();logIntegrity('developer_shortcut','Developer-tools shortcut attempted.');}
  }
  function beforeUnload(event){if(!state.assessmentActive)return;event.preventDefault();event.returnValue='';}
  function blockBack(){if(!state.assessmentActive)return;history.pushState({placeaiSecure:true},'',location.href);logIntegrity('back_navigation','Back navigation attempt blocked.');showIntegrityPause('Navigation attempt detected','The assessment is forward-only. Restore secure mode to continue.');}
  function visibilityGuard(){if(!state.assessmentActive||state.finishing)return;if(document.hidden){logIntegrity('tab_hidden','Assessment tab lost visibility.');}else if(document.fullscreenElement) showIntegrityPause('Focus interruption recorded','The assessment tab lost visibility. This event is available in the integrity timeline.');}
  function blurGuard(){if(!state.assessmentActive||state.finishing)return;logIntegrity('window_blur','Browser window lost focus.');}
  function fullscreenGuard(){if(!state.assessmentActive||state.finishing||state.ignoreFullscreen)return;if(!document.fullscreenElement){logIntegrity('fullscreen_exit','Secure full-screen was exited.');showIntegrityPause('Secure full-screen was interrupted','The assessment is paused. This event has been added to the integrity timeline. Restore full-screen to continue.');}}

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
        $('#liveness-help').textContent='This browser does not expose the required local face-detection capability. Secure liveness cannot be certified in this browser.';
        setCheck('liveness','fail','Unsupported');
      }
    } catch (error) {
      setCheck('camera','fail','Denied');
      setCheck('microphone','fail','Denied');
      $('#system-status-pill').textContent='Permission required';
      toast('Camera and microphone permission are required for secure mode.','error');
    }
    updateStartEligibility();
  }

  async function runLiveness() {
    if(!state.mediaStream){toast('Run the system check first.','error');return;}
    $('#run-liveness').disabled=true;
    $('#liveness-title').textContent='Checking face presence…';

    if(previewMode) {
      await new Promise(r=>setTimeout(r,900));
      state.livenessPassed=true;
      $('#liveness-title').textContent='Preview workflow passed';
      $('#liveness-help').textContent='UI preview only — no biometric or ML liveness conclusion has been made.';
      setCheck('liveness','pass','Preview flow');
      updateStartEligibility();
      return;
    }

    if(!('FaceDetector' in window)) {
      $('#liveness-title').textContent='Unsupported in this browser';
      setCheck('liveness','fail','Unsupported');
      toast('A compatible secure browser is required for active liveness verification.','error');
      return;
    }

    try {
      const detector=new FaceDetector({fastMode:true,maxDetectedFaces:2});
      const video=$('#camera-preview');
      const samples=[];
      $('#liveness-help').textContent='Keep your face centered, then slowly move your head left and right.';
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
        $('#liveness-title').textContent='Active liveness passed';
        $('#liveness-help').textContent='One live face and sufficient head movement were observed during the challenge.';
        setCheck('liveness','pass','Passed');
      }else{
        state.livenessPassed=false;
        $('#liveness-title').textContent='Liveness not verified';
        $('#liveness-help').textContent='Keep one face visible and repeat the left/right movement challenge.';
        setCheck('liveness','fail','Retry');
        $('#run-liveness').disabled=false;
      }
    } catch {
      state.livenessPassed=false;
      $('#liveness-title').textContent='Liveness check unavailable';
      setCheck('liveness','fail','Unavailable');
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
      apiErrors.applyToForm?.(event.currentTarget, error);
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
    state.assessmentActive=true; state.finishing=false; state.current=0; state.totalRemaining=TOTAL_SECONDS; state.sectionRemaining=0; state.integrityEvents=[];
    document.body.classList.add('secure-assessment');
    $('#system-panel').classList.add('hidden'); $('#interview-panel').classList.remove('hidden');
    history.pushState({placeaiSecure:true},'',location.href);
    installSecureGuards();
    renderQuestion(); startTimer(); startPresenceMonitoring();
  }

  async function startPresenceMonitoring() {
    clearInterval(state.faceTimer);
    if(previewMode || !('FaceDetector' in window)) return;
    const detector=new FaceDetector({fastMode:true,maxDetectedFaces:3});
    state.faceTimer=setInterval(async()=>{
      if(!state.assessmentActive || document.hidden) return;
      try {
        const faces=await detector.detect($('#assessment-camera'));
        if(faces.length===0) logIntegrity('face_absent','No face detected during periodic presence check.');
        if(faces.length>1) logIntegrity('multiple_faces',`${faces.length} faces detected during periodic presence check.`);
      } catch {}
    },15000);
  }

  async function submitAndContinue() {
    if(!answerCurrentQuestion()) return;
    if(state.current>=state.questions.length-1){await finishAssessment(false);return;}
    state.current++;
    renderQuestion();
  }

  function mockResult() {
    return {
      overall_score:82,
      overall_feedback:'Strong baseline placement readiness with clear technical fundamentals and structured reasoning. The next improvement priority is deeper explanation of trade-offs in programming and project-defence answers.',
      dimensions:{aptitude:86,reasoning:81,communication:84,technical:79,programming:76,coding:78,resume_defence:88,behavioral:85},
      strengths:['Clear problem decomposition across aptitude and technical questions.','Strong resume/project ownership language.','Professional, concise communication in behavioural scenarios.'],
      improvements:['Explain technical trade-offs more explicitly.','Use measurable evidence when defending project outcomes.','Practice edge-case reasoning in coding and debugging responses.'],
      weak_topics:['Algorithmic complexity under constraints','Database indexing trade-offs','Production debugging edge cases'],
      next_practice_plan:['Targeted 20-minute DSA/complexity drill.','Resume defence round focused on evidence and metrics.','Technical follow-up simulation with deeper probing.'],
      evaluations:[],
      disclaimer:'Preparation signal only. Integrity events are provided separately for human review and are not automatic findings of misconduct.'
    };
  }

  async function finishAssessment(auto=false) {
    if(state.finishing)return; state.finishing=true;
    clearInterval(state.timerId); clearInterval(state.faceTimer);
    let result;
    try {
      if(previewMode) result=mockResult();
      else {
        result=await api('/mock-interview/evaluate',{method:'POST',body:JSON.stringify({interview_id:state.session.interview_id,answers:state.answers.filter(Boolean)})});
      }
    } catch(error){state.finishing=false;startTimer();toast(error.message,'error');return;}

    state.ignoreFullscreen=true;
    try{if(document.fullscreenElement) await document.exitFullscreen();}catch{}
    state.ignoreFullscreen=false;
    state.assessmentActive=false; uninstallSecureGuards(); document.body.classList.remove('secure-assessment');
    $('#integrity-overlay').classList.add('hidden'); $('#interview-panel').classList.add('hidden');
    renderResult(result,auto);
  }

  function renderResult(result,auto) {
    $('#overall-score').textContent=result.overall_score ?? '—';
    $('#report-iri').textContent=`${result.overall_score ?? '—'}/100`;
    $('#overall-feedback').textContent=result.overall_feedback || 'Assessment completed.';
    $('#integrity-status').textContent=state.integrityEvents.length===0?'No review events':'Review recommended';
    $('#integrity-summary-text').textContent=state.integrityEvents.length===0
      ? 'No browser integrity events were recorded during this session.'
      : `${state.integrityEvents.length} event${state.integrityEvents.length===1?' was':'s were'} recorded for human review. Events are not treated as automatic proof of misconduct.`;
    $('#dimension-grid').innerHTML=Object.entries(result.dimensions||{}).map(([key,score])=>`<article class="dimension"><small>${esc(key.replaceAll('_',' '))}</small><strong>${score}</strong><div class="meter"><i style="width:${Math.max(0,Math.min(100,Number(score)||0))}%"></i></div></article>`).join('');
    const list=(values,fallback)=> (values||[]).map(x=>`<li>${esc(x)}</li>`).join('') || `<li>${esc(fallback)}</li>`;
    $('#strength-list').innerHTML=list(result.strengths,'No specific strength returned.');
    $('#improvement-list').innerHTML=list(result.improvements,'No specific improvement returned.');
    $('#weak-topic-list').innerHTML=list(result.weak_topics,'No major weak topic detected.');
    $('#practice-plan-list').innerHTML=list(result.next_practice_plan,'Run another role-specific assessment.');
    $('#answer-feedback').innerHTML=(result.evaluations||[]).map((item,index)=>`<article class="answer-review"><header><strong>Q${index+1}. ${esc(item.question||'')}</strong><b>${item.score ?? '—'}/100</b></header><p>${esc(item.feedback||'')}</p></article>`).join('') || '<p class="disclaimer">Question-level coaching is hidden in this UI preview.</p>';
    $('#result-disclaimer').textContent=result.disclaimer || '';
    $('#result-panel').classList.remove('hidden');
    $('#result-panel').scrollIntoView({behavior:'smooth',block:'start'});
    loadHistory();
    if(auto) toast('Assessment submitted automatically when time expired.');
  }

  function resetAssessment() {
    clearInterval(state.timerId);clearInterval(state.faceTimer);
    state.assessmentActive=false;state.finishing=false;state.current=0;state.answers=[];state.questions=[];state.session=null;state.livenessPassed=false;state.systemReady=false;
    if(state.mediaStream){state.mediaStream.getTracks().forEach(t=>t.stop());state.mediaStream=null;}
    document.body.classList.remove('secure-assessment');
    $('#result-panel').classList.add('hidden');$('#system-panel').classList.add('hidden');$('#setup-panel').classList.remove('hidden');
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
  $('#next-question')?.addEventListener('click',submitAndContinue);
  $('#restore-secure-mode')?.addEventListener('click',restoreSecureMode);
  $('#practice-again')?.addEventListener('click',resetAssessment);

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
      if(demo==='result'){ $('#setup-panel').classList.add('hidden'); renderResult(mockResult(),false); }
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