/* A focused, accessible reading surface. Visible position and completion are separate. */
(() => {
  'use strict';
  let cleanup=()=>{};
  window.PlaceAINotesReader={mount(ctx,book,helpers){
    cleanup();const article=document.querySelector('.learning-notebook');if(!article)return;
    const e=v=>ctx.esc(String(v??'')),sections=book.chapters.flatMap((chapter,i)=>chapter.subtopics.map((sub,j)=>({key:`${i+1}.${j+1}`,chapter,sub})));
    if(!sections.length)return;
    let state={sections:[],completed:0,total:sections.length,percent:0,last_section:null},current=sections[0].key,focus=false,alive=true,readingSize=18,saving=Promise.resolve(),lastActivity=Date.now(),lastPulse=Date.now(),bookmarkTimer;
    const controller=new AbortController();const signal=controller.signal;
    const active=()=>alive&&article.isConnected&&ctx.state.view==='learning-hub';
    const toolbar=document.createElement('div');toolbar.className='notes-reader-toolbar';toolbar.innerHTML='<button class="button button-secondary" data-notes-focus>Read in focus view</button><button class="button button-secondary" data-notes-track>Add to study plan</button><span data-notes-progress role="status"></span>';
    article.querySelector('.panel-head').after(toolbar);
    const reader=document.createElement('section');reader.className='notes-focus-reader';reader.hidden=true;reader.setAttribute('aria-label','Focused notes reader');article.querySelector('#learning-chapters').before(reader);
    function status(){if(active())toolbar.querySelector('[data-notes-progress]').textContent=`${state.percent}% marked complete · ${state.completed} of ${state.total} sections`;}
    function render(){
      const chosen=sections.find(s=>s.key===current)||sections[0],index=sections.indexOf(chosen),done=state.sections.some(s=>s.key===current&&s.completed);
      const example=ex=>`<section><h4>Worked example: ${e(ex.title)}</h4>${ex.code?`<p>${e(ex.language)} · Illustrative code</p><pre><code>${e(ex.code)}</code></pre>`:''}${helpers.prose(ex.explanation)}<h4>Expected result</h4>${helpers.prose(ex.expected_result)}</section>`;
      const names=new Set(chosen.chapter.subtopics.map(s=>s.title));
      const supplements=`<details class="notes-chapter-supplements"><summary>Chapter examples, practice and revision</summary>${chosen.chapter.examples.filter(ex=>!names.has(ex.subtopic)).map(example).join('')}${chosen.chapter.diagrams.filter(d=>!d.subtopics?.length).map(helpers.diagramHtml).join('')}<h4>Common mistakes</h4><ul>${chosen.chapter.common_mistakes.map(x=>`<li>${helpers.prose(x)}</li>`).join('')}</ul><h4>Practice and solutions</h4>${chosen.chapter.exercises.map(x=>`<section>${helpers.prose(x.question)}<details><summary>Show solution</summary>${helpers.prose(x.solution)}</details></section>`).join('')}<h4>Quick revision</h4><ul>${chosen.chapter.key_takeaways.map(x=>`<li>${helpers.prose(x)}</li>`).join('')}</ul>${helpers.teachingExtras(chosen.chapter)}</details>`;
      reader.innerHTML=`<div class="notes-focus-top"><button class="button button-secondary" data-notes-back>Back to notebook</button><span>${e(current)} · ${index+1} of ${sections.length} sections</span><label>Text size<select data-notes-size aria-label="Reading text size"><option value="18" ${readingSize===18?'selected':''}>Standard</option><option value="20" ${readingSize===20?'selected':''}>Large</option><option value="23" ${readingSize===23?'selected':''}>Extra large</option></select></label></div><div class="notes-reader-layout"><nav aria-label="Notes section outline">${sections.map(s=>`<button type="button" data-notes-section="${e(s.key)}" ${s.key===current?'aria-current="location"':''}><span aria-hidden="true">${state.sections.some(x=>x.key===s.key&&x.completed)?'✓':'○'}</span> ${e(s.key)} ${e(s.sub.title)}</button>`).join('')}</nav><div class="notes-focus-content" tabindex="0" aria-label="Section reading area"><small>${e(chosen.chapter.title)}</small><h3 tabindex="-1">${e(current+' · '+chosen.sub.title)}</h3>${helpers.prose(chosen.sub.explanation)}<p class="learning-citations">Sources: ${chosen.sub.source_ids.map(id=>`<a href="#learning-source-${Number(id)}">[${Number(id)}]</a>`).join(' ')}</p>${chosen.chapter.examples.filter(x=>x.subtopic===chosen.sub.title).map(example).join('')}${chosen.chapter.diagrams.filter(x=>x.subtopics?.includes(chosen.sub.title)).map(helpers.diagramHtml).join('')}${supplements}<div class="notes-reader-completion"><label><input type="checkbox" data-notes-complete ${done?'checked':''}>I have finished this section</label><p>Reading position saves automatically. Completion reflects your own check-in.</p></div><div class="notes-reader-navigation"><button class="button button-secondary" data-notes-move="-1" ${index===0?'disabled':''}>Previous section</button><button class="button button-primary" data-notes-move="1" ${index===sections.length-1?'disabled':''}>Next section</button></div></div></div>`;
      status();
    }
    function save(extra={}){
      const key=current;
      const operation=async()=>{
      if(!active())return;
      try{const next=await ctx.api(`/study-tracker/notes/${encodeURIComponent(book.id)}`,{method:'PUT',body:JSON.stringify({section_key:key,event_id:crypto.randomUUID(),...extra})});if(active()){state=next;status();}}
      catch(error){if(active())toolbar.querySelector('[data-notes-progress]').textContent='Reading position could not be saved. '+error.message;}
      };
      saving=saving.then(operation,operation);
      return saving;
    }
    function showFocus(key){current=sections.some(s=>s.key===key)?key:current;focus=true;reader.hidden=false;article.classList.add('notes-focus-active');render();reader.scrollIntoView({block:'start',behavior:'auto'});reader.querySelector('.notes-focus-content h3')?.focus({preventScroll:true});save();}
    article.addEventListener('click',event=>{
      const button=event.target.closest('[data-notes-focus],[data-notes-back],[data-notes-section],[data-notes-move],[data-notes-track]');if(!button||!active())return;
      lastActivity=Date.now();
      if(button.hasAttribute('data-notes-focus'))showFocus(state.last_section||current);
      else if(button.hasAttribute('data-notes-back')){focus=false;reader.hidden=true;article.classList.remove('notes-focus-active');toolbar.querySelector('[data-notes-focus]').focus();}
      else if(button.hasAttribute('data-notes-track')){window.PlaceAIStudy?.selectResource('notes',book.id);ctx.navigate('study-tracker');}
      else if(button.dataset.notesSection)showFocus(button.dataset.notesSection);
      else{const index=sections.findIndex(s=>s.key===current)+Number(button.dataset.notesMove);if(sections[index])showFocus(sections[index].key);}
    },{signal});
    reader.addEventListener('change',async event=>{
      if(event.target.matches('[data-notes-size]')){readingSize=Number(event.target.value);reader.style.setProperty('--notes-reading-size',readingSize+'px');}
      if(event.target.matches('[data-notes-complete]')){const input=event.target;input.disabled=true;await save({completed:input.checked});if(active()&&input.isConnected){input.checked=state.sections.some(s=>s.key===current&&s.completed);input.disabled=false;reader.querySelector(`[data-notes-section="${current}"] span`).textContent=input.checked?'✓':'○';}}
    },{signal});
    ['pointerdown','keydown','scroll'].forEach(name=>article.addEventListener(name,()=>{lastActivity=Date.now();},{signal,capture:true,passive:true}));
    const observer=new IntersectionObserver(entries=>{
      if(focus||!active()||document.hidden)return;
      const entry=entries.filter(x=>x.isIntersecting).sort((a,b)=>b.intersectionRatio-a.intersectionRatio)[0];
      if(entry&&entry.target.dataset.noteSection!==current){clearTimeout(bookmarkTimer);bookmarkTimer=setTimeout(()=>{if(!focus&&active()&&!document.hidden){current=entry.target.dataset.noteSection;save();}},1200);}
    },{threshold:[.1,.3,.6]});
    article.querySelectorAll('[data-note-section]').forEach(s=>observer.observe(s));
    const timer=setInterval(()=>{const now=Date.now(),seconds=Math.min(30,Math.floor((now-lastPulse)/1000));lastPulse=now;if(!active()){cleanup();return;}if(!document.hidden&&document.hasFocus()&&article.getClientRects().length&&now-lastActivity<90000)save({active_seconds:seconds});},30000);
    ctx.api(`/study-tracker/notes/${encodeURIComponent(book.id)}`).then(data=>{if(active()){state=data;status();const selection=window.PlaceAIStudySelection;if(selection?.kind==='notes'&&selection.id===book.id){window.PlaceAIStudySelection=null;showFocus(selection.section||data.last_section||current);}}}).catch(()=>{if(active())toolbar.querySelector('[data-notes-progress]').textContent='Progress will save when the tracker is available.';});
    cleanup=()=>{alive=false;clearInterval(timer);clearTimeout(bookmarkTimer);observer.disconnect();controller.abort();};
  }};
})();
