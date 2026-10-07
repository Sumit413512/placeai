(() => {
  'use strict';
  // Legacy static-mirror regression marker: Resilient role-grounded practice / resilient_baseline

  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const esc = (value = '') => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const apiErrors = window.PlaceAIApiErrors || {createError:()=>new Error('Request failed'),applyToForm:()=>{}};
  const previewMode = location.hostname === 'placeai-interview-intelligence-preview.onrender.com' || new URLSearchParams(location.search).get('preview') === '1';

  const BLUEPRINT = [
    {key:'quantitative', label:'Quantitative Aptitude', count:8, minutes:12, kind:'mcq'},
    {key:'logical', label:'Logical & Analytical Reasoning', count:8, minutes:12, kind:'mcq'},
    {key:'communication', label:'Verbal & Communication', count:6, minutes:10, kind:'mcq'},
    {key:'technical', label:'Technical Assessment · Fundamentals', count:8, minutes:14, kind:'mcq'},
    {key:'programming', label:'Technical Assessment · Programming & Debugging', count:6, minutes:14, kind:'mcq'},
    {key:'coding', label:'Technical Assessment · Coding Editor', count:2, minutes:24, kind:'code'},
    {key:'resume', label:'Resume & Project Defence', count:4, minutes:10, kind:'text'},
    {key:'behavioral', label:'Behavioural & HR', count:4, minutes:10, kind:'video'},
    {key:'role', label:'Role / JD / Company', count:2, minutes:5, kind:'text'},
    {key:'situational', label:'Situational & Decision', count:2, minutes:5, kind:'text'}
  ];
  const TOTAL_QUESTIONS = BLUEPRINT.reduce((sum, item) => sum + item.count, 0);
  const TOTAL_SECONDS = BLUEPRINT.reduce((sum, item) => sum + item.minutes * 60, 0);

  const state = {
    token:'',
    me:null,
    recordingPolicy:null,
    jobs:[],
    session:null,
    questions:[],
    answers:[],
    current:0,
    selectedOption:null,
    mediaStream:null,
    screenStream:null,
    proctorModel:null,
    proctorModelReady:false,
    proctorModelLoading:null,
    proctorModelBusy:false,
    nativeFaceDetector:null,
    localProctorTimer:null,
    mediaWatchTimer:null,
    proctorBannerTimer:null,
    signalStreaks:{candidate:0,multiple:0,phone:0},
    signalLastWarning:{candidate:0,multiple:0,phone:0},
    singleMonitorReady:true,
    screenReady:false,
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
    analysisGeneration:0,
    integrityWarnings:0,
    integrityWarningLimit:4,
    lastWarningAt:0,
    autoSubmittedIntegrity:false,
    integrityTerminationReason:'',
    proctorVisionTimer:null,
    proctorVisionBusy:false,
    faceMissStreak:0,
    multipleFaceStreak:0,
    phoneDetectionStreak:0,
    expandedSections:{},
    codeDrafts:{},
    codeExecution:{},
    hr:null,
    examDeadline:0,
    sectionDeadline:0,
    advancing:false,
    submissionSaved:false,
    recordingUrl:null
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
        <div><strong>${esc(item.label)}</strong><small>${item.minutes} min · ${item.kind === 'mcq' ? 'Objective' : item.kind === 'mixed' ? 'Objective + applied' : item.kind === 'code' ? 'Executable coding' : item.kind === 'video' ? 'Recorded spoken answers' : 'Applied response'}</small></div>
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
    let response = await fetch(path, {...options,headers,credentials:'include',signal:options.signal || AbortSignal.timeout(180000)});
    if (response.status === 401 && await refreshToken()) {
      headers.set('Authorization', `Bearer ${state.token}`);
      response = await fetch(path, {...options,headers,credentials:'include',signal:options.signal || AbortSignal.timeout(180000)});
    }
    const contentType = response.headers.get('content-type') || '';
    if(options.rawResponse && response.ok)return response;
    const data = contentType.includes('application/json') ? await response.json().catch(()=>({})) : {};
    if (!response.ok) throw apiErrors.createError(data || {}, response.status);
    return data;
  }

  async function loadJobs() {
    const jobs = previewMode ? previewJobs() : await api('/mock-interview/jobs');
    state.jobs = jobs;
    const select = $('#job-select');
    select.innerHTML = `<option value="">Select an opportunity…</option>${jobs.map(j=>{
      const demoLabel = j.is_trial_demo
      ? (j.can_start
          ? (j.free_attempts_remaining === 1 ? ' · 1 FREE DEMO ATTEMPT' : ' · INCLUDED WITH ACCESS')
          : ' · STUDENT ACCESS REQUIRED')
      : '';
      const disabled = j.is_trial_demo && !j.can_start ? ' disabled' : '';
      return `<option value="${esc(j.id)}"${disabled}>${esc(j.title)}${j.company_name ? ` · ${esc(j.company_name)}` : ''}${demoLabel}</option>`;
    }).join('')}`;
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
      $('#history-list').innerHTML = rows.length ? rows.map(row=>`<article class="history-item"><div><strong>${esc(row.job_title)}</strong><span>${esc(row.company_name || 'Company')} · ${row.created_at ? new Date(row.created_at).toLocaleString('en-IN') : 'Saved attempt'}</span>${row.id?`<button type="button" class="button secondary" data-saved-result="${esc(row.id)}">${row.overall_score===null?'Complete analysis':'View complete result'}</button>`:''}</div><div class="history-score">${row.overall_score ?? 'Pending'}</div></article>`).join('') : '<p class="disclaimer">No saved attempts yet.</p>';
    } catch (_) {
      panel.classList.remove('hidden');
      $('#history-list').textContent='Saved reports could not load. Refresh this page to try again.';
    }
  }

  const sampleBank = {
    quantitative:[
      ['A campus recruiter shortlists 72 of 120 applicants. What percentage of applicants were shortlisted?',['50%','55%','60%','65%'],'60%'],
      ['A test has 80 questions. A candidate answers 68. What fraction of the test was attempted?',['75%','80%','85%','90%'],'85%'],
      ['An internship stipend increases from 20,000 to 23,000. What is the percentage increase?',['10%','12%','15%','18%'],'15%'],
      ['Five students complete a task in 12 hours at the same rate. How many student-hours are required?',['17','48','60','72'],'60'],
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


  function demoCodingSpec(index) {
    const starter={
      python:"import sys\n\ndef solve():\n    data = sys.stdin.read().strip().split()\n    # Write your solution here\n\nif __name__ == '__main__':\n    solve()\n",
      javascript:"const fs = require('fs');\nconst input = fs.readFileSync(0, 'utf8').trim();\n// Write your solution here\n",
      java:"import java.io.*;\nimport java.util.*;\n\npublic class Main {\n    public static void main(String[] args) throws Exception {\n        // Write your solution here\n    }\n}\n",
      cpp:"#include <bits/stdc++.h>\nusing namespace std;\nint main(){ ios::sync_with_stdio(false); cin.tie(nullptr); /* solution */ return 0; }\n",
      c:"#include <stdio.h>\nint main(void){ /* solution */ return 0; }\n"
    };
    const languages=[
      {key:'python',label:'Python 3.14'},{key:'javascript',label:'JavaScript (Node.js 22)'},
      {key:'java',label:'Java 17'},{key:'cpp',label:'C++ (GCC 14)'},{key:'c',label:'C (GCC 14)'}
    ];
    if(index===0)return {
      question:'Remove duplicates while preserving first occurrence. Input N and then N integers. Print distinct integers in first-occurrence order.',
      spec:{allowed_languages:languages,starter_code:starter,constraints:['0 <= N <= 100000','Preserve first occurrence order.'],sample_tests:[{input:'5\n1 2 2 3 1\n',output:'1 2 3'},{input:'5\n4 4 4 4 4\n',output:'4'}],test_case_count:10,hidden_test_count:7}
    };
    return {
      question:'Find the length of the longest consecutive integer sequence in an unsorted array. Aim for O(N) expected time.',
      spec:{allowed_languages:languages,starter_code:starter,constraints:['0 <= N <= 100000','Target expected complexity: O(N).'],sample_tests:[{input:'6\n100 4 200 1 3 2\n',output:'4'},{input:'6\n1 2 0 1 3 4\n',output:'5'}],test_case_count:10,hidden_test_count:7}
    };
  }

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
        if(section.key==='coding'){
          const demo=demoCodingSpec(i);
          questions.push({question_id:id++,section:'coding',category:section.label,difficulty:i===0?'Intermediate':'Advanced',question:demo.question,answer_type:'code',coding_spec:demo.spec,options:[]});
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
      answer_type:q.answer_type==='video' ? 'video' : Array.isArray(q.options) && q.options.length ? 'mcq' : (q.answer_type || 'text'),
      options:q.answer_type==='video' ? [] : Array.isArray(q.options) ? q.options : []
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
    ctx.clearRect(0,0,width,height);
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
    const currentQuestion=state.questions[state.current];

    nav.innerHTML=BLUEPRINT.map(function(section){
      const rows=state.questions.map(function(q,index){return {q:q,index:index};}).filter(function(row){return row.q.section===section.key;});
      if(!rows.length)return '';
      const isExpanded=Boolean(state.expandedSections[section.key]);
      const isCurrentSection=Boolean(currentQuestion && currentQuestion.section===section.key);
      const chips=rows.map(function(row){
        const isCurrent=row.index===state.current;
        const attempted=isAttemptedAnswer(state.answers[row.q.question_id-1]);
        const status=attempted?'attempted':isCurrent?'current':'unattempted';
        const currentClass=isCurrent?' is-current':'';
        const label='Question '+row.q.question_id+' · '+(attempted?'attempted':isCurrent?'currently attempting':'not attempted');
        return '<span class="palette-question '+status+currentClass+' locked" aria-label="'+esc(label)+'" title="'+esc(label)+'">'+row.q.question_id+'</span>';
      }).join('');
      const done=rows.filter(function(row){return isAttemptedAnswer(state.answers[row.q.question_id-1]);}).length;
      return '<section class="palette-section '+(isCurrentSection?'active-section':'')+' '+(isExpanded?'expanded':'collapsed')+'">'
        +'<button class="palette-section-toggle" type="button" data-section-toggle="'+esc(section.key)+'" aria-expanded="'+(isExpanded?'true':'false')+'">'
        +'<span class="palette-section-copy"><strong>'+esc(section.label)+'</strong><small>'+done+' attempted · '+rows.length+' questions</small></span>'
        +'<span class="palette-section-meta"><b>'+done+'/'+rows.length+'</b><i class="palette-chevron" aria-hidden="true">⌄</i></span>'
        +'</button>'
        +'<div class="palette-question-wrap" '+(isExpanded?'':'hidden')+'><div class="palette-question-grid">'+chips+'</div></div>'
        +'</section>';
    }).join('');
  }

  function toggleNavigatorSection(sectionKey) {
    if(!sectionKey)return;
    state.expandedSections[sectionKey]=!state.expandedSections[sectionKey];
    renderSectionNav();
  }


  function parseStoredCodeAnswer(answer) {
    try {
      const data=JSON.parse(answer||'{}');
      if(data && typeof data==='object' && typeof data.language==='string' && typeof data.source_code==='string') return data;
    } catch {}
    return null;
  }

  function codeDraftBucket(questionId) {
    state.codeDrafts[questionId]=state.codeDrafts[questionId]||{};
    return state.codeDrafts[questionId];
  }

  function renderCodeExecution(data) {
    const panel=$('#code-execution-panel');
    if(!panel)return;
    if(!data){
      panel.innerHTML='<div class="code-empty-state">Run the sample tests to see compilation and execution results.</div>';
      return;
    }
    const passed=Number(data.passed||0);
    const total=Number(data.total||0);
    const compile=Boolean(data.compile_success);
    const rows=(data.results||[]).map(function(result){
      const status=result.passed?'passed':'failed';
      const visibility=result.visibility==='hidden'?'Hidden':'Sample';
      let detail='';
      if(result.visibility!=='hidden'){
        if(result.compile_output) detail='<pre>'+esc(result.compile_output)+'</pre>';
        else if(result.stderr) detail='<pre>'+esc(result.stderr)+'</pre>';
        else if(result.stdout) detail='<pre>Output: '+esc(result.stdout)+'</pre>';
      }
      return '<article class="code-test-result '+status+'"><div><strong>'+visibility+' test '+result.index+'</strong><span>'+esc(result.status||'')+'</span></div><b>'+(result.passed?'Passed':'Failed')+'</b>'+detail+'</article>';
    }).join('');
    panel.innerHTML='<div class="code-run-summary '+(compile?'compile-ok':'compile-fail')+'">'
      +'<div><span>'+(compile?'Compilation / execution completed':'Compilation / runtime failed')+'</span><strong>'+passed+' / '+total+' tests passed</strong></div>'
      +'<b>'+Math.round(total?passed/total*100:0)+'%</b></div>'
      +'<div class="code-test-results">'+rows+'</div>';
  }

  async function runCurrentCode(mode) {
    const q=state.questions[state.current];
    if(!q || q.answer_type!=='code')return;
    const language=$('#code-language')?.value||'';
    const source=($('#code-editor')?.value||'').trimEnd();
    if(!language || !source.trim()){toast('Choose a language and enter code first.','error');return;}
    const runButton=$('#run-code');
    const submitButton=$('#submit-code-tests');
    if(runButton)runButton.disabled=true;
    if(submitButton)submitButton.disabled=true;
    $('#code-run-status').textContent=mode==='submit'?'Submitting against sample + hidden tests…':'Compiling and running sample tests…';
    try{
      if(previewMode){
        await new Promise(function(resolve){setTimeout(resolve,500);});
        const samples=q.coding_spec?.sample_tests||[];
        const data={compile_success:true,passed:0,total:samples.length,sample_count:samples.length,hidden_count:0,results:samples.map(function(_,i){return {index:i+1,visibility:'sample',passed:false,status:'Preview mode — live execution requires a signed-in student session',stdout:'',stderr:'',compile_output:''};})};
        state.codeExecution[q.question_id]=data;
        renderCodeExecution(data);
      }else{
        const data=await api('/mock-interview/code/run',{method:'POST',body:JSON.stringify({
          interview_id:state.session.interview_id,
          question_id:q.question_id,
          language:language,
          source_code:source,
          mode:mode
        })});
        state.codeExecution[q.question_id]=data;
        renderCodeExecution(data);
        toast(data.compile_success
          ? data.passed+' of '+data.total+' test cases passed.'
          : 'Compilation failed. Review the compiler output.\n', data.passed===data.total&&data.total>0?'':'error');
      }
    }catch(error){
      renderCodeExecution({compile_success:false,passed:0,total:0,results:[{index:1,visibility:'sample',passed:false,status:error.message||'Execution unavailable',stdout:'',stderr:'',compile_output:''}]});
      toast(error.message||'Code execution failed.','error');
    }finally{
      if(runButton)runButton.disabled=false;
      if(submitButton)submitButton.disabled=false;
      $('#code-run-status').textContent=mode==='submit'?'Code submission complete':'Sample test run complete';
    }
  }

  function renderAnswerArea(question) {
    const area=$('#answer-area');
    area.className='answer-area '+(question.answer_type==='mcq'?'mcq-answer-area':'text-answer-area');
    area.onclick=null;
    state.selectedOption=null;
    const existing=state.answers[question.question_id-1];

    if(question.answer_type==='mcq'){
      const options=Array.isArray(question.options)?question.options.filter(function(option){return typeof option==='string'&&option.trim();}).slice(0,4):[];
      if(options.length!==4){
        area.innerHTML='<div class="answer-load-error"><strong>Question options unavailable</strong><span>This objective item did not load correctly. The assessment has been paused to protect scoring integrity.</span></div>';
        $('#next-question').disabled=true;
        $('#save-question').disabled=true;
        logIntegrity('mcq_options_invalid','Objective question did not contain exactly four selectable options.','system',null);
        return;
      }
      $('#next-question').disabled=false;
      $('#save-question').disabled=false;

      if(existing?.answer){
        const existingIndex=options.findIndex(function(option){return option===existing.answer;});
        if(existingIndex>=0) state.selectedOption=existingIndex;
      }

      area.innerHTML='<div class="answer-options" role="radiogroup" aria-label="Answer options">'
        +options.map(function(option,i){
          const letter=String.fromCharCode(65+i);
          return '<button class="option-button" type="button" role="radio" aria-checked="false" aria-label="Option '+letter+': '+esc(option)+'" data-option-index="'+i+'">'
            +'<span class="option-key">'+letter+'</span>'
            +'<span class="option-text">'+esc(option)+'</span>'
            +'<span class="option-select-indicator" aria-hidden="true"></span>'
            +'</button>';
        }).join('')
        +'</div>';

      $$('.option-button',area).forEach(function(button,i){
        if(state.selectedOption===i){
          button.classList.add('selected');
          button.setAttribute('aria-checked','true');
        }
      });

      area.onclick=function(event){
        const button=event.target.closest('.option-button');
        if(!button||!area.contains(button))return;
        const i=Number(button.dataset.optionIndex);
        if(!Number.isInteger(i)||i<0||i>=options.length)return;
        $$('.option-button',area).forEach(function(x){
          x.classList.remove('selected');
          x.setAttribute('aria-checked','false');
        });
        button.classList.add('selected');
        button.setAttribute('aria-checked','true');
        state.selectedOption=i;
        $('#autosave-state').textContent='Option '+String.fromCharCode(65+i)+' selected · not saved yet';
      };
      return;
    }

    if(question.answer_type==='code'){
      const spec=question.coding_spec||{};
      const languages=Array.isArray(spec.allowed_languages)?spec.allowed_languages:[];
      const stored=existing?.answer?parseStoredCodeAnswer(existing.answer):null;
      const initialLanguage=(stored&&languages.some(x=>x.key===stored.language)?stored.language:(languages[0]?.key||'python'));
      const bucket=codeDraftBucket(question.question_id);
      if(stored?.source_code) bucket[stored.language]=stored.source_code;
      const starter=(spec.starter_code&&spec.starter_code[initialLanguage])||'';
      const initialCode=bucket[initialLanguage]??starter;
      let activeLanguage=initialLanguage;
      area.innerHTML='<div class="code-workspace">'
        +'<div class="code-toolbar"><label>Language<select id="code-language">'+languages.map(function(lang){return '<option value="'+esc(lang.key)+'">'+esc(lang.label)+'</option>';}).join('')+'</select></label>'
        +'<div class="code-actions"><button id="run-code" type="button" class="button secondary">Run Code</button><button id="submit-code-tests" type="button" class="button primary">Submit Code</button></div></div>'
        +'<div class="code-editor-shell"><div class="code-editor-title"><span>Solution editor</span><small id="code-run-status">Not run yet</small></div><div class="code-editor-frame"><pre id="code-line-numbers" class="code-line-numbers" aria-hidden="true">1</pre><textarea id="code-editor" class="code-editor" aria-label="Code editor" spellcheck="false" autocapitalize="off" autocomplete="off"></textarea></div></div>'
        +'<div class="code-problem-meta"><div><strong>Constraints</strong><ul>'+(spec.constraints||[]).map(function(x){return '<li>'+esc(x)+'</li>';}).join('')+'</ul></div><div><strong>Sample tests</strong>'+(spec.sample_tests||[]).map(function(test,i){return '<article class="sample-case"><span>Sample '+(i+1)+'</span><pre>Input\n'+esc(test.input||'')+'\nExpected\n'+esc(test.output||'')+'</pre></article>';}).join('')+'</div></div>'
        +'<div id="code-execution-panel" class="code-execution-panel"></div>'
        +'</div>';
      $('#code-language').value=initialLanguage;
      $('#code-editor').value=initialCode;
      const updateCodeLineNumbers=function(){
        const editor=$('#code-editor');
        const gutter=$('#code-line-numbers');
        if(!editor||!gutter)return;
        const count=Math.max(1,editor.value.split('\n').length);
        gutter.textContent=Array.from({length:count},function(_,i){return String(i+1);}).join('\n');
        gutter.scrollTop=editor.scrollTop;
      };
      $('#code-editor').addEventListener('input',function(){bucket[$('#code-language').value]=this.value;updateCodeLineNumbers();$('#autosave-state').textContent='Code changed · not saved yet';});
      $('#code-editor').addEventListener('scroll',function(){const gutter=$('#code-line-numbers');if(gutter)gutter.scrollTop=this.scrollTop;});
      $('#code-editor').addEventListener('keydown',function(event){
        if(event.key!=='Tab')return;
        event.preventDefault();
        const start=this.selectionStart;
        const end=this.selectionEnd;
        const indent='    ';
        this.setRangeText(indent,start,end,'end');
        bucket[$('#code-language').value]=this.value;
        updateCodeLineNumbers();
        $('#autosave-state').textContent='Code changed · not saved yet';
      });
      updateCodeLineNumbers();
      $('#code-language').addEventListener('change',function(){
        const editor=$('#code-editor');
        bucket[activeLanguage]=editor.value;
        const lang=this.value;
        activeLanguage=lang;
        editor.value=bucket[lang]??((spec.starter_code&&spec.starter_code[lang])||'');
        updateCodeLineNumbers();
        $('#autosave-state').textContent='Language changed · code not saved yet';
      });
      $('#run-code').addEventListener('click',function(){runCurrentCode('run');});
      $('#submit-code-tests').addEventListener('click',function(){runCurrentCode('submit');});
      renderCodeExecution(state.codeExecution[question.question_id]||null);
      $('#next-question').disabled=false;
      $('#save-question').disabled=false;
      return;
    }

    $('#next-question').disabled=false;
    $('#save-question').disabled=false;
    area.innerHTML='<label class="answer-field">Your response<textarea id="current-answer" class="secure-textarea" maxlength="5000" autocomplete="off" spellcheck="true" placeholder="Write a concise, evidence-based response."></textarea></label>';
    if(existing?.answer) $('#current-answer').value=existing.answer;
  }

  function hrStatus(message) {
    const node=$('#hr-recording-status');
    if(node)node.textContent=message;
  }

  async function uploadHRChunks() {
    const hr=state.hr;
    if(!hr)return;
    if(hr.uploadPromise)return hr.uploadPromise;
    hr.uploadPromise=(async()=>{
      while(hr.uploaded<hr.chunks.length){
        const index=hr.uploaded;
        await api(`/mock-interview/${state.session.interview_id}/hr/chunks/${index}`,{
          method:'PUT',headers:{'Content-Type':'application/octet-stream'},body:hr.chunks[index],signal:AbortSignal.timeout(30000)
        });
        // Keep only unsaved media in memory. A retry uses the same sequence and bytes.
        hr.chunks[index]=null;
        hr.uploaded++;
      }
      hr.uploadError='';
    })().catch(()=>{
      hr.uploadError='Recording upload is waiting for a connection. Keep this page open; saved parts are safe.';
    }).finally(()=>{hr.uploadPromise=null;});
    return hr.uploadPromise;
  }

  async function beginHRVideo() {
    if(state.hr?.starting || state.hr?.recorder || state.finishing)return;
    const hr=state.hr || (state.hr={chunks:[],uploaded:0,bytes:0,transitioning:false,uploadError:'',error:'',trackListeners:[]});
    hr.starting=true;
    $('#next-question').disabled=true;
    $('#save-question').disabled=true;
    $('#retry-hr-recording')?.classList.add('hidden');
    try {
      if(!window.MediaRecorder)throw new Error('This browser cannot record the HR section. Use a current Chrome, Edge, Firefox or Safari browser.');
      const tracks=state.mediaStream?.getTracks() || [];
      if(!tracks.some(t=>t.kind==='audio' && t.readyState==='live') || !tracks.some(t=>t.kind==='video' && t.readyState==='live'))throw new Error('A working camera and microphone are required for spoken answers.');
      const mime=['video/webm;codecs=vp8,opus','video/webm','video/mp4'].find(type=>MediaRecorder.isTypeSupported(type));
      if(!mime)throw new Error('No supported video recording format is available.');
      // Prepare the recorder before starting the server clock. A failed request is safe to retry.
      const recorder=new MediaRecorder(state.mediaStream,{mimeType:mime,videoBitsPerSecond:240000,audioBitsPerSecond:32000});
      const response=await api(`/mock-interview/${state.session.interview_id}/hr/start`,{method:'POST',body:JSON.stringify({mime_type:mime.split(';')[0],consent:$('#consent-check').checked,processor:state.recordingPolicy?.processor || 'google'})});
      if(response.status!=='recording' || response.chunk_count)throw new Error('This recording has already started in another session. Keep its original exam tab open to finish uploading.');
      if(state.finishing)return;
      hr.server=response;
      hr.recorder=recorder;
      hr.error='';
      recorder.ondataavailable=event=>{
        if(!event.data.size)return;
        hr.bytes+=event.data.size;
        if(hr.bytes>response.max_bytes){
          hr.error='The recording reached its size limit. The saved recording will be submitted with your exam.';
          hrStatus(hr.error);
          if(recorder.state!=='inactive')recorder.stop();
          return;
        }
        for(let pos=0;pos<event.data.size;pos+=512*1024)hr.chunks.push(event.data.slice(pos,pos+512*1024));
        uploadHRChunks();
      };
      recorder.onerror=()=>{
        hr.error='Camera recording was interrupted. Your captured answers will be saved; keep this page open.';
        hrStatus(hr.error);
      };
      recorder.onstop=()=>{
        if(!hr.stopping && state.assessmentActive && !state.finishing){
          hr.error=hr.error || 'The recording ended unexpectedly. Your captured answers will be submitted for review.';
          logIntegrity('hr_recording_interrupted','The HR recording ended before the section finished.','browser');
          finishAssessment(true);
        }
      };
      tracks.forEach(track=>{
        const ended=()=>{
          hr.error='Your camera or microphone stopped. Your captured answers will be submitted for review.';
          hrStatus(hr.error);
          if(state.assessmentActive && !state.finishing)finishAssessment(true);
        };
        const muted=()=>hrStatus('Camera or microphone signal interrupted. Check your device; the answer timer continues.');
        track.addEventListener('ended',ended);
        track.addEventListener('mute',muted);
        hr.trackListeners.push([track,'ended',ended],[track,'mute',muted]);
      });
      if(window.speechSynthesis)speechSynthesis.cancel();
      recorder.start(4000);
      hrStatus('Recording · camera and microphone on · answers saved privately');
      hr.retryTimer=setInterval(uploadHRChunks,5000);
      setHRQuestionDeadline(response);
      $('#next-question').disabled=false;
      $('#start-hr-recording')?.classList.add('hidden');
      if($('#repeat-hr-question'))$('#repeat-hr-question').disabled=true;
    } catch(error) {
      hr.error=error.message;
      if(hr.recorder?.state==='inactive')hr.recorder=null;
      hrStatus(error.message);
      $('#retry-hr-recording')?.classList.remove('hidden');
      toast(error.message,'error');
    } finally {hr.starting=false;}
  }

  function setHRQuestionDeadline(response) {
    const now=Date.now();
    const serverTime=Date.parse(response.server_time);
    const questionTime=Date.parse(response.question_deadline_at);
    const sectionTime=Date.parse(response.deadline_at);
    if(!Number.isFinite(serverTime) || !Number.isFinite(questionTime) || !Number.isFinite(sectionTime))throw new Error('The answer timer could not synchronize. Retry to continue.');
    state.hr.questionDeadline=now+Math.max(0,questionTime-serverTime);
    state.sectionDeadline=now+Math.max(0,sectionTime-serverTime);
    state.sectionRemaining=Math.max(0,Math.ceil((state.sectionDeadline-now)/1000));
  }

  function cancelQuestionReading() {
    state.narrationGeneration=(state.narrationGeneration || 0)+1;
    if(window.speechSynthesis)speechSynthesis.cancel();
  }

  async function readQuestionBeforeAnswer(q, record) {
    cancelQuestionReading();
    const generation=state.narrationGeneration;
    const spec=q.coding_spec || {};
    const examples=(spec.sample_tests || []).map((sample,i)=>'Example '+(i+1)+'. Input. '+sample.input+'. Expected output. '+sample.output).join(' ');
    const text='Reading question. '+q.question+(q.options?.length?' Options. '+q.options.map((v,i)=>'Option '+(i+1)+'. '+v).join(' '):'')+' '+(spec.constraints || []).join('. ')+' '+examples+'. '+(record?'Record your answer.':'You may answer now.');
    if(!window.speechSynthesis)throw new Error('Question reading is unavailable in this browser. Read the displayed question, then select Start answer.');
    // Short utterances avoid browser truncation of long questions. Every
    // character is included, and the microphone recorder starts only on end.
    for(let pos=0;pos<text.length;){
      if(state.narrationGeneration!==generation || !state.assessmentActive)return;
      let end=Math.min(text.length,pos+180);
      if(end<text.length){const space=text.lastIndexOf(' ',end);if(space>pos)end=space+1;}
      const chunk=text.slice(pos,end);pos=end;
      await new Promise((resolve,reject)=>{
        const utterance=new SpeechSynthesisUtterance(chunk);utterance.lang='en-IN';utterance.rate=0.95;
        const timer=setTimeout(()=>{if(state.narrationGeneration!==generation){resolve();return;}speechSynthesis.cancel();reject(new Error('Question reading was interrupted. Read the displayed question, then select Start answer.'));},60000);
        utterance.onend=()=>{clearTimeout(timer);resolve();};
        utterance.onerror=()=>{clearTimeout(timer);if(state.narrationGeneration!==generation){resolve();return;}reject(new Error('Question reading was interrupted. Read the displayed question, then select Start answer.'));};
        speechSynthesis.speak(utterance);
      });
    }
    if(record && state.narrationGeneration===generation && state.assessmentActive)await beginQuestionAnswer(q);
  }

  async function uploadQuestionAnswer(clip) {
    if(clip.uploading)return clip.uploading;
    clip.uploading=(async()=>{
      while(clip.uploaded<clip.chunks.length){
        const sequence=clip.uploaded;
        await api(`/mock-interview/${clip.interviewId}/answers/${clip.questionId}/chunks/${sequence}`,{method:'PUT',headers:{'Content-Type':'application/octet-stream'},body:clip.chunks[sequence]});
        clip.chunks[sequence]=null;clip.uploaded++;
      }
    })().finally(()=>{clip.uploading=null;});
    return clip.uploading;
  }

  async function drainQuestionAnswerUploads(clip) {
    // MediaRecorder may emit its final dataavailable event while an earlier
    // upload promise is settling. Re-check the queue after every awaited
    // upload so submission can never seal before that final chunk is saved.
    while(clip.uploading || clip.uploaded<clip.chunks.length)await uploadQuestionAnswer(clip);
  }

  function beginQuestionAnswer(q) {
    if(state.answerStartTask)return state.answerStartTask;
    state.answerStartTask=startQuestionRecorder(q).finally(()=>{state.answerStartTask=null;});
    return state.answerStartTask;
  }

  async function startQuestionRecorder(q) {
    if(state.answerClip?.questionId===q.question_id || state.answerStarting || !state.assessmentActive)return;
    state.answerStarting=true;
    try {
      cancelQuestionReading();
      if(!window.MediaRecorder)throw new Error('This browser cannot record this answer. Use a supported browser.');
      const audioOnly=q.response_mode==='audio';
      const tracks=state.mediaStream?.getTracks().filter(t=>!audioOnly || t.kind==='audio') || [];
      if(!tracks.some(t=>t.kind==='audio' && t.readyState==='live') || !audioOnly && !tracks.some(t=>t.kind==='video' && t.readyState==='live'))throw new Error('Camera or microphone is unavailable. Restore your devices to record.');
      const formats=audioOnly?['audio/webm;codecs=opus','audio/webm','audio/mp4']:['video/webm;codecs=vp8,opus','video/webm','video/mp4'];
      const mime=formats.find(t=>MediaRecorder.isTypeSupported(t));
      if(!mime)throw new Error('This browser cannot record this answer. Use a supported browser.');
      const recorder=new MediaRecorder(new MediaStream(tracks),{mimeType:mime,audioBitsPerSecond:48000,...(!audioOnly?{videoBitsPerSecond:250000}:{})});
      const server=await api(`/mock-interview/${state.session.interview_id}/answers/${q.question_id}/start`,{method:'POST',body:JSON.stringify({mime_type:mime.split(';')[0],consent:$('#consent-check').checked})});
      if(server.status!=='recording')throw new Error('This answer has already been submitted.');
      const clip={questionId:q.question_id,interviewId:state.session.interview_id,recorder,chunks:[],uploaded:0,bytes:0,submitted:false,
        deadline:Date.now()+Math.max(0,Date.parse(server.question_deadline_at)-Date.parse(server.server_time))};
      recorder.ondataavailable=event=>{
        if(!event.data.size)return;
        clip.bytes+=event.data.size;
        if(clip.bytes>server.max_bytes){clip.error='The answer reached its recording size limit. Finish this answer now.';if(recorder.state!=='inactive')recorder.stop();return;}
        for(let pos=0;pos<event.data.size;pos+=512*1024)clip.chunks.push(event.data.slice(pos,pos+512*1024));
        uploadQuestionAnswer(clip).catch(error=>{clip.error=error.message;});
      };
      recorder.onerror=()=>{clip.error='Recording was interrupted. Finish this answer to preserve captured media.';};
      recorder.start(4000);
      state.answerClip=clip;
      $('#spoken-answer-status').textContent='Recording your answer · microphone on'+(audioOnly?'':' · camera on');
      $('#start-spoken-answer').classList.add('hidden');
      $('#next-question').disabled=false;
    }catch(error){$('#spoken-answer-status').textContent=error.message;$('#start-spoken-answer')?.classList.remove('hidden');}
    finally{state.answerStarting=false;}
  }

  async function finishQuestionAnswer() {
    cancelQuestionReading();
    if(state.answerStartTask)await state.answerStartTask;
    const clip=state.answerClip;
    if(!clip || clip.submitted)return;
    if(clip.finishing)return clip.finishing;
    clip.finishing=(async()=>{
      if(clip.recorder.state!=='inactive')await new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>reject(new Error('The recording is still closing. Keep this page open and retry.')),10000);
        clip.recorder.addEventListener('stop',()=>{clearTimeout(timer);resolve();},{once:true});clip.recorder.stop();
      });
      await drainQuestionAnswerUploads(clip);
      if(clip.uploaded!==clip.chunks.length)throw new Error('The spoken answer has not finished uploading. Keep this page open and retry.');
      await api(`/mock-interview/${clip.interviewId}/answers/${clip.questionId}/submit`,{method:'POST',body:JSON.stringify({chunks:clip.uploaded})});
      clip.submitted=true;
      state.answers[clip.questionId-1]={question_id:clip.questionId,answer:clip.uploaded?'[Spoken answer submitted]':'[No response submitted: no recording captured]'};
    })().finally(()=>{clip.finishing=null;});
    return clip.finishing;
  }

  function renderSpokenAnswer(q) {
    state.answerClip=null;
    $('#answer-area').innerHTML='<div class="answer-field"><strong>'+(q.response_mode==='video'?'HR camera and voice answer':'Spoken answer')+'</strong><p>Listen to the question, then answer aloud. This question has its own private recording and up to 2 minutes 30 seconds of answer time.</p><p id="spoken-answer-status" role="status">Reading question…</p><button id="start-spoken-answer" type="button" class="button secondary hidden">Start answer</button>'+(q.response_mode==='video'?'<video id="hr-answer-preview" autoplay playsinline muted aria-label="Your live HR camera preview"></video>':'')+'</div>';
    const preview=$('#hr-answer-preview');if(preview){preview.srcObject=state.mediaStream;preview.play().catch(()=>{});}
    $('#start-spoken-answer').onclick=()=>beginQuestionAnswer(q);
    $('#save-question').disabled=true;$('#next-question').disabled=true;
    readQuestionBeforeAnswer(q,true).catch(error=>{
      if(state.questions[state.current]?.question_id!==q.question_id || !state.assessmentActive)return;
      $('#spoken-answer-status').textContent=error.message;$('#start-spoken-answer').classList.remove('hidden');
    });
  }

  function speakHRQuestion() {
    if(!window.speechSynthesis || state.hr?.recorder?.state==='recording' || state.questions[state.current]?.answer_type!=='video')return;
    speechSynthesis.cancel();
    const speech=new SpeechSynthesisUtterance(state.questions[state.current].question);
    speech.lang='en-IN';speech.rate=0.95;
    speechSynthesis.speak(speech);
  }

  async function stopHRVideo() {
    const hr=state.hr;
    if(!hr?.recorder)return;
    if(window.speechSynthesis)speechSynthesis.cancel();
    hr.stopping=true;
    (hr.trackListeners || []).forEach(([track,event,listener])=>track.removeEventListener(event,listener));
    hr.trackListeners=[];
    if(hr.recorder.state!=='inactive')await new Promise((resolve,reject)=>{
      const timeout=setTimeout(()=>reject(new Error('The recording is still closing. Keep this page open and retry submission.')),10000);
      hr.recorder.addEventListener('stop',()=>{clearTimeout(timeout);resolve();},{once:true});
      hr.recorder.stop();
    });
  }

  async function submitHRVideo() {
    const hr=state.hr;
    if(!hr?.recorder || hr.submitted)return;
    await stopHRVideo();
    await uploadHRChunks();
    if(hr.uploaded!==hr.chunks.length)throw new Error(hr.uploadError || 'The HR recording has not finished uploading. Keep this page open and retry.');
    await api(`/mock-interview/${state.session.interview_id}/hr/submit`,{method:'POST',body:JSON.stringify({chunks:hr.uploaded})});
    hr.submitted=true;
    clearInterval(hr.retryTimer);
  }

  async function advanceHRQuestion() {
    const hr=state.hr;
    if(!hr?.recorder || hr.transitioning || state.finishing)return false;
    hr.transitioning=true;$('#next-question').disabled=true;
    try {
      const response=await api(`/mock-interview/${state.session.interview_id}/hr/advance`,{method:'POST',body:JSON.stringify({question_id:state.questions[state.current].question_id})});
      hr.server=response;
      if(response.status==='recorded')await stopHRVideo();
      else setHRQuestionDeadline(response);
      return true;
    }catch(error){toast(error.message,'error');return false;}
    finally{hr.transitioning=false;$('#next-question').disabled=state.finishing;}
  }

  function renderQuestion() {
    const q=state.questions[state.current];
    if(!q) return;
    if(!(q.section in state.expandedSections)) state.expandedSections[q.section]=true;
    const info=currentSectionInfo(q);
    $('#section-label').textContent=info.label;
    $('#question-progress').textContent=`Question ${state.current+1} of ${state.questions.length}`;
    $('#question-section').textContent=info.label;
    $('#question-difficulty').textContent=q.difficulty || 'Mixed';
    $('#question-guidance').textContent=q.answer_type==='mcq'
      ? 'Select one option. Use Save answer to keep it on the current question, or Save & Next to lock it and move forward.'
      : q.answer_type==='code'
        ? 'Technical coding question: write a complete program, use Run Code for sample tests, then Submit Code for sample + hidden tests before Save & Next.'
        : 'Respond using clear reasoning and evidence. After submission this question is permanently closed.';
    const stage=$('.question-stage');
    if(stage) stage.scrollTop=0;
    $('#question-text').textContent=q.question;
    $('#question-watermark').textContent=`${state.candidateLabel} · Q${state.current+1}`;
    if(q.response_mode)renderSpokenAnswer(q);
    else if(q.answer_type==='video') {
      $('#answer-area').innerHTML='<div class="answer-field"><strong>HR video answer</strong><p>Answer aloud in English. One private video captures all four HR answers. Each answer has up to 2 minutes 30 seconds; the next question opens automatically when its time expires.</p><p id="hr-recording-status" role="status">Camera and microphone ready. Read the question, then start your answer.</p><button type="button" id="start-hr-recording" class="button primary">Start HR recording</button><button type="button" id="repeat-hr-question" class="button secondary">Read question aloud</button><button type="button" id="retry-hr-recording" class="button secondary hidden">Retry recording setup</button><video id="hr-answer-preview" autoplay playsinline muted aria-label="Your live HR camera preview"></video></div>';
      $('#repeat-hr-question').onclick=speakHRQuestion;
      $('#retry-hr-recording').onclick=beginHRVideo;
      const preview=$('#hr-answer-preview');
      preview.srcObject=state.mediaStream;
      preview.play().catch(()=>{});
      const recording=state.hr?.recorder?.state==='recording';
      if(recording)hrStatus('Recording · camera and microphone on · answer timer continues');
      $('#start-hr-recording').classList.toggle('hidden',recording);
      $('#start-hr-recording').onclick=beginHRVideo;
      $('#repeat-hr-question').disabled=recording;
      $('#next-question').disabled=!recording;
      $('#save-question').disabled=true;
    } else {
      renderAnswerArea(q);
      if(q.narration_enabled)readQuestionBeforeAnswer(q,false).catch(()=>{if(state.assessmentActive)toast('Question reading is unavailable. Use the full question displayed on screen.','error');});
    }
    renderSectionNav();
    $('#autosave-state').textContent=isAttemptedAnswer(state.answers[q.question_id-1])?'Answer saved':'Response not saved';
    $('#next-question').textContent=q.response_mode || q.answer_type==='video'?'Finish answer & Next':state.current===state.questions.length-1?'Save & Submit':'Save & Next';
    const sectionFirst=state.questions.findIndex(x=>x.section===q.section);
    if(state.current===sectionFirst || state.sectionRemaining<=0){
      state.sectionRemaining=info.minutes*60;
      state.sectionDeadline=Date.now()+state.sectionRemaining*1000;
    }
    updateTimers();
  }

  function answerCurrentQuestion() {
    const q=state.questions[state.current];
    let answer='';
    if(q.response_mode){
      if(!state.answerClip){toast('Wait for the question reading and recording to start.','error');return false;}
      answer='[Spoken answer submitted]';
    } else if(q.answer_type==='video') {
      if(!state.hr?.recorder){toast('The HR recording has not started.','error');return false;}
      answer='[HR video response submitted]';
    } else if(q.answer_type==='mcq') {
      if(state.selectedOption===null) { toast('Select an option before continuing.','error'); return false; }
      answer=q.options[state.selectedOption];
    } else if(q.answer_type==='code') {
      const language=$('#code-language')?.value||'';
      const source=($('#code-editor')?.value||'').trimEnd();
      if(!language || !source.trim()) { toast('Enter a coding solution before continuing.','error'); return false; }
      answer=JSON.stringify({language:language,source_code:source});
      codeDraftBucket(q.question_id)[language]=source;
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

  async function expireCurrentSection() {
    if(state.advancing || state.finishing)return;
    state.advancing=true;
    try {
    if(state.questions[state.current]?.response_mode)await finishQuestionAnswer();
    else if(state.questions[state.current]?.answer_type==='video'){answerCurrentQuestion();await stopHRVideo();}
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
    } finally {state.advancing=false;}
  }

  function fillUnansweredResponses(reason) {
    state.questions.forEach(function(_,index){markQuestionUnanswered(index,reason||'[No response submitted before assessment ended]');});
  }

  function startTimer() {
    clearInterval(state.timerId);
    state.timerId=setInterval(()=>{
      if(!state.assessmentActive || state.finishing || state.autoSubmittedIntegrity) return;
      state.totalRemaining=Math.max(0,Math.ceil((state.examDeadline-Date.now())/1000));
      state.sectionRemaining=Math.max(0,Math.ceil((state.sectionDeadline-Date.now())/1000));
      updateTimers();
      // The whole-exam deadline takes priority over advancing an HR answer.
      if(state.totalRemaining<=0){
        finishAssessment(true);
        return;
      }
      if(state.answerClip && !state.answerClip.submitted && Date.now()>=state.answerClip.deadline && !state.advancing){submitAndContinue().catch(error=>toast(error.message,'error'));return;}
      if(state.sectionRemaining<=0 && !state.hr?.transitioning){
        logIntegrity('section_time_expired','Section time expired; remaining unanswered items in this section were closed automatically.');
        expireCurrentSection();
        return;
      }
      if(state.questions[state.current]?.answer_type==='video' && state.hr?.questionDeadline){
        const left=Math.max(0,Math.ceil((state.hr.questionDeadline-Date.now())/1000));
        const status=$('#hr-recording-status');
        const muted=state.mediaStream?.getTracks().some(track=>track.muted || !track.enabled);
        if(status)status.textContent=state.hr.error || state.hr.uploadError || (muted?'Camera or microphone signal interrupted. Check your device; the answer timer continues.':`Recording · ${formatTime(left)} for this answer · ${state.hr.uploaded} parts saved privately`);
        if(left<=0 && !state.hr.transitioning){submitAndContinue();return;}
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
      showProctorWarning(
        title||'Integrity warning',
        detail+' Warning '+state.integrityWarnings+' of '+state.integrityWarningLimit+'.'
      );
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

  async function ensureProctorModel() {
    if(state.proctorModelReady && state.proctorModel) return true;
    if(state.proctorModelLoading) return state.proctorModelLoading;
    state.proctorModelLoading=(async function(){
      try{
        setCheck('proctor',null,'Loading model');
        if(!window.tf || !window.cocoSsd) throw new Error('On-device proctor runtime did not load');
        await window.tf.ready();
        state.proctorModel=await window.cocoSsd.load({base:'lite_mobilenet_v2'});
        state.proctorModelReady=Boolean(state.proctorModel);
        setCheck('proctor',state.proctorModelReady?'pass':'fail',state.proctorModelReady?'Ready':'Unavailable');
        return state.proctorModelReady;
      }catch(error){
        state.proctorModel=null;
        state.proctorModelReady=false;
        setCheck('proctor','fail','Unavailable');
        return false;
      }finally{
        state.proctorModelLoading=null;
      }
    })();
    return state.proctorModelLoading;
  }

  async function detectProctorObjects(video) {
    if(!state.proctorModelReady || !state.proctorModel || !video || video.readyState<2) return [];
    return state.proctorModel.detect(video,10,0.32);
  }

  function showProctorWarning(title,detail) {
    const banner=$('#proctor-warning-banner');
    if(!banner)return;
    $('#proctor-warning-title').textContent=title||'Integrity warning';
    $('#proctor-warning-detail').textContent=detail||'A proctoring event was detected.';
    $('#proctor-warning-count').textContent=state.integrityWarnings+' / '+state.integrityWarningLimit;
    banner.classList.remove('hidden');
    clearTimeout(state.proctorBannerTimer);
    state.proctorBannerTimer=setTimeout(function(){banner.classList.add('hidden');},6500);
  }

  function resetSignalStreak(name) {
    state.signalStreaks[name]=0;
  }

  function confirmVisualSignal(name,active,threshold,warningType,detail,title) {
    if(!active){resetSignalStreak(name);return;}
    state.signalStreaks[name]=(state.signalStreaks[name]||0)+1;
    if(state.signalStreaks[name]<threshold)return;
    const now=Date.now();
    const last=state.signalLastWarning[name]||0;
    if(now-last<10000)return;
    state.signalLastWarning[name]=now;
    state.signalStreaks[name]=0;
    registerIntegrityWarning(warningType,detail,'on_device_ml',title,false);
  }

  async function runLocalProctorCheck() {
    if(!state.assessmentActive||state.finishing||state.autoSubmittedIntegrity||document.hidden||state.proctorModelBusy)return;
    if(!$('#integrity-overlay').classList.contains('hidden'))return;
    const video=$('#assessment-camera');
    if(!video||video.readyState<2)return;
    state.proctorModelBusy=true;
    try{
      const predictions=await detectProctorObjects(video);
      const persons=predictions.filter(function(item){return item.class==='person'&&Number(item.score||0)>=0.32;});
      const phones=predictions.filter(function(item){return (item.class==='cell phone'||item.class==='mobile phone')&&Number(item.score||0)>=0.25;});
      const phoneScore=phones.reduce(function(max,item){return Math.max(max,Number(item.score||0));},0);

      let faceCount=null;
      if(state.nativeFaceDetector){
        try{
          const faces=await state.nativeFaceDetector.detect(video);
          faceCount=Array.isArray(faces)?faces.length:null;
        }catch{
          state.nativeFaceDetector=null;
        }
      }
      const candidateMissing=persons.length===0 && (faceCount===null || faceCount===0);
      const multiplePeople=persons.length>1 || (faceCount!==null && faceCount>1);

      if(phones.length){
        $('#camera-proctor-status').textContent='Mobile phone detected';
        logIntegrity('phone_visual_signal','On-device object detection identified a visible mobile phone (confidence '+Math.round(phoneScore*100)+'%).','on_device_ml',null);
      }else if(candidateMissing){
        $('#camera-proctor-status').textContent='Candidate not visible';
      }else if(multiplePeople){
        $('#camera-proctor-status').textContent='Multiple people detected';
      }else{
        $('#camera-proctor-status').textContent='Candidate present · monitoring';
      }

      confirmVisualSignal(
        'phone',
        phones.length>0,
        2,
        'mobile_phone_detected',
        'A mobile phone was detected in consecutive webcam checks.',
        'Mobile phone detected'
      );
      confirmVisualSignal(
        'candidate',
        candidateMissing,
        3,
        'candidate_not_visible',
        'The candidate was not visible in consecutive webcam checks.',
        'Candidate not visible'
      );
      confirmVisualSignal(
        'multiple',
        multiplePeople,
        2,
        'multiple_people',
        'More than one person was detected in consecutive webcam checks.',
        'Multiple people detected'
      );
    }catch(error){
      $('#camera-proctor-status').textContent='Proctor model recovering';
      logIntegrity('local_proctor_error','On-device proctor model check failed and will retry.','system',null);
    }finally{
      state.proctorModelBusy=false;
    }
  }

  function currentMonitorStatus() {
    return window.screen && window.screen.isExtended===true ? 'extended' : 'single_or_unreported';
  }

  function checkLiveMediaIntegrity() {
    if(!state.assessmentActive||state.finishing||state.autoSubmittedIntegrity)return;
    const camera=state.mediaStream?.getVideoTracks?.()[0];
    const screenTrack=state.screenStream?.getVideoTracks?.()[0];
    if(!camera || camera.readyState==='ended' || !camera.enabled){
      registerIntegrityWarning('camera_interrupted','Camera feed is no longer available.','camera','Camera interrupted',true);
    }
    if(!screenTrack || screenTrack.readyState==='ended'){
      registerIntegrityWarning('screen_share_stopped','Entire-screen sharing stopped during the assessment.','screen','Screen sharing stopped',true);
    }
    if(currentMonitorStatus()==='extended'){
      const now=Date.now();
      if(now-(state.signalLastWarning.monitor||0)>=10000){
        state.signalLastWarning.monitor=now;
        registerIntegrityWarning('multiple_monitors','An extended or additional display was detected by the browser.','browser','Multiple monitors detected',false);
      }
    }
  }

  async function runSystemCheck() {
    setCheck('browser','pass','Ready');
    setCheck('clipboard','pass','Enabled');
    setCheck('visibility','pass','Enabled');
    setCheck('fullscreen',document.fullscreenEnabled?'pass':'fail',document.fullscreenEnabled?'Supported':'Unavailable');

    state.singleMonitorReady=currentMonitorStatus()!=='extended';
    setCheck(
      'monitor',
      state.singleMonitorReady?'pass':'fail',
      state.singleMonitorReady?(window.screen && 'isExtended' in window.screen?'Single display':'Browser check limited'):'Extended display detected'
    );

    let mediaReady=false;
    try {
      if(state.mediaStream) state.mediaStream.getTracks().forEach(function(t){t.stop();});
      state.mediaStream=await navigator.mediaDevices.getUserMedia({
        video:{facingMode:'user',width:{ideal:1280},height:{ideal:720}},
        audio:true
      });
      const video=$('#camera-preview');
      video.srcObject=state.mediaStream;
      await video.play();
      $('#assessment-camera').srcObject=state.mediaStream;
      $('#assessment-camera').play().catch(function(){});
      $('#camera-placeholder').classList.add('hidden');
      $('#camera-live').classList.remove('hidden');
      const videoTrack=state.mediaStream.getVideoTracks()[0];
      const audioTrack=state.mediaStream.getAudioTracks()[0];
      $('#device-label').textContent=videoTrack?.label || 'Camera connected';
      setCheck('camera',videoTrack?'pass':'fail',videoTrack?'Connected':'Missing');
      setCheck('microphone',audioTrack?'pass':'fail',audioTrack?'Connected':'Missing');
      mediaReady=Boolean(videoTrack&&audioTrack);
      $('#run-liveness').disabled=!videoTrack;
    } catch (error) {
      setCheck('camera','fail','Permission required');
      setCheck('microphone','fail','Permission required');
      $('#run-liveness').disabled=true;
      toast('Camera and microphone permission are required for the proctored assessment.','error');
    }

    state.screenReady=false;
    try {
      if(state.screenStream) state.screenStream.getTracks().forEach(function(t){t.stop();});
      if(!navigator.mediaDevices?.getDisplayMedia) throw new Error('Screen sharing unavailable');
      state.screenStream=await navigator.mediaDevices.getDisplayMedia({
        video:{displaySurface:'monitor'},
        audio:false
      });
      const screenTrack=state.screenStream.getVideoTracks()[0];
      if(!screenTrack) throw new Error('No screen-share track');
      const surface=screenTrack.getSettings?.().displaySurface;
      if(surface && surface!=='monitor'){
        screenTrack.stop();
        state.screenStream=null;
        setCheck('screen','fail','Share entire screen');
        toast('Share your entire screen, not a tab or single window, to continue.','error');
      }else{
        state.screenReady=true;
        setCheck('screen','pass',surface==='monitor'?'Entire screen shared':'Screen shared');
        screenTrack.onended=function(){
          state.screenReady=false;
          setCheck('screen','fail','Sharing stopped');
          updateStartEligibility();
          if(state.assessmentActive){
            registerIntegrityWarning(
              'screen_share_stopped',
              'Entire-screen sharing stopped during the assessment.',
              'screen',
              'Screen sharing stopped',
              true
            );
          }
        };
      }
    } catch (error) {
      state.screenReady=false;
      setCheck('screen','fail','Permission required');
      toast('Entire-screen sharing is required for the proctored assessment.','error');
    }

    const modelReady=await ensureProctorModel();
    if(modelReady){
      if('FaceDetector' in window){
        try{state.nativeFaceDetector=new FaceDetector({fastMode:true,maxDetectedFaces:3});}catch{state.nativeFaceDetector=null;}
      }
      $('#liveness-help').textContent='Keep one person centered in view and complete the short movement challenge. On-device detection remains active during the assessment.';
    }else{
      $('#liveness-help').textContent='The on-device proctoring model could not load. Check your connection and run the system check again.';
      $('#run-liveness').disabled=true;
    }

    $('#system-status-pill').textContent=mediaReady&&state.screenReady&&modelReady?'Preflight ready':'Action required';
    $('#system-status-pill').classList.toggle('neutral',!(mediaReady&&state.screenReady&&modelReady));
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
    if(!state.proctorModelReady){toast('The on-device proctor model must be ready first.','error');return;}

    $('#run-liveness').disabled=true;
    $('#liveness-title').textContent='Checking active presence…';
    $('#liveness-help').textContent='Keep one person centered in view and slowly move your head left and right.';

    const video=$('#camera-preview');
    try {
      const motionFrames=[];
      const personCounts=[];
      const faceCounts=[];
      const faceCenters=[];

      for(let i=0;i<6;i++){
        motionFrames.push(motionSignature(video));
        const predictions=await detectProctorObjects(video);
        const persons=predictions.filter(function(item){return item.class==='person'&&Number(item.score||0)>=0.32;});
        personCounts.push(persons.length);

        let detectedFaces=-1;
        if(state.nativeFaceDetector){
          try{
            const faces=await state.nativeFaceDetector.detect(video);
            detectedFaces=faces.length;
            if(faces.length===1){
              const box=faces[0].boundingBox;
              faceCenters.push((box.x+box.width/2)/Math.max(1,video.videoWidth));
            }
          }catch{
            state.nativeFaceDetector=null;
          }
        }
        faceCounts.push(detectedFaces);
        await new Promise(function(resolve){setTimeout(resolve,330);});
      }

      let maxMotion=0;
      for(let i=1;i<motionFrames.length;i++){
        maxMotion=Math.max(maxMotion,motionDelta(motionFrames[i-1],motionFrames[i]));
      }
      const singlePersonSamples=personCounts.filter(function(count,index){
        return count===1 || faceCounts[index]===1;
      }).length;
      const multiplePersonSamples=personCounts.filter(function(count,index){
        return count>1 || faceCounts[index]>1;
      }).length;
      const faceMovement=faceCenters.length>=2?Math.max(...faceCenters)-Math.min(...faceCenters):0;
      const movementPassed=maxMotion>=0.012 || faceMovement>=0.055;
      const presencePassed=singlePersonSamples>=4 && multiplePersonSamples===0;

      if(presencePassed&&movementPassed){
        state.livenessPassed=true;
        $('#liveness-title').textContent='Active presence check passed';
        $('#liveness-help').textContent='One candidate remained visible and live movement was observed. Continuous monitoring will continue during the assessment.';
        setCheck('liveness','pass','Passed');
      }else{
        state.livenessPassed=false;
        $('#liveness-title').textContent='Active presence not verified';
        $('#liveness-help').textContent=multiplePersonSamples>0
          ? 'Only one person may be visible. Clear the camera view and repeat the check.'
          : 'Keep your full face/upper body visible and repeat the left/right movement challenge.';
        setCheck('liveness','fail','Retry');
        $('#run-liveness').disabled=false;
      }
    } catch (error) {
      state.livenessPassed=false;
      $('#liveness-title').textContent='Presence check unavailable';
      $('#liveness-help').textContent='The on-device presence check could not complete. Verify camera access and rerun the system check.';
      setCheck('liveness','fail','Retry');
      $('#run-liveness').disabled=false;
    }
    updateStartEligibility();
  }

  function updateStartEligibility() {
    const consent=$('#consent-check').checked;
    const media=Boolean(state.mediaStream?.getVideoTracks().length&&state.mediaStream?.getAudioTracks().length);
    state.singleMonitorReady=currentMonitorStatus()!=='extended';
    state.systemReady=Boolean(
      media &&
      state.screenReady &&
      state.proctorModelReady &&
      state.livenessPassed &&
      state.singleMonitorReady &&
      document.fullscreenEnabled
    );
    $('#start-assessment').disabled=!(state.systemReady&&consent);
    $('#system-status-pill').textContent=state.systemReady?'Ready for proctored assessment':'Action required';
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
      $('#interview-title').textContent=`${job.title} placement assessment`;
      $('#interview-context').textContent=`${job.company_name || 'Opportunity'} · standardized blueprint · proctored forward-only mode`;
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
    if(state.assessmentActive || $('#start-assessment').disabled)return;
    if(!state.systemReady || !$('#consent-check').checked){toast('Complete all required secure checks first.','error');return;}
    $('#start-assessment').disabled=true;
    try {
      await $('#interview-panel').requestFullscreen();
      let remaining=TOTAL_SECONDS*1000;
      if(!previewMode){
        const clock=await api(`/mock-interview/${state.session.interview_id}/hr/exam-start`,{method:'POST',body:JSON.stringify({processor:state.recordingPolicy?.processor || 'google',consent:$('#consent-check').checked})});
        remaining=Math.max(0,Date.parse(clock.exam_deadline_at)-Date.parse(clock.server_time));
        if(!Number.isFinite(remaining))throw new Error('The assessment timer could not synchronize. Try again.');
      }
      state.examDeadline=Date.now()+remaining;
    } catch(error) {
      if(document.fullscreenElement)await document.exitFullscreen().catch(()=>{});
      $('#start-assessment').disabled=false;
      toast(error.message || 'Full-screen permission is required to start the assessment.','error');
      return;
    }
    state.assessmentActive=true;state.finishing=false;state.current=0;state.totalRemaining=TOTAL_SECONDS;state.sectionRemaining=0;state.integrityEvents=[];state.integrityWarnings=0;state.lastWarningAt=0;state.autoSubmittedIntegrity=false;state.integrityTerminationReason='';state.proctorVisionBusy=false;state.proctorModelBusy=false;state.faceMissStreak=0;state.multipleFaceStreak=0;state.phoneDetectionStreak=0;state.signalStreaks={candidate:0,multiple:0,phone:0};state.signalLastWarning={candidate:0,multiple:0,phone:0,monitor:0};
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
    if(previewMode||!state.assessmentActive||state.recordingPolicy?.remote_proctoring===false||state.proctorVisionBusy||document.hidden||!state.session?.interview_id)return;
    const image=captureProctorFrame();
    if(!image)return;
    state.proctorVisionBusy=true;
    try{
      const data=await api('/mock-interview/proctor-frame',{
        method:'POST',
        body:JSON.stringify({interview_id:state.session.interview_id,image_data_url:image})
      });
      if(data.mobile_phone_detected){
        logIntegrity('cloud_phone_confirmation','Secondary vision analysis confirmed a visible mobile-phone signal.','vision',null);
        confirmVisualSignal(
          'phone',
          true,
          2,
          'mobile_phone_detected',
          'A mobile phone was confirmed in repeated webcam checks.',
          'Mobile phone detected'
        );
      }
      if(!data.candidate_visible||Number(data.person_count||0)===0){
        logIntegrity('cloud_candidate_absence','Secondary vision analysis could not see the candidate.','vision',null);
        confirmVisualSignal(
          'candidate',
          true,
          3,
          'candidate_not_visible',
          'The candidate was not visible in repeated webcam checks.',
          'Candidate not visible'
        );
      }
      if(Number(data.person_count||0)>1){
        logIntegrity('cloud_multiple_people','Secondary vision analysis detected more than one person.','vision',null);
        confirmVisualSignal(
          'multiple',
          true,
          2,
          'multiple_people',
          'More than one person was confirmed in repeated webcam checks.',
          'Multiple people detected'
        );
      }
    }catch(error){
      logIntegrity('secondary_vision_unavailable','Secondary cloud vision check was temporarily unavailable; on-device monitoring remained active.','system',null);
    }finally{
      state.proctorVisionBusy=false;
    }
  }

  async function startPresenceMonitoring() {
    clearInterval(state.faceTimer);
    clearInterval(state.localProctorTimer);
    clearInterval(state.proctorVisionTimer);
    clearInterval(state.mediaWatchTimer);

    state.signalStreaks={candidate:0,multiple:0,phone:0};
    state.signalLastWarning={candidate:0,multiple:0,phone:0,monitor:0};
    state.faceMissStreak=0;
    state.multipleFaceStreak=0;
    state.phoneDetectionStreak=0;

    if('FaceDetector' in window && !state.nativeFaceDetector){
      try{state.nativeFaceDetector=new FaceDetector({fastMode:true,maxDetectedFaces:3});}catch{state.nativeFaceDetector=null;}
    }

    const cameraTrack=state.mediaStream?.getVideoTracks?.()[0];
    if(cameraTrack){
      cameraTrack.onended=function(){
        registerIntegrityWarning('camera_stopped','Camera access stopped during the assessment.','camera','Camera stopped',true);
      };
      cameraTrack.onmute=function(){
        logIntegrity('camera_muted','Camera stream was temporarily muted.','camera',null);
      };
    }
    const screenTrack=state.screenStream?.getVideoTracks?.()[0];
    if(screenTrack){
      screenTrack.onended=function(){
        state.screenReady=false;
        registerIntegrityWarning(
          'screen_share_stopped',
          'Entire-screen sharing stopped during the assessment.',
          'screen',
          'Screen sharing stopped',
          true
        );
      };
    }

    $('#camera-proctor-status').textContent='Initializing proctor model…';
    await ensureProctorModel();
    if(!state.proctorModelReady){
      registerIntegrityWarning(
        'proctor_model_unavailable',
        'The on-device proctoring model became unavailable.',
        'system',
        'Proctoring unavailable',
        true
      );
      return;
    }

    $('#camera-proctor-status').textContent='Candidate present · monitoring';
    state.localProctorTimer=setInterval(runLocalProctorCheck,1500);
    state.mediaWatchTimer=setInterval(checkLiveMediaIntegrity,3500);
    setTimeout(runLocalProctorCheck,650);

    if(!previewMode){
      state.proctorVisionTimer=setInterval(runVisionProctorCheck,10000);
      setTimeout(runVisionProctorCheck,5000);
    }
  }

  function saveCurrentAnswerOnly() {
    if(!answerCurrentQuestion())return;
    $('#autosave-state').textContent='Answer saved · use Save & Next to continue';
    toast('Answer saved for the current question.');
  }

  async function submitAndContinue() {
    if(state.advancing || state.finishing || !state.assessmentActive)return;
    state.advancing=true;
    try {
    if(!answerCurrentQuestion()) return;
    if(state.questions[state.current].response_mode)await finishQuestionAnswer();
    else if(state.questions[state.current].answer_type==='video' && !await advanceHRQuestion())return;
    cancelQuestionReading();
    if(state.finishing)return;
    if(state.current>=state.questions.length-1){await finishAssessment(false);return;}
    state.current++;
    renderQuestion();
    } catch(error){toast(error.message,'error');} finally {state.advancing=false;}
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

  function showAnalysisPanel() {
    clearAnalysisTimers();
    $('#result-panel').classList.add('hidden');
    $('#analysis-panel').classList.remove('hidden');
    $('#retry-analysis').classList.add('hidden');
    $$('.analysis-step').forEach(row=>{
      row.classList.remove('done','active');
      row.querySelector('b').textContent='Pending';
    });
    $('#analysis-message').textContent='Preparing your complete report. All section scores appear together after grading and HR video analysis finish.';
    $('#return-to-setup').classList.toggle('hidden',!state.submissionSaved || !!(state.hr?.recorder && !state.hr.submitted));
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

  function savedAttemptKey() {
    return state.me?.id ? `placeai-assessment-result:${state.me.id}` : null;
  }

  function rememberSubmittedAttempt() {
    const key=savedAttemptKey();
    if(key && state.session?.interview_id)try{sessionStorage.setItem(key,state.session.interview_id);}catch{}
  }

  async function openSavedResult(interviewId) {
    if(state.assessmentActive || state.finishing)return;
    if(state.hr?.recorder && !state.hr.submitted){toast('Finish submitting the current recording before opening another result.','error');return;}
    const generation=++state.analysisGeneration;
    state.session={interview_id:interviewId};
    state.submissionSaved=true;
    state.answers=[];
    state.hr=null;
    state.finishing=true;
    $('#setup-panel').classList.add('hidden');
    showAnalysisPanel();
    try{
      const saved=await api(`/mock-interview/${interviewId}/result`);
      if(state.analysisGeneration!==generation || state.session?.interview_id!==interviewId)return;
      state.finishing=false;
      if(saved.status==='complete'){
        $('#analysis-panel').classList.add('hidden');
        state.lastResult=saved.result;
        renderResult(saved.result,false);
      }else{
        $('#analysis-message').textContent=saved.status==='pending'
          ? (saved.queued?'Your submitted exam is saved. Every section is being analyzed in the background. Return to exam history later for the complete report.':'Your submitted exam is saved. Its complete report is pending. Retry analysis or return to setup to start another assessment.')
          : 'This assessment has not been submitted. Finish it in the original exam tab.';
        $('#retry-analysis').classList.toggle('hidden',saved.status!=='pending');
      }
    }catch(error){
      if(state.analysisGeneration!==generation || state.session?.interview_id!==interviewId)return;
      state.finishing=false;
      $('#analysis-message').textContent=error.message || 'Your saved report could not load. Please try again.';
      $('#retry-analysis').classList.remove('hidden');
    }
  }

  async function waitForQueuedResult(generation) {
    clearAnalysisTimers();
    $('#analysis-message').textContent='Your exam is saved securely. Preparing every section of your report; you can also return to it from exam history.';
    $('#return-to-setup').classList.remove('hidden');
    const interviewId=state.session.interview_id;
    const deadline=Date.now()+10*60*1000;
    while(Date.now()<deadline && state.analysisGeneration===generation && state.session?.interview_id===interviewId){
      // Jitter prevents students finishing together from polling together.
      await new Promise(resolve=>setTimeout(resolve,(document.hidden?20000:8000)+Math.random()*4000));
      if(state.analysisGeneration!==generation || state.session?.interview_id!==interviewId)return;
      const saved=await api(`/mock-interview/${interviewId}/result`);
      if(state.analysisGeneration!==generation || state.session?.interview_id!==interviewId)return;
      if(saved.status==='complete')return saved.result;
      if(saved.queue_status==='failed')throw new Error('Your exam is saved. Analysis needs support to resume; contact your institution.');
      if(saved.error_code==='VIDEO_PROVIDER_CAPACITY')$('#analysis-message').textContent='Your exam is saved. Analysis is waiting for available capacity. You can leave this page and return to exam history later; your complete report appears after every section is ready.';
      else if(saved.spoken_progress)$('#analysis-message').textContent=`Your exam is saved. ${saved.spoken_progress.analyzed} of ${saved.spoken_progress.recorded} recorded answers analyzed. The complete report appears after every section is ready; you can return from exam history later.`;
    }
    throw new Error('Your exam is saved. Return to exam history to view the report when it is ready.');
  }

  async function runResultAnalysis(auto) {
    const generation=++state.analysisGeneration;
    const interviewId=state.session?.interview_id;
    showAnalysisPanel();
    try {
      let result;
      if(previewMode){
        await new Promise(resolve=>setTimeout(resolve,1400));
        result=buildPreviewResult();
      }else{
        await finishQuestionAnswer();
        await submitHRVideo();
        if(state.analysisGeneration!==generation || state.session?.interview_id!==interviewId)return;
        rememberSubmittedAttempt();
        // Save once. Subsequent requests re-analyze the immutable submitted exam.
        for(let attempt=0;attempt<2;attempt++){
          try {
            if(state.submissionSaved || attempt>0){
              const saved=await api(`/mock-interview/${state.session.interview_id}/result`);
              if(state.analysisGeneration!==generation || state.session?.interview_id!==interviewId)return;
              if(saved.status==='complete'){result=saved.result;break;}
              if(saved.requires_recording_consent){
                if(!window.confirm('PlaceAI can resume your saved report using Groq. Do you consent to sending your voice, HR camera recordings and sampled frames to Groq for transcription and practice coaching with Zero Data Retention? Your recordings remain private in PlaceAI for 30 days.')){
                  const cancelled=new Error('Your exam stays saved. Approve the updated recording notice when you are ready to resume.');cancelled.status=409;throw cancelled;
                }
                await api(`/mock-interview/${interviewId}/hr/processor-consent`,{method:'POST',body:JSON.stringify({processor:'groq',consent:true})});
                if(state.analysisGeneration!==generation || state.session?.interview_id!==interviewId)return;
              }
              if(saved.status==='pending'){state.submissionSaved=true;if(saved.queued){result=await waitForQueuedResult(generation);break;}}
              else{
                state.submissionSaved=false;
                if(!state.answers.length)throw new Error('This exam has not been submitted. Return to the original exam tab to finish uploading and submit.');
              }
            }
            result=state.submissionSaved
              ? await api(`/mock-interview/${state.session.interview_id}/retry`,{method:'POST',body:'{}'})
              : await api('/mock-interview/evaluate',{method:'POST',body:JSON.stringify({
                interview_id:state.session.interview_id,answers:state.answers.filter(Boolean),
                integrity_events:state.integrityEvents,integrity_warning_count:state.integrityWarnings,
                integrity_auto_submitted:state.autoSubmittedIntegrity,
                integrity_termination_reason:state.integrityTerminationReason||null
              })});
            if(state.analysisGeneration!==generation || state.session?.interview_id!==interviewId)return;
            state.submissionSaved=true;
            if(result.queued){result=await waitForQueuedResult(generation);break;}
            if(result.analysis_status==='complete')break;
            throw new Error('Your exam is saved. Analysis is still processing.');
          }catch(error){
            if(state.analysisGeneration!==generation || state.session?.interview_id!==interviewId)return;
            const supportRequired=['VIDEO_PROVIDER_CAPACITY','VIDEO_PROVIDER_ACCESS','VIDEO_PROVIDER_MODEL','VIDEO_PROVIDER_UNAVAILABLE','AI_PROVIDER_CAPACITY','AI_PROVIDER_UNAVAILABLE','VIDEO_PROCESSOR_CONSENT_REQUIRED'].includes(error.code);
            if(supportRequired && !state.submissionSaved){
              try{
                const saved=await api(`/mock-interview/${interviewId}/result`);
                if(state.analysisGeneration!==generation || state.session?.interview_id!==interviewId)return;
                state.submissionSaved=['pending','complete'].includes(saved.status);
                if(saved.status==='complete'){result=saved.result;break;}
              }catch{ /* Preserve the original safe error when confirmation is unavailable. */ }
            }
            if(attempt===1 || supportRequired || [400,401,403,404,409,410,413,422].includes(error.status) || !state.answers.length && !state.submissionSaved)throw error;
            clearAnalysisTimers();
            $('#analysis-message').textContent='Finishing the complete report, including spoken HR answers. All scores will appear together when analysis is ready.';
            await new Promise(resolve=>setTimeout(resolve,[2000,5000,10000][attempt]));
            if(state.analysisGeneration!==generation || state.session?.interview_id!==interviewId)return;
          }
        }
      }
      if(state.analysisGeneration!==generation || state.session?.interview_id!==interviewId)return;
      if(result?.analysis_status!=='complete' && !previewMode)throw new Error('Your exam is saved. Analysis is still pending; retry to receive all results together.');
      markAnalysisComplete();
      state.lastResult=result;
      state.finishing=false;
      $('#analysis-panel').classList.add('hidden');
      renderResult(result,!!auto);
    }catch(error){
      if(state.analysisGeneration!==generation || state.session?.interview_id!==interviewId)return;
      clearAnalysisTimers();
      state.finishing=false;
      $('#analysis-message').textContent=error.message || (state.submissionSaved
        ? 'Your submitted exam is saved. The complete report is pending. Retry analysis later.'
        : 'Submission could not complete. Keep this page open and retry to save your answers.');
      $('#return-to-setup').classList.toggle('hidden',!state.submissionSaved || !!(state.hr?.recorder && !state.hr.submitted));
      $('#retry-analysis').classList.remove('hidden');
      toast(state.submissionSaved?'All scores remain hidden until the complete report is ready.':'Keep this page open and retry submission.','error');
    }
  }

  async function finishAssessment(auto) {
    cancelQuestionReading();
    // Lock synchronously: expiry, device loss and a final click may arrive together.
    if(state.finishing || !state.assessmentActive)return;
    state.finishing=true;
    state.assessmentActive=false;
    if(state.questions[state.current]?.answer_type==='video' && state.hr?.recorder)answerCurrentQuestion();
    clearInterval(state.timerId);
    clearInterval(state.faceTimer);
    clearInterval(state.localProctorTimer);
    clearInterval(state.proctorVisionTimer);
    clearInterval(state.mediaWatchTimer);
    clearTimeout(state.proctorBannerTimer);
    try{await finishQuestionAnswer();await stopHRVideo();}catch(error){toast(error.message,'error');}
    fillUnansweredResponses(auto?'[No response submitted before assessment ended]':'[No response submitted]');
    state.ignoreFullscreen=true;
    try{if(document.fullscreenElement)await document.exitFullscreen();}catch{}
    state.ignoreFullscreen=false;
    if(state.mediaStream){state.mediaStream.getTracks().forEach(t=>t.stop());state.mediaStream=null;}
    if(state.screenStream){state.screenStream.getTracks().forEach(t=>t.stop());state.screenStream=null;}
    state.screenReady=false;
    uninstallSecureGuards();
    document.body.classList.remove('secure-assessment','integrity-critical');
    $('#integrity-overlay').classList.add('hidden');
    $('#proctor-warning-banner')?.classList.add('hidden');
    $('#interview-panel').classList.add('hidden');
    await runResultAnalysis(!!auto);
  }

  function renderSectionPerformance(rows) {
    rows = rows || [];
    $('#section-performance').innerHTML = rows.map(function(row){
      return '<tr><td><strong>'+esc(row.label||row.key)+'</strong><small class="section-practice-note">'+esc(Number(row.score)>=75?'Strong performance · maintain with practice':Number(row.score)>=50?'Developing · review missed questions':'Focus area · revisit fundamentals and retry')+'</small></td><td class="section-score">'+(row.score??'—')+'/100</td><td class="good-count">'+(row.correct??0)+'</td><td class="partial-count">'+(row.partial??0)+'</td><td class="bad-count">'+(row.incorrect??0)+'</td><td>'+(row.insufficient??0)+'</td><td>'+(row.questions??0)+'</td></tr>';
    }).join('') || '<tr><td colspan="7">No section results available.</td></tr>';
  }

  function reviewDetailsList(title,items) {
    items = items || [];
    if(!items.length)return '';
    return '<div class="review-detail-box"><h5>'+esc(title)+'</h5><ul>'+items.map(function(x){return '<li>'+esc(x)+'</li>';}).join('')+'</ul></div>';
  }

  async function loadHRPlayback(atSeconds=0) {
    const button=$('#load-hr-recording');
    const video=$('#hr-result-video');
    const status=$('#hr-playback-status');
    if(!video || !state.lastResult?.hr_video)return;
    if(state.recordingUrl){video.currentTime=atSeconds;await video.play().catch(()=>{});return;}
    if(button.disabled)return;
    button.disabled=true;
    status.textContent='Loading your private HR recording...';
    try{
      const info=state.lastResult.hr_video;
      const expectedSize=Number(info.size_bytes);
      if(!Number.isInteger(expectedSize) || expectedSize<=0 || expectedSize>40*1024*1024)throw new Error('This recording is not available for playback.');
      const chunks=[];
      let received=0;
      while(received<expectedSize){
        const end=Math.min(expectedSize-1,received+3*1024*1024-1);
        const response=await api(`/mock-interview/${state.session.interview_id}/hr/recording`,{headers:{Range:`bytes=${received}-${end}`},rawResponse:true});
        const range=/^bytes (\d+)-(\d+)\/(\d+)$/.exec(response.headers.get('Content-Range') || '');
        if(response.status!==206 || !range || Number(range[1])!==received || Number(range[2])!==end || Number(range[3])!==expectedSize)throw new Error('The recording could not be loaded completely. Try again.');
        const part=await response.blob();
        if(part.size!==end-received+1)throw new Error('The recording download was interrupted. Try again.');
        chunks.push(part);received+=part.size;
      }
      state.recordingUrl=URL.createObjectURL(new Blob(chunks,{type:info.mime_type || 'video/webm'}));
      video.src=state.recordingUrl;
      video.classList.remove('hidden');
      video.addEventListener('loadedmetadata',()=>{video.currentTime=atSeconds;},{once:true});
      status.textContent='Private recording loaded. It is available only during its retention period.';
      button.textContent='Play recording';
      await video.play().catch(()=>{});
    }catch(error){status.textContent=error.status===410?'This recording has expired. Your feedback is still available.':error.message || 'The recording could not be loaded. Try again.';}
    finally{button.disabled=false;}
  }

  function renderHRVideoResult(result) {
    if(state.recordingUrl){URL.revokeObjectURL(state.recordingUrl);state.recordingUrl=null;}
    const panel=$('#hr-video-report');
    if(!panel)return;
    panel.classList.toggle('hidden',!result.hr_video);
    const video=$('#hr-result-video');
    video.pause();video.removeAttribute('src');video.load();video.classList.add('hidden');
    if(!result.hr_video)return;
    $('#hr-video-summary').textContent=result.hr_video.summary || 'Review your recorded answers and evidence below.';
    $('#hr-playback-status').textContent=`Private recording retained for ${result.hr_video.retention_days || 30} days. Feedback remains in your report.`;
    $('#load-hr-recording').disabled=false;
    $('#load-hr-recording').textContent='Load private recording';
  }

  function renderQuestionReviews(filter) {
    (state.answerPlaybackUrls || []).forEach(url=>URL.revokeObjectURL(url));state.answerPlaybackUrls=[];
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
      html+='<span class="review-chip '+bucket+'">'+esc(item.answer_type==='mcq' ? (bucket==='correct'?'✓ Correct':bucket==='insufficient'?'– Not answered':'✕ Incorrect') : (bucket==='correct'?'✓ Strong response':bucket==='partial'?'◐ Developing':bucket==='insufficient'?'– Insufficient evidence':'↗ Needs practice'))+'</span>';
      html+='<span class="review-chip">'+esc((item.section||'interview').replaceAll('_',' '))+'</span>';
      html+='<span class="review-chip">'+esc(item.grading_method==='system'?'System graded':item.grading_method==='code_execution'?'Code tests':item.grading_method==='system_relevance_gate'?'Relevance check':item.grading_method==='ai_video'?'HR video analysis':item.grading_method==='ai_audio'?'Spoken answer analysis':item.grading_method==='ai'?'AI graded':'Preview graded')+'</span>';
      html+='</div><h4>Q'+item.question_id+'. '+esc(item.question||'')+'</h4></div><div class="answer-score-box"><strong>'+(item.score??'—')+'</strong><small>/100</small></div></header>';
      let answerBody='<p>'+esc(item.answer||'No answer')+'</p>';
      if(item.answer_type==='code'){
        const stored=parseStoredCodeAnswer(item.answer);
        answerBody='<div class="review-code-meta"><strong>'+esc(stored?.language||'code')+'</strong><span>'+esc(item.execution?((item.execution.passed||0)+'/'+(item.execution.total||0)+' tests passed'):'')+'</span></div><pre class="review-code">'+esc(stored?.source_code||'No code submitted')+'</pre>';
      }
      html+='<div class="answer-comparison"><div class="answer-pane"><span>Your answer</span>'+answerBody+'</div>';
      html+='<div class="answer-pane correct-pane"><span>'+(item.answer_type==='mcq'?'Correct answer':item.answer_type==='code'?'Execution result':'Strong answer / reference')+'</span><p>'+esc(item.answer_type==='code'?(item.feedback||'See execution evidence below.'):(expected||'See detailed feedback below.'))+'</p></div></div>';
      html+='<p class="review-feedback"><strong>Assessment:</strong> '+esc(item.feedback||'No detailed feedback returned.')+'</p>';
      if(rubricEntries.length && item.answer_type!=='mcq'){
        html+='<div class="rubric-grid">'+rubricEntries.map(function(entry){return '<div class="rubric-item"><span>'+esc(entry[0].replaceAll('_',' '))+'</span><strong>'+entry[1]+'/100</strong></div>';}).join('')+'</div>';
      }
      html+='<div class="review-details">'+reviewDetailsList('What worked',item.strengths||[])+reviewDetailsList('Errors / gaps',[].concat(item.issues||[],item.missing_points||[]))+'</div>';
      if(['audio','video'].includes(item.answer_type) && Array.isArray(item.evidence)){
        html+='<div class="review-detail-box"><h5>Recording evidence</h5><ul>'+item.evidence.map(e=>'<li><button type="button" class="button secondary" '+(item.recording_url?'data-answer-recording="'+Number(item.question_id)+'" ':'')+'data-recording-second="'+Number(e.at_seconds || 0)+'">'+esc(formatTime(e.at_seconds))+'</button> '+esc(e.observation)+'</li>').join('')+'</ul>'+(item.recording_url?'<p role="status" id="answer-playback-status-'+Number(item.question_id)+'"></p><'+(item.answer_type==='audio'?'audio':'video')+' id="answer-playback-'+Number(item.question_id)+'" class="hidden" controls playsinline preload="none" style="max-width:100%"></'+(item.answer_type==='audio'?'audio':'video')+'>':'')+'</div>';
      }
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
    if(!previewMode && result.analysis_status!=='complete'){showAnalysisPanel();return;}
    state.lastResult=result;
    const complete=result.analysis_status==='complete';
    const summary=result.score_summary||{};
    $('#overall-score').textContent=result.overall_score??'—';
    $('#report-iri').textContent=result.overall_score===null||result.overall_score===undefined?'Withheld':result.overall_score+'/100';
    $('#overall-feedback').textContent=result.overall_feedback||'Assessment completed.';
    $('#grading-method-label').textContent=previewMode?'Answer key + coding workspace + preview scoring':'Answer key + sandbox execution + answer and HR video analysis';
    renderIntegrityReport(result);
    renderHRVideoResult(result);
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
    $('#summary-coding').textContent=summary.coding_tests_total?((summary.coding_tests_passed||0)+' / '+summary.coding_tests_total):'—';
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
    (state.answerPlaybackUrls || []).forEach(url=>URL.revokeObjectURL(url));state.answerPlaybackUrls=[];
    cancelQuestionReading();
    state.answerClip=null;
    state.analysisGeneration++;
    clearInterval(state.timerId);
    clearInterval(state.faceTimer);
    clearInterval(state.localProctorTimer);
    clearInterval(state.proctorVisionTimer);
    clearInterval(state.mediaWatchTimer);
    clearTimeout(state.proctorBannerTimer);
    state.assessmentActive=false;
    state.finishing=false;
    state.current=0;
    state.answers=[];
    state.questions=[];
    state.session=null;
    state.livenessPassed=false;
    state.systemReady=false;
    state.screenReady=false;
    state.lastResult=null;
    state.reviewFilter='all';
    state.integrityEvents=[];
    state.integrityWarnings=0;
    state.lastWarningAt=0;
    state.autoSubmittedIntegrity=false;
    state.integrityTerminationReason='';
    state.faceMissStreak=0;
    state.multipleFaceStreak=0;
    state.phoneDetectionStreak=0;
    state.signalStreaks={candidate:0,multiple:0,phone:0};
    state.signalLastWarning={candidate:0,multiple:0,phone:0,monitor:0};
    state.expandedSections={};
    state.codeDrafts={};
    state.codeExecution={};
    clearInterval(state.hr?.retryTimer);
    if(state.recordingUrl)URL.revokeObjectURL(state.recordingUrl);
    state.recordingUrl=null;
    state.hr=null;
    state.submissionSaved=false;
    state.examDeadline=0;
    state.sectionDeadline=0;
    state.advancing=false;
    const savedKey=savedAttemptKey();
    if(savedKey)try{sessionStorage.removeItem(savedKey);}catch{}
    clearAnalysisTimers();
    if(state.mediaStream){state.mediaStream.getTracks().forEach(function(t){t.stop();});state.mediaStream=null;}
    if(state.screenStream){state.screenStream.getTracks().forEach(function(t){t.stop();});state.screenStream=null;}
    document.body.classList.remove('secure-assessment','integrity-critical');
    $('#proctor-warning-banner')?.classList.add('hidden');
    $('#result-panel').classList.add('hidden');
    $('#analysis-panel').classList.add('hidden');
    $('#system-panel').classList.add('hidden');
    $('#setup-panel').classList.remove('hidden');
    $('#consent-check').checked=false;
    $('#start-assessment').disabled=true;
    $('#run-liveness').disabled=true;
    setCheck('liveness',null,'Required');
    setCheck('screen',null,'Required');
    $('#camera-placeholder').classList.remove('hidden');
    $('#camera-live').classList.add('hidden');
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
  $('#return-to-setup')?.addEventListener('click',()=>{
    if(!state.submissionSaved || state.hr?.recorder && !state.hr.submitted)return;
    resetAssessment();
    loadHistory();
  });
  $('#load-hr-recording')?.addEventListener('click',()=>loadHRPlayback());
  async function loadAnswerPlayback(questionId,atSeconds) {
    const item=state.lastResult?.evaluations?.find(answer=>answer.question_id===questionId);
    const media=$('#answer-playback-'+questionId),status=$('#answer-playback-status-'+questionId);
    if(!item || !media || !status)return;
    if(media.src){media.currentTime=Math.max(0,atSeconds);media.play().catch(()=>{});return;}
    const size=Number(item.recording_size_bytes);
    if(!Number.isInteger(size) || size<=0 || size>7*1024*1024)return;
    status.textContent='Loading your private answer…';
    try {
      const parts=[];
      for(let start=0;start<size;){
        const end=Math.min(size-1,start+3*1024*1024-1);
        const response=await api(`/mock-interview/${state.lastResult.interview_id}/answers/${questionId}/recording`,{headers:{Range:`bytes=${start}-${end}`},rawResponse:true});
        if(response.status!==206 || response.headers.get('Content-Range')!==`bytes ${start}-${end}/${size}`)throw new Error('The answer could not be loaded completely. Try again.');
        const part=await response.blob();if(part.size!==end-start+1)throw new Error('Answer playback was interrupted. Try again.');
        parts.push(part);start+=part.size;
      }
      if(!media.isConnected)return;
      const url=URL.createObjectURL(new Blob(parts,{type:item.recording_mime_type}));
      (state.answerPlaybackUrls || (state.answerPlaybackUrls=[])).push(url);media.src=url;media.classList.remove('hidden');
      media.addEventListener('loadedmetadata',()=>{media.currentTime=Math.max(0,atSeconds);},{once:true});
      status.textContent='Private answer recording · available during the 30-day retention period.';media.play().catch(()=>{});
    }catch(error){status.textContent=error.status===410?'This recording has expired. Your feedback remains available.':error.message;}
  }

  $('#answer-feedback')?.addEventListener('click',event=>{const button=event.target.closest('[data-recording-second]');if(button){if(button.dataset.answerRecording)loadAnswerPlayback(Number(button.dataset.answerRecording),Number(button.dataset.recordingSecond));else loadHRPlayback(Number(button.dataset.recordingSecond));}});
  $('#history-list')?.addEventListener('click',event=>{const button=event.target.closest('[data-saved-result]');if(button)openSavedResult(button.dataset.savedResult);});
  $('#retry-analysis')?.addEventListener('click',function(){if(state.finishing)return;state.finishing=true;runResultAnalysis(false);});
  $('#retry-analysis-result')?.addEventListener('click',function(){if(state.finishing)return;state.finishing=true;runResultAnalysis(false);});
  $('#review-filters')?.addEventListener('click',function(event){const button=event.target.closest('[data-review-filter]');if(button)renderQuestionReviews(button.dataset.reviewFilter);});
  $('#section-nav')?.addEventListener('click',function(event){
    const button=event.target.closest('[data-section-toggle]');
    if(button) toggleNavigatorSection(button.dataset.sectionToggle);
  });

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
      if(demo==='assessment'){
        const job=previewJobs()[0];
        state.session={interview_id:'preview-assessment',job_title:job.title,company_name:job.company_name,mode:'assessment'};
        state.questions=makeDemoQuestions(job);
        state.answers=new Array(state.questions.length);
        state.current=0;
        state.expandedSections={quantitative:true};
        $('#job-select').value=job.id;
        $('#interview-title').textContent=job.title+' placement assessment';
        $('#interview-context').textContent=(job.company_name||'Opportunity')+' · standardized blueprint · proctored forward-only mode';
        $('#setup-panel').classList.add('hidden');
        $('#history-panel').classList.add('hidden');
        $('#system-panel').classList.remove('hidden');
        $('#system-panel').scrollIntoView({behavior:'smooth',block:'start'});
        return;
      }
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
      state.recordingPolicy=await api('/mock-interview/recording-policy').catch(()=>null);
      if(state.recordingPolicy?.processor==='groq'){
        $('#consent-check').closest('label').querySelector('span').textContent='I understand that this proctored practice assessment uses camera, microphone, screen sharing and browser monitoring for integrity signals reviewed by institution staff. I consent to sending my spoken answers, HR camera recordings and selected video frames to Groq for transcription and practice coaching, with Zero Data Retention enabled. PlaceAI keeps recordings private for 30 days for me and authorized institution staff. Speech-recognition and sampled-frame feedback cannot assess pronunciation or continuous-video behavior. All section results appear together after analysis finishes. These are practice insights for human review, not hiring decisions.';
      }
      state.candidateLabel=(state.me.full_name || state.me.username || 'Candidate').toUpperCase().slice(0,40);
      $('#auth-state').classList.add('hidden'); $('#setup-panel').classList.remove('hidden');
      await Promise.all([loadJobs(),loadHistory()]);
      // Entry always opens setup. Saved reports are an explicit history action.
    } catch(error){ $('#auth-state').textContent=error.message; toast(error.message,'error'); }
  })();
})();
