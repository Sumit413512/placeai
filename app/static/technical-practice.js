/* Technical foundations practice. Answer keys and deadlines are authoritative on the server. */
(() => {
  'use strict';
  let ctx, attempt, position=0, clock, offset=0, busy=false, epoch=0, autoRetryAt=0;
  const active=(version=epoch)=>version===epoch&&ctx?.state.view==='technical-practice'&&document.querySelector('#technical-practice');
  const esc=value=>ctx.esc(String(value??''));
  const storageKey='placeai.technical.attempt.v1';
  const notice=text=>{const node=document.querySelector('#technical-notice');if(node)node.textContent=text;};
  const remaining=()=>Math.max(0,Math.ceil((Date.parse(attempt.deadline_at)-Date.now()-offset)/1000));
  function accept(data){attempt=data;offset=Date.parse(data.server_time)-Date.now();try{sessionStorage.setItem(storageKey,data.id);}catch{}}
  function tick(){
    if(!active()||!attempt||attempt.result){clearInterval(clock);return;}
    const seconds=remaining(),node=document.querySelector('[data-technical-clock]');
    if(node)node.textContent=`${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`;
    if(!seconds&&!busy&&Date.now()>=autoRetryAt)submit();
  }
  function shell(){return ctx.pageHead('Technical interview practice','A focused exam for SQL, debugging, APIs and systems fundamentals.')+'<div id="technical-practice"></div>';}
  function renderAttempt(){
    if(!active())return;clearInterval(clock);
    const host=document.querySelector('#technical-practice');
    if(attempt.result){
      const result=attempt.result;
      host.innerHTML=`<section class="panel technical-result"><span class="section-kicker">Your practice report</span><h2>${result.score}% · ${result.correct} of ${result.total} correct</h2><p>${esc(result.note)}</p><div class="technical-section-scores">${result.sections.map(s=>`<article><h3>${esc(s.name)}</h3><strong>${s.correct} / ${s.total}</strong></article>`).join('')}</div><button class="button button-primary" data-technical-new>Practise again</button><h3>Review every answer</h3>${result.questions.map(q=>`<details class="technical-review"><summary>${q.id}. ${esc(q.question)} · ${q.earned?'Correct':q.selected==null?'Unanswered':'Review'}</summary><p><strong>Your answer:</strong> ${esc(q.selected==null?'No saved answer':q.options[q.selected])}</p><p><strong>Correct answer:</strong> ${esc(q.options[q.correct])}</p><p>${esc(q.explanation)}</p></details>`).join('')}<p id="technical-notice" role="status"></p></section>`;return;
    }
    position=Math.min(position,attempt.questions.length-1);
    const q=attempt.questions[position];
    host.innerHTML=`<section class="panel technical-session"><header class="technical-session-head"><div><span class="section-kicker">${esc(q.section)}</span><h2>Question ${position+1} of ${attempt.questions.length}</h2></div><div class="technical-clock">Time remaining <strong data-technical-clock></strong></div></header><p>Answers save when you select them. You can revisit questions before submitting. The timer continues if you leave.</p><nav class="technical-question-map" aria-label="Practice questions">${attempt.questions.map((item,i)=>`<button class="row-button" data-technical-question="${i}" ${i===position?'aria-current="step"':''} aria-label="Question ${i+1}${attempt.answers[item.id]!=null?', answered':''}">${i+1}${attempt.answers[item.id]!=null?' ✓':''}</button>`).join('')}</nav><fieldset class="technical-options"><legend>${esc(q.question)}</legend>${q.options.map((option,i)=>`<label><input type="radio" name="technical-answer" value="${i}" ${attempt.answers[q.id]===i?'checked':''}>${esc(option)}</label>`).join('')}</fieldset><div class="technical-actions"><button class="button button-secondary" data-technical-move="-1" ${position===0?'disabled':''}>Previous question</button><button class="button button-secondary" data-technical-move="1" ${position===attempt.questions.length-1?'disabled':''}>Next question</button><button class="button button-primary" data-technical-submit>Finish and review</button></div><p id="technical-notice" role="status" aria-live="polite"></p></section>`;
    tick();clock=setInterval(tick,1000);
  }
  async function start(){
    if(busy)return;busy=true;const version=epoch;
    try{const data=await ctx.api('/technical-practice/start',{method:'POST',body:JSON.stringify({request_id:crypto.randomUUID()})});if(!active(version))return;accept(data);position=0;renderAttempt();}
    catch(error){if(active(version))notice(error.message);}finally{if(version===epoch)busy=false;}
  }
  async function submit(){
    if(busy||!attempt)return;busy=true;const version=epoch;autoRetryAt=Date.now()+10000;
    try{const data=await ctx.api(`/technical-practice/${encodeURIComponent(attempt.id)}/submit`,{method:'POST'});if(!active(version))return;accept(data);renderAttempt();}
    catch(error){if(active(version))notice('Your saved answers are retained. '+error.message);}finally{if(version===epoch)busy=false;}
  }
  async function render(context){
    const version=++epoch;ctx=context;attempt=null;busy=false;clearInterval(clock);ctx.setPage('Technical practice');ctx.setContextAction();
    document.querySelector('#app-content').innerHTML=shell();
    const rows=await ctx.api('/technical-practice');if(!active(version))return;
    document.querySelector('#technical-practice').innerHTML=`<section class="panel technical-intro"><span class="section-kicker">Technical foundations · Practice exam</span><h2>Think through the fundamentals.</h2><p>16 questions · 4 sections · 24 minutes. Every answer earns one point. No negative marking, camera or microphone required.</p><p>Get an immediate answer-by-answer report with explanations. Repeat attempts may contain the same versioned questions. This is separate from the full proctored placement assessment and does not alter its scoring.</p><button class="button button-primary" data-technical-start>Begin technical exam</button><p id="technical-notice" role="status"></p></section>${rows.length?`<section class="panel"><h2>Your attempts</h2>${rows.map(row=>`<button class="technical-saved" data-technical-open="${esc(row.id)}">${esc(new Date(row.created_at).toLocaleString())} · ${row.score==null?'Open attempt':row.score+'% · Review report'}</button>`).join('')}</section>`:''}`;
  }
  function register(){return window.PlaceAIStudentViews?.register('technical-practice',render);}if(!register())window.addEventListener('placeai:student-views-ready',register,{once:true});
  document.addEventListener('change',async event=>{
    if(!event.target.matches('[name=technical-answer]')||!active()||busy)return;
    const q=attempt.questions[position],option=Number(event.target.value),version=epoch,id=attempt.id;busy=true;
    document.querySelectorAll('.technical-options input').forEach(input=>input.disabled=true);
    try{await ctx.api(`/technical-practice/${encodeURIComponent(attempt.id)}/answer`,{method:'PUT',body:JSON.stringify({question_id:q.id,option})});if(active(version)&&attempt.id===id){attempt.answers[q.id]=option;renderAttempt();notice('Answer saved.');}}
    catch(error){if(active(version)){renderAttempt();notice(error.message+' Your previous saved answer is unchanged.');}}
    finally{if(version===epoch)busy=false;}
  });
  document.addEventListener('click',async event=>{
    const button=event.target.closest('[data-technical-start],[data-technical-new],[data-technical-open],[data-technical-question],[data-technical-move],[data-technical-submit]');if(!button||!active()||busy)return;
    if(button.hasAttribute('data-technical-start')||button.hasAttribute('data-technical-new'))return start();
    if(button.hasAttribute('data-technical-submit'))return submit();
    if(button.dataset.technicalOpen){busy=true;const version=epoch;try{const data=await ctx.api('/technical-practice/'+encodeURIComponent(button.dataset.technicalOpen));if(active(version)){accept(data);position=0;renderAttempt();}}catch(error){if(active(version))notice(error.message);}finally{if(version===epoch)busy=false;}return;}
    position=button.hasAttribute('data-technical-question')?Number(button.dataset.technicalQuestion):position+Number(button.dataset.technicalMove);renderAttempt();
  });
})();
