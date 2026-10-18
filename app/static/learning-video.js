/* Source-grounded video courses. No provider keys or learner data in public assets. */
(() => {
  'use strict';
  let cleanup = () => {};
  window.PlaceAIVideoLearning = {mount(ctx) {
    cleanup();
    const hub = document.querySelector('#learning-hub');
    if (!hub) return;
    const esc = value => ctx.esc(String(value ?? ''));
    const notes = [...hub.children];
    const navigation = document.createElement('div');
    navigation.className = 'learning-mode-switch';
    navigation.setAttribute('aria-label', 'Learning formats');
    navigation.innerHTML = '<button type="button" class="button button-secondary" aria-pressed="true" data-format="notes">Detailed notes</button><button type="button" class="button button-secondary" aria-pressed="false" data-format="video">Video learning</button>';
    hub.prepend(navigation);
    const panel = document.createElement('section');
    panel.className = 'learning-video-panel'; panel.hidden = true;
    panel.innerHTML = `<div data-video-discovery><section class="panel"><span class="section-kicker">Video learning</span><h2>One topic. A complete course.</h2><p>Build from the basics to advanced applications with AI-taught videos, worked examples and quizzes.</p><form id="learning-video-form"><div class="learning-form-grid"><label>Video topic<input name="video_topic" required minlength="2" maxlength="180" placeholder="Full SQL course"></label></div><p>Shared topic library: enter a subject, not personal information. From foundations to practical applications. Saved videos are reused for everyone; your progress stays private.</p><button class="button button-primary" type="submit">Find or create course</button></form></section><section class="panel"><div class="panel-head"><h2>Your video courses</h2><button type="button" class="button button-secondary" data-video-refresh>Refresh</button></div><div data-video-library>Loading your courses…</div></section></div><p data-video-status role="status"></p><section data-video-workspace hidden><div data-video-course></div><section data-video-overview class="panel"></section><div class="learning-video-study-layout" hidden><aside data-video-outline aria-label="Course outline"></aside><div data-video-player></div></div></section>`;
    hub.append(panel);
    let alive = true, current = null, course = null, poll = null, player = null, position = null, studying = false;
    let libraryPoll = null;
    let urls = [], playerEpoch = 0, saving = false, lastSaved = 0, observer;
    const apiBase = '/learning-hub/video';
    const active = () => alive && hub.isConnected && ctx.state.view === 'learning-hub';
    const status = message => { if (active()) panel.querySelector('[data-video-status]').textContent = message; };
    const isCurrent = (id, version) => active() && current === id && playerEpoch === version;
    const failedCourse = data => data.status === 'failed' || data.lessons.some(item => item.status === 'failed');
    const libraryLabel = data => structure(data).course_ready ? 'Ready to begin' :
      data.preparation_status === 'queued' ? 'Queued' : data.preparation_status === 'waiting_capacity' ? 'Waiting to retry' : 'Processing';
    const badge = data => `<small class="learning-status" data-state="${structure(data).course_ready ? 'ready' : 'processing'}">${libraryLabel(data)}</small>`;
    const lessonPath = (id, index) => `${apiBase}/${encodeURIComponent(id)}/lessons/${index}`;
    function stopPlayer() {
      playerEpoch += 1;
      if (player) { player.pause(); player.removeAttribute('src'); player.load(); player = null; }
      urls.forEach(url => URL.revokeObjectURL(url)); urls = [];
      panel.querySelector('[data-video-player]').replaceChildren(); position = null;
    }
    async function saveProgress() {
      if (!active() || !player || position === null || saving) return;
      const id = current, index = position, video = player;
      saving = true; lastSaved = Date.now();
      try {
        const progress = await ctx.api(`${lessonPath(id, index)}/progress`, {method:'PUT', body:JSON.stringify({position_seconds:video.currentTime})});
        if (active() && current === id && position === index) {
          const text = panel.querySelector('[data-video-save-status]');
          if (text) text.textContent = progress.video_completed ? 'Video viewing complete. Try the practice questions below.' : 'Playback progress saved.';
          if (course?.id === id) { Object.assign(course.lessons[index], progress); showCourse(course); }
        }
      } catch { if (active()) { const text = panel.querySelector('[data-video-save-status]'); if (text) text.textContent = 'Progress could not be saved. Check your connection.'; } }
      finally { saving = false; }
    }
    function structure(data) {
      const modules = [];
      data.lessons.forEach((item, index) => {
        const number = item.module_number || Math.floor(index / 2) + 1;
        let group = modules.find(module => module.number === number);
        if (!group) { group = {number, title:item.module_title || `Module ${number}`, positions:[]}; modules.push(group); }
        group.positions.push(index);
        item.number ||= `${number}.${group.positions.length}`;
      });
      data.modules = modules;
      data.videos_completed = data.lessons.filter(item => item.video_completed).length;
      data.practice_completed = data.lessons.filter(item => item.practice_completed).length;
      data.completed_parts = data.lessons.filter(item => item.video_completed && item.practice_completed).length;
      data.ready_parts = data.lessons.filter(item => item.status === 'ready').length;
      data.checked_parts = data.lessons.filter(item => item.status === 'ready' && item.quality_checked).length;
      data.course_ready = data.status === 'ready' && data.lessons.length > 0 && data.ready_parts === data.lessons.length && (!data.requires_full_preparation || data.checked_parts === data.lessons.length);
      data.completion_percent = data.lessons.length ? Math.round(100 * data.completed_parts / data.lessons.length) : 0;
      return data;
    }
    function updateLessonNavigation() {
      if (!course || position === null) return;
      for (const direction of [-1, 1]) {
        const button = panel.querySelector(`[data-video-move="${direction}"]`);
        if (!button) continue;
        const next = course.lessons[position + direction];
        button.disabled = !next || next.status !== 'ready';
        button.textContent = direction < 0 ? 'Previous lesson' : next ? `Next: ${next.number} ${next.title}` : 'End of course';
        button.title = next && next.status !== 'ready' ? 'This part is still being prepared. Saved lessons remain available.' : '';
      }
    }
    function showCourse(data) {
      if (failedCourse(data)) { stopPlayer(); clearTimeout(poll); current = null; course = null; studying = false; panel.querySelector('[data-video-discovery]').hidden = false; panel.querySelector('[data-video-workspace]').hidden = true; status(''); library().catch(() => {}); return; }
      course = structure(data);
      panel.querySelector('[data-video-discovery]').hidden = true;
      panel.querySelector('[data-video-workspace]').hidden = false;
      const saved = [...panel.querySelectorAll('[data-video-id]')].find(item => item.dataset.videoId === data.id);
      if (saved) saved.innerHTML = `<span>${esc(data.title)}</span>${badge(data)}`;
      const pending = ['queued', 'running', 'retrying'];
      const preparation = libraryLabel(data);
      const retryDate = data.next_retry_at ? new Date(data.next_retry_at) : null;
      const retryNotice = retryDate && Number.isFinite(retryDate.getTime()) ? ` Next automatic retry: ${retryDate.toLocaleString()}.` : '';
      panel.querySelector('[data-video-course]').innerHTML = `<header class="panel learning-video-course-header"><div><nav class="learning-video-breadcrumb" aria-label="Course navigation"><button type="button" class="button button-secondary" data-video-browse>All courses</button>${studying ? '<button type="button" class="button button-secondary" data-video-overview-back>Back to course</button>' : ''}</nav><h2>${esc(data.title)}</h2><p class="learning-video-preparation"><span class="learning-status" data-state="${data.course_ready ? 'ready' : 'processing'}">${esc(preparation)}</span></p>${data.preparation_notice && !data.course_ready ? `<p class="learning-meta">${esc(data.preparation_notice + retryNotice)}</p>` : ''}${data.retry_available ? '<button type="button" class="button button-secondary" data-video-retry-course>Retry learning path</button>' : ''}</div><div class="learning-video-course-progress" ${data.course_ready ? '' : 'hidden'}><strong>${data.completion_percent}% complete</strong><progress aria-label="Course completion" max="100" value="${data.completion_percent}"></progress><small>Your learning progress · Video + quiz</small></div></header>`;
      panel.querySelector('[data-video-outline]').innerHTML = `<details class="learning-video-outline-disclosure" open><summary>Course outline</summary><nav aria-label="Course lessons">${data.modules.map(module => `<section class="learning-video-module"><h3>${esc(module.title)}</h3><ol class="learning-video-lessons">${module.positions.map(index => {
        const item = data.lessons[index], complete = item.video_completed && item.practice_completed;
        const waiting = pending.includes(item.status), unavailable = item.status === 'failed' && !item.retry_available;
        const label = item.status === 'ready' ? complete ? 'Complete' : item.video_completed ? 'Video viewed · Quiz pending' : item.position_seconds ? 'Resume lesson' : 'Watch lesson' : item.status === 'failed' ? item.retry_available ? 'Retry preparation' : 'Preparation unavailable' : waiting ? ['NARRATION_CAPACITY','REVIEW_CAPACITY'].includes(item.error_code) ? 'Waiting for capacity' : 'Preparing' : 'Prepare video';
        return `<li><button type="button" data-video-lesson="${index}" ${waiting || unavailable ? 'disabled' : ''} ${position === index ? 'aria-current="step"' : ''} data-complete="${complete}"><span class="learning-video-step" aria-hidden="true">${complete ? '✓' : item.status === 'ready' ? '▶' : '○'}</span><span><span class="learning-video-lesson-title">${esc(item.number)} ${esc(item.title)}</span><small>${esc(label)}${item.duration_seconds ? ` · ${Math.ceil(item.duration_seconds / 60)} min` : ''}</small></span></button></li>`;
      }).join('')}</ol></section>`).join('')}</nav></details>`;
      panel.querySelector('[data-video-overview]').hidden = studying;
      panel.querySelector('.learning-video-study-layout').hidden = !studying;
      const first = data.lessons.find(item => item.status === 'ready' && !(item.video_completed && item.practice_completed)) || data.lessons.find(item => item.status === 'ready');
      const mayBegin = first && data.course_ready;
      const overview = panel.querySelector('[data-video-overview]');
      const signature = JSON.stringify([data.introduction, data.prerequisites, data.modules, data.lessons, data.course_ready]);
      if (overview.dataset.signature !== signature) {
        const expanded = [...overview.querySelectorAll('details[open]')].map(item => item.dataset.module);
        overview.innerHTML = `<h2 tabindex="-1" data-video-overview-title>Course overview</h2><p>${esc(data.introduction || 'We are researching the subject and building its syllabus in prerequisite order. Return later; preparation continues in the background.')}</p><p class="learning-meta">${data.modules.length} modules · ${data.lessons.length} videos · A quick quiz and practice exercise with each lesson</p>${data.prerequisites?.length ? `<h3>Before you start</h3><ul>${data.prerequisites.map(item => `<li>${esc(item)}</li>`).join('')}</ul>` : ''}${data.requires_full_preparation ? `<section class="learning-video-quality" aria-label="Course preparation checks"><h3>Preparation and recheck</h3><ol><li>${data.status === 'ready' ? 'Syllabus coverage reviewed' : 'Researching and reviewing the syllabus'}</li><li>${data.course_ready ? 'Videos prepared' : 'Processing videos'}</li><li>${data.course_ready ? 'Content and media checks passed' : 'Processing quality checks'}</li></ol><p>Checks cover lesson accuracy, quiz answers, readable slides, decodable audio/video, matching scene timelines and an AI review of the rendered audio and visuals. Generated lesson videos and scripts are reviewed with Google Gemini; no student recordings are used. AI checks can miss errors; word-level timing is estimated.</p><p>${data.course_ready ? 'All lessons passed their checks. Your course is ready to begin.' : 'The full course opens after every lesson is prepared and checked. Preparation may span several days when provider allowances are limited. You can leave this page and return later.'}</p></section>` : ''}${mayBegin ? `<button type="button" class="button button-primary" data-video-begin>${data.completed_parts ? 'Continue learning' : 'Begin learning'}</button>` : '<p role="status">Preparing your full course. Begin learning will appear when it is ready.</p>'}<h3>Course syllabus</h3><div class="learning-video-syllabus">${data.modules.map(module => `<details data-module="${module.number}" ${expanded.includes(String(module.number)) ? 'open' : ''}><summary><span>Module ${module.number}: ${esc(module.title)}</span><small>${module.positions.length} videos + quizzes</small></summary><ol>${module.positions.map(index => {const item=data.lessons[index]; return `<li><span>${esc(item.number)} ${esc(item.title)}</span><small>${esc(item.objective)}${item.video_completed && item.practice_completed ? ' · Complete' : ''}</small>${item.retry_available ? `<button type="button" class="button button-secondary" data-video-lesson="${index}">Retry lesson ${esc(item.number)}</button>` : ''}</li>`;}).join('')}</ol></details>`).join('')}</div>`;
        overview.dataset.signature = signature;
      }
      updateLessonNavigation();
      clearTimeout(poll);
      if (!data.course_ready) {
        const id = current;
        poll = setTimeout(async () => { try { const next = await ctx.api(`${apiBase}/${encodeURIComponent(id)}`); if (active() && current === id) showCourse(next); } catch { status('Could not refresh preparation progress. Use All courses to refresh.'); } }, 8000);
      }
    }
    async function library() {
      const data = await ctx.api(apiBase);
      if (!active()) return;
      data.items = data.items.filter(item => !failedCourse(item));
      clearTimeout(libraryPoll);
      if (!current && !panel.hidden && data.items.some(item => !structure(item).course_ready)) libraryPoll = setTimeout(() => { if (active() && !current && !panel.hidden) library().catch(() => {}); }, 8000);
      panel.querySelector('[data-video-library]').innerHTML = data.items.length ? data.items.map(item => `<button type="button" class="learning-library-item" data-video-id="${esc(item.id)}"><span>${esc(item.title)}</span>${badge(item)}</button>`).join('') : '<p>Your saved video courses will appear here.</p>';
      if (!data.generation_available) status('New video preparation is temporarily unavailable. Your saved lessons remain accessible.');
      return data;
    }
    async function binary(path) {
      const response = await fetch(path, {credentials:'include', headers:ctx.state.token ? {Authorization:`Bearer ${ctx.state.token}`} : {}});
      if (!response.ok) throw new Error('The lesson could not be loaded. Refresh and try again.');
      return response.blob();
    }
    async function openLesson(index) {
      if (!course?.course_ready) { status('Your full course is still being prepared and checked.'); return; }
      await saveProgress(); stopPlayer();
      const id = current, version = playerEpoch;
      status('Loading your lesson…');
      const data = await ctx.api(lessonPath(id, index));
      if (!isCurrent(id, version)) return;
      if (data.status !== 'ready') { status('This video is still being prepared.'); return; }
      const [media, captions] = await Promise.all([binary(`${lessonPath(id,index)}/media`), binary(`${lessonPath(id,index)}/captions`)]);
      if (!isCurrent(id, version)) return;
      const videoUrl = URL.createObjectURL(media), captionUrl = URL.createObjectURL(captions); urls.push(videoUrl, captionUrl);
      const content = data.content;
      const host = panel.querySelector('[data-video-player]');
      const outline = course.lessons[index];
      host.innerHTML = `<section class="panel learning-video-lesson-panel"><p class="learning-meta">Lesson ${esc(outline.number)}</p><h2>${esc(data.title)}</h2><p>${esc(content.objective)}</p><video class="learning-video-player" controls playsinline preload="metadata" aria-label="${esc(data.title)}"><track kind="captions" srclang="en" label="English" default></video><div class="learning-video-playback-tools"><label>Playback speed <select data-video-speed aria-label="Playback speed"><option value="0.75">0.75×</option><option value="1" selected>1×</option><option value="1.25">1.25×</option><option value="1.5">1.5×</option><option value="2">2×</option></select></label><small>AI narration · Captions available</small></div><p data-video-save-status role="status">Resume position is saved while you watch.</p><section class="learning-video-quiz" aria-label="Quick quiz"><h3>Quick quiz</h3><p>Check what you learned in this lesson.</p><form data-video-practice>${content.quiz.map((q,i) => `<fieldset><legend>${esc(q.question)}</legend>${q.options.map((option,j) => `<label class="learning-video-option"><input type="radio" name="q${i}" value="${j}" required> ${esc(option)}</label>`).join('')}</fieldset>`).join('')}<button class="button button-primary" type="submit">Check answers</button></form><div data-video-feedback aria-live="polite"></div></section><div class="learning-video-lesson-navigation" aria-label="Lesson navigation"><button type="button" class="button button-secondary" data-video-move="-1">Previous lesson</button><button type="button" class="button button-primary" data-video-move="1">Next lesson</button></div><details><summary>Key takeaways and practice exercise</summary><ul>${content.takeaways.map(item => `<li>${esc(item)}</li>`).join('')}</ul><h3>Try it yourself</h3><p>${esc(content.exercise)}</p><div data-video-solution></div></details><details><summary>Transcript and visual explanations</summary>${content.scenes.map(scene => `<section><h3>${esc(scene.title)}</h3><p>${esc(scene.narration)}</p>${scene.code ? `<pre><code>${esc(scene.code)}</code></pre>` : ''}${scene.diagram ? `<p>${esc(scene.diagram.explanation)}</p>` : ''}</section>`).join('')}</details><details><summary>Research references</summary><p class="learning-meta">AI-authored explanations use these references. Examples have not been executed.</p><ul>${content.sources.map(source => { let url; try { url = new URL(source.url); } catch { return ''; } return url.protocol === 'https:' && !url.username && !url.password ? `<li><a href="${esc(url.href)}" target="_blank" rel="noopener noreferrer">${esc(source.title)}</a></li>` : ''; }).join('')}</ul></details></section>`;
      player = host.querySelector('video'); position = index; studying = true;
      player.src = videoUrl; player.querySelector('track').src = captionUrl;
      player.addEventListener('loadedmetadata', () => { if (player && isCurrent(id, version)) player.currentTime = data.position_seconds < data.duration_seconds - 2 ? data.position_seconds : 0; }, {once:true});
      player.addEventListener('error', () => status('Your browser could not play this video. Try an updated browser; the transcript and practice remain available below.'));
      player.addEventListener('timeupdate', () => { if (Date.now() - lastSaved >= 10000 && !player?.paused) saveProgress(); });
      const mounted = player;
      const saveMounted = () => { if (isCurrent(id, version) && player === mounted) saveProgress(); };
      player.addEventListener('pause', saveMounted); player.addEventListener('ended', saveMounted);
      showCourse(course);
      status('');
      host.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion:reduce)').matches ? 'instant' : 'smooth', block:'start'});
    }
    navigation.addEventListener('click', event => {
      const button = event.target.closest('[data-format]'); if (!button) return;
      const video = button.dataset.format === 'video';
      navigation.querySelectorAll('button').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
      notes.forEach(item => { item.hidden = video; }); panel.hidden = !video;
      if (!video) { saveProgress(); player?.pause(); }
      else library().catch(error => status(error.message));
    });
    panel.addEventListener('change', event => { if (event.target.matches('[data-video-speed]') && player) player.playbackRate = Number(event.target.value); });
    panel.addEventListener('submit', async event => {
      event.preventDefault(); const form = event.target, button = form.querySelector('[type="submit"]');
      if (button.disabled) return; button.disabled = true;
      const id = current, index = position, version = playerEpoch;
      try {
        if (form.id === 'learning-video-form') {
          const fields = Object.fromEntries(new FormData(form));
          fields.topic = fields.video_topic; delete fields.video_topic;

          const fingerprint = JSON.stringify(fields);
          if (form.dataset.fingerprint !== fingerprint) { form.dataset.fingerprint = fingerprint; form.dataset.requestId = crypto.randomUUID(); }
          const data = await ctx.api(apiBase, {method:'POST', body:JSON.stringify({...fields, request_id:form.dataset.requestId})});
          if (!active()) return;
          stopPlayer(); studying = false; current = data.id; showCourse(data); await library();
          status('');
          delete form.dataset.fingerprint; delete form.dataset.requestId;
        } else if (form.matches('[data-video-practice]') && index !== null) {
          const values = new FormData(form);
          const result = await ctx.api(`${lessonPath(id,index)}/practice`, {method:'POST', body:JSON.stringify({answers:[0,1,2].map(i => Number(values.get(`q${i}`)))})});
          if (!isCurrent(id, version)) return;
          panel.querySelector('[data-video-feedback]').innerHTML = result.results.map((item,i) => `<p>${i+1}. ${item.correct ? 'Correct' : 'Review this answer'}: ${esc(item.explanation)}</p>`).join('') + `<p>${result.practice_completed ? 'Practice completed.' : 'Review the explanations and try again.'}</p>`;
          panel.querySelector('[data-video-solution]').innerHTML = `<details><summary>Exercise solution</summary><p>${esc(result.solution)}</p></details>`;
          Object.assign(course.lessons[index], result); course.practice_completed = course.lessons.filter(item => item.practice_completed).length; showCourse(course);
        }
      } catch (error) { status(error.message); }
      finally { if (button.isConnected) button.disabled = false; }
    });
    panel.addEventListener('click', async event => {
      const button = event.target.closest('[data-video-id],[data-video-lesson],[data-video-refresh],[data-video-retry-course],[data-video-move],[data-video-browse],[data-video-begin],[data-video-overview-back]');
      if (!button || button.disabled) return; button.disabled = true;
      try {
        if (button.hasAttribute('data-video-browse')) { await saveProgress(); stopPlayer(); clearTimeout(poll); current = null; course = null; studying = false; panel.querySelector('[data-video-discovery]').hidden = false; panel.querySelector('[data-video-workspace]').hidden = true; status(''); await library(); }
        else if (button.hasAttribute('data-video-overview-back')) { await saveProgress(); stopPlayer(); studying = false; showCourse(course); panel.querySelector('[data-video-overview-title]').focus(); }
        else if (button.hasAttribute('data-video-begin')) { const first = course.lessons.find(item => item.status === 'ready' && !(item.video_completed && item.practice_completed)) || course.lessons.find(item => item.status === 'ready'); if (first) await openLesson(first.position); }
        else if (button.hasAttribute('data-video-move')) { const next = position + Number(button.dataset.videoMove); if (course?.lessons[next]?.status === 'ready') await openLesson(next); }
        else if (button.dataset.videoId) { await saveProgress(); stopPlayer(); studying = false; current = button.dataset.videoId; const id = current; const data = await ctx.api(`${apiBase}/${encodeURIComponent(id)}`); if (active() && current === id) showCourse(data); }
        else if (button.hasAttribute('data-video-refresh')) { await library(); const id = current; if (id) { const data = await ctx.api(`${apiBase}/${encodeURIComponent(id)}`); if (active() && current === id) showCourse(data); } }
        else if (button.hasAttribute('data-video-retry-course')) { const id = current; const data = await ctx.api(`${apiBase}/${encodeURIComponent(id)}/retry`, {method:'POST'}); if (active() && current === id) showCourse(data); }
        else { const index = Number(button.dataset.videoLesson); const item = course.lessons[index];
          if (item.status === 'ready') { if (!player || position !== index) await openLesson(index); }
          else { const id = current; const data = await ctx.api(lessonPath(id,index), {method:'POST'}); if (active() && current === id) { showCourse(data); status('Your video is queued. Preparation can take several minutes; you can return later.'); } }
        }
      } catch (error) { status(error.message); }
      finally { if (button.isConnected) button.disabled = false; }
    });
    cleanup = () => { alive = false; clearTimeout(poll); clearTimeout(libraryPoll); observer?.disconnect(); stopPlayer(); };
    observer = new MutationObserver(() => { if (!hub.isConnected) cleanup(); });
    observer.observe(document.querySelector('#app-content'), {childList:true});
  }};
})();
