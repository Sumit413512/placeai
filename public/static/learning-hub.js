(() => {
  'use strict';
  let context = null, selected = null, timer = null, libraryTimer = null, epoch = 0;
  const root = () => document.querySelector('#learning-hub');
  const active = version => version === epoch && context?.state.view === 'learning-hub' && root();
  const e = value => context.esc(String(value ?? ''));
  // Escape first. Only this small formatting vocabulary can create markup.
  const inline = value => e(value).replace(/\*\*([^*\n]{1,200})\*\*/g, '<strong>$1</strong>');
  function prose(value) {
    const lines = String(value || '').split(/\n+/).filter(line => line.trim());
    let html = '', mode = '';
    for (const line of lines) {
      const bullet = line.match(/^\s*[-•]\s+(.+)/), step = line.match(/^\s*\d+[.)]\s+(.+)/);
      const next = bullet ? 'ul' : step ? 'ol' : '';
      if (mode && mode !== next) html += `</${mode}>`;
      if (next && mode !== next) html += `<${next}>`;
      html += next ? `<li>${inline((bullet || step)[1])}</li>` : `<p>${inline(line)}</p>`;
      mode = next;
    }
    return html + (mode ? `</${mode}>` : '');
  }
  const list = values => `<ul>${(values || []).map(value => `<li>${inline(value)}</li>`).join('')}</ul>`;
  function teachingExtras(chapter) {
    const tables = (chapter.comparisons || []).map(table => `<section><h3>${e(table.title)}</h3><div class="learning-table-wrap" role="region" aria-label="${e(table.title)}" tabindex="0"><table class="learning-comparison"><caption>${e(table.title)}</caption><thead><tr>${table.columns.map(column => `<th scope="col">${e(column)}</th>`).join('')}</tr></thead><tbody>${table.rows.map(row => `<tr>${row.map(cell => `<td>${inline(cell)}</td>`).join('')}</tr>`).join('')}</tbody></table></div></section>`).join('');
    const formulas = (chapter.formulas || []).map(formula => `<section class="learning-formula"><h3>${e(formula.title)}</h3><pre aria-label="Formula"><code>${e(formula.expression)}</code></pre><h4>Variables</h4><dl>${formula.variables.map(v => `<dt>${e(v.term)}</dt><dd>${prose(v.meaning)}</dd>`).join('')}</dl><h4>Worked calculation</h4>${prose(formula.worked_example)}<h4>Interpretation</h4>${prose(formula.interpretation)}</section>`).join('');
    const terms = chapter.key_terms?.length ? `<section><h3>Key terms</h3><dl class="learning-key-terms">${chapter.key_terms.map(term => `<dt>${e(term.term)}</dt><dd>${prose(term.meaning)}</dd>`).join('')}</dl></section>` : '';
    const exams = chapter.exam_focus?.length ? `<section><h3>Important for exams</h3>${list(chapter.exam_focus)}</section>` : '';
    const interviews = chapter.interview_questions?.length ? `<section><h3>Interview insight</h3>${chapter.interview_questions.map(item => `<details class="learning-exercise"><summary>${e(item.question)}</summary>${prose(item.solution)}</details>`).join('')}</section>` : '';
    return tables + formulas + terms + exams + interviews;
  }
  function sourceUrl(value) {
    try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password ? url.href : ''; }
    catch { return ''; }
  }
  function diagramHtml(diagram) {
    const nodes = new Map(diagram.nodes.map(node => [node.id, node.label]));
    return `<figure class="learning-diagram"><figcaption>${e(diagram.title)}</figcaption>${diagram.edges.map(edge =>
      `<div class="learning-relationship"><span>${e(nodes.get(edge.source))}</span><div><small>${e(edge.label)}</small><i aria-hidden="true">→</i></div><span>${e(nodes.get(edge.target))}</span></div>`
    ).join('')}${prose(diagram.explanation)}</figure>`;
  }
  function chapterHtml(chapter, index) {
    return `<details class="learning-chapter" ${index === 0 ? 'open' : ''}><summary>${String(index + 1).padStart(2, '0')}. ${e(chapter.title)}</summary><div class="learning-chapter-body">${prose(chapter.overview)}${chapter.subtopics.map(sub =>
      `<section><h3>${e(sub.title)}</h3>${prose(sub.explanation)}<p class="learning-citations">Sources: ${sub.source_ids.map(id => `<a href="#learning-source-${Number(id)}">[${Number(id)}]</a>`).join(' ')}</p></section>`
    ).join('')}${chapter.examples.map(example => `<section><h3>Worked example: ${e(example.title)}</h3>${example.code ? `<small>${e(example.language)}</small><pre><code>${e(example.code)}</code></pre>` : ''}${prose(example.explanation)}<h4>Expected result</h4>${prose(example.expected_result)}</section>`).join('')}${chapter.diagrams.map(diagramHtml).join('')}${teachingExtras(chapter)}<h3>Common mistakes</h3>${list(chapter.common_mistakes)}<h3>Practice and solutions</h3>${chapter.exercises.map(exercise => `<div class="learning-exercise">${prose(exercise.question)}<details><summary>Show solution and reasoning</summary>${prose(exercise.solution)}</details></div>`).join('')}<h3>Quick revision</h3>${list(chapter.key_takeaways)}${chapter.next_topics?.length ? `<h3>What to learn next</h3>${list(chapter.next_topics)}` : ''}</div></details>`;
  }
  const isReady = book => book.status === 'ready' && book.total_chapters > 0 && book.completed_chapters === book.total_chapters && book.pdf_available !== false;
  const badge = book => `<small class="learning-status" data-state="${isReady(book) ? 'ready' : 'processing'}">${isReady(book) ? 'Ready to begin' : 'Processing'}</small>`;
  function notebookHtml(book) {
    const ready = isReady(book);
    if (!ready) return `<article class="panel learning-notebook"><div class="panel-head"><h2>${e(book.title)}</h2>${badge(book)}</div><p role="status">Your complete notes are being prepared and checked. You can leave this page and return later.</p></article>`;
    return `<article class="panel learning-notebook"><div class="panel-head"><div><span class="section-kicker">Your learning notebook</span><h2>${e(book.title)}</h2></div>${ready ? '<button class="button button-primary" data-learning-action="pdf">Download complete PDF</button>' : ''}</div><p role="status">Ready to begin</p>${book.plan?.introduction ? `<div class="learning-introduction">${prose(book.plan.introduction)}<h3>Before you begin</h3>${list(book.plan.prerequisites)}<details class="learning-outline"><summary>Full chapter outline</summary><ol>${book.plan.chapters.map(ch => `<li>${e(ch.title)}${list(ch.subtopics)}</li>`).join('')}</ol></details></div>` : ''}<div id="learning-chapters">${(book.chapters || []).map(chapterHtml).join('')}</div>${book.sources?.length ? `<section class="learning-sources"><h3>Research sources</h3><p>AI-authored explanations use the references below. Consult official documentation for version-specific details. Code examples are illustrative and have not been executed by PlaceAI.</p><ol>${book.sources.map((s, i) => { const url = sourceUrl(s.url); return `<li id="learning-source-${i + 1}">${url ? `<a href="${e(url)}" target="_blank" rel="noopener noreferrer">${e(s.title)}</a>` : e(s.title)}</li>`; }).join('')}</ol></section>` : ''}</article>`;
  }
  function showBook(book) {
    if (book.status === 'failed') { selected = null; clearTimeout(timer); document.querySelector('#learning-notebook-result')?.replaceChildren(); refreshLibrary(epoch).catch(() => {}); return; }
    selected = book.id;
    const saved = [...document.querySelectorAll('[data-learning-id]')].find(item => item.dataset.learningId === book.id);
    if (saved) saved.innerHTML = `<span>${e(book.title)}</span>${badge(book)}`;
    const output = document.querySelector('#learning-notebook-result');
    if (!output) return;
    const signature = [book.id, book.status, book.completed_chapters, book.sources?.length, book.plan?.title].join('|');
    // Preserve expanded chapters during progress updates.
    if (output.dataset.learningSignature !== signature) {
    const open = new Set([...output.querySelectorAll('.learning-chapter[open]')].map(item => item.querySelector('summary').textContent));
    output.innerHTML = notebookHtml(book);
    output.querySelectorAll('.learning-chapter').forEach(item => { if (open.has(item.querySelector('summary').textContent)) item.open = true; });
    output.dataset.learningSignature = signature;
    }
    clearTimeout(timer);
    if (!isReady(book)) {
      const version = epoch;
      const notebookId = selected;
      timer = setTimeout(async () => {
        if (!active(version)) return;
        try { const next = await context.api(`/learning-hub/${encodeURIComponent(notebookId)}`); if (active(version) && selected === notebookId) showBook(next); }
        catch (error) { if (active(version)) { document.querySelector('#learning-refresh-status').textContent = 'Could not refresh progress. Use Refresh to check again.'; } }
      }, 8000);
    }
  }
  async function refreshLibrary(version) {
    const library = await context.api('/learning-hub');
    if (!active(version)) return;
    library.items = library.items.filter(book => book.status !== 'failed');
    clearTimeout(libraryTimer);
    if (library.items.some(book => !isReady(book))) libraryTimer = setTimeout(() => { if (active(version)) refreshLibrary(version).catch(() => {}); }, 8000);
    document.querySelector('#learning-library').innerHTML = library.items.length ? library.items.map(book =>
      `<button type="button" class="learning-library-item" data-learning-id="${e(book.id)}"><span>${e(book.title)}</span>${badge(book)}</button>`).join('') : '<p>Your saved notebooks will appear here.</p>';
    document.querySelector('#learning-service-status').textContent = library.generation_available ? '' : 'Research is temporarily unavailable. You can still read and download your saved notes.';
    return library;
  }
  async function render(ctx) {
    context = ctx; epoch += 1; clearTimeout(timer); clearTimeout(libraryTimer);
    const version = epoch;
    ctx.setPage('Learning Hub', 'Student workspace'); ctx.setContextAction();
    document.querySelector('#app-content').innerHTML = `${ctx.pageHead('Learning Hub', 'Learn a language, technology or field through detailed notes and video lessons tailored to your goal.')}<div id="learning-hub"><section class="panel"><div class="panel-head"><div><span class="section-kicker">Build your study notebook</span><h2>What would you like to learn?</h2><p>Web research, detailed explanations, worked examples, diagrams and solved exercises.</p></div></div><form id="learning-hub-form"><div class="learning-form-grid"><label>Topic or subject<input name="topic" required minlength="2" maxlength="180" placeholder="SQL, Python, data analysis, networking…"></label><label>Field or career direction<input name="field" maxlength="180" placeholder="Backend development, data engineering…"></label><label>Programming language or tool<input name="programming_language" maxlength="120" placeholder="PostgreSQL, Java, Python…"></label><label>Current level<select name="level"><option value="beginner">Beginner</option><option value="intermediate">Intermediate</option><option value="advanced">Advanced</option></select></label><label>Depth<select name="chapters"><option value="8">Detailed · 8 chapters</option><option value="12" selected>Comprehensive · 12 chapters</option><option value="16">Extended · 16 chapters</option></select></label><label class="learning-wide">What should your notes cover?<textarea name="goals" maxlength="2000" rows="4" placeholder="For example: learn SQL from foundations to joins, subqueries, indexes and transactions, with explained queries and practical exercises."></textarea></label></div><p>Notes are written in English, chapter by chapter. The full PDF becomes available after every chapter is complete.</p><p id="learning-service-status" role="status"></p><p id="learning-form-status" role="status"></p><button class="button button-primary" type="submit">Research and create detailed notes</button></form></section><section class="panel"><div class="panel-head"><h2>Your notebooks</h2><button class="button button-secondary" data-learning-action="refresh">Refresh</button></div><p id="learning-refresh-status" role="status"></p><div id="learning-library">Loading saved notebooks…</div></section><div id="learning-notebook-result"></div></div>`;
    window.PlaceAIVideoLearning?.mount(ctx);
    const library = await refreshLibrary(version);
    if (!active(version)) return;
    const id = selected && library.items.some(book => book.id === selected) ? selected : library.items[0]?.id;
    if (id) { const book = await ctx.api(`/learning-hub/${encodeURIComponent(id)}`); if (active(version)) showBook(book); }
  }
  function register() { return window.PlaceAIStudentViews?.register('learning-hub', render); }
  if (!register()) window.addEventListener('placeai:student-views-ready', register, {once:true});
  document.addEventListener('submit', async event => {
    if (event.target.id !== 'learning-hub-form') return;
    event.preventDefault();
    const form = event.target, button = form.querySelector('[type="submit"]'), version = epoch;
    if (button.disabled) return;
    button.disabled = true;
    const fields = Object.fromEntries(new FormData(form));
    // Keep the key across a network retry only while the exact preferences remain the same.
    const fingerprint = JSON.stringify(fields);
    if (form.dataset.fingerprint !== fingerprint) { form.dataset.requestId = crypto.randomUUID(); form.dataset.fingerprint = fingerprint; }
    try {
      const book = await context.api('/learning-hub', {method:'POST', body:JSON.stringify({...fields, chapters:Number(fields.chapters), request_id:form.dataset.requestId})});
      if (active(version)) { form.dataset.requestId = ''; form.dataset.fingerprint = ''; document.querySelector('#learning-form-status').textContent = 'Your notebook has been saved and queued for research.'; showBook(book); await refreshLibrary(version); }
    } catch (error) { if (active(version)) document.querySelector('#learning-form-status').textContent = error.message; }
    finally { if (form.isConnected) button.disabled = false; }
  });
  document.addEventListener('click', async event => {
    const button = event.target.closest('[data-learning-action], [data-learning-id]');
    if (!button || !root() || context?.state.view !== 'learning-hub') return;
    const version = epoch;
    if (button.disabled) return;
    button.disabled = true;
    try {
      if (button.dataset.learningId) { selected = button.dataset.learningId; clearTimeout(timer); const book = await context.api(`/learning-hub/${encodeURIComponent(selected)}`); if (active(version) && selected === book.id) showBook(book); }
      else if (button.dataset.learningAction === 'refresh') { await refreshLibrary(version); if (selected && active(version)) { const book = await context.api(`/learning-hub/${encodeURIComponent(selected)}`); if (active(version)) { showBook(book); document.querySelector('#learning-refresh-status').textContent = ''; } } }
      else if (button.dataset.learningAction === 'retry') { const book = await context.api(`/learning-hub/${encodeURIComponent(selected)}/retry`, {method:'POST'}); if (active(version)) showBook(book); }
      else if (button.dataset.learningAction === 'pdf') {
        const response = await fetch(`/learning-hub/${encodeURIComponent(selected)}/pdf`, {credentials:'include', headers:context.state.token ? {Authorization:`Bearer ${context.state.token}`} : {}});
        if (!response.ok) throw new Error('The PDF could not be downloaded. Refresh your notebook and try again.');
        const blob = await response.blob(), url = URL.createObjectURL(blob), link = document.createElement('a');
        link.href = url; link.download = 'PlaceAI-Learning-Notes.pdf'; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 10000);
      }
    } catch (error) { if (active(version)) document.querySelector('#learning-refresh-status').textContent = error.message; }
    finally { if (button.isConnected) button.disabled = false; }
  });
})();
