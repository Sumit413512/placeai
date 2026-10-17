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
    panel.innerHTML = `<section class="panel"><span class="section-kicker">Video learning</span><h2>A topic. A clear learning path.</h2><p>Learn in short narrated lessons with visual explanations, practice and saved progress.</p><form id="learning-video-form"><div class="learning-form-grid"><label>Video topic<input name="video_topic" required minlength="2" maxlength="180" placeholder="SQL for placement interviews"></label></div><p>Shared topic library: enter a subject, not personal information. From foundations to practical applications. Saved videos are reused for everyone; your progress stays private.</p><button class="button button-primary" type="submit">Find or create course</button></form><p data-video-status role="status"></p></section><section class="panel"><div class="panel-head"><h2>Your video courses</h2><button type="button" class="button button-secondary" data-video-refresh>Refresh</button></div><div data-video-library>Loading your courses…</div></section><div data-video-course></div><div data-video-player></div>`;
    hub.append(panel);
    let alive = true, current = null, course = null, poll = null, player = null, position = null;
    let urls = [], playerEpoch = 0, saving = false, lastSaved = 0, observer;
    const apiBase = '/learning-hub/video';
    const active = () => alive && hub.isConnected && ctx.state.view === 'learning-hub';
    const status = message => { if (active()) panel.querySelector('[data-video-status]').textContent = message; };
    const isCurrent = (id, version) => active() && current === id && playerEpoch === version;
    const libraryLabel = data => data.lessons.length ? `${data.videos_completed}/${data.lessons.length} viewed · ${data.status === 'ready' ? 'Ready' : data.status}` : data.status === 'failed' ? 'Preparation unavailable' : 'Preparing learning path';
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
    function showCourse(data) {
      data.videos_completed = data.lessons.filter(item => item.video_completed).length;
      data.practice_completed = data.lessons.filter(item => item.practice_completed).length;
      course = data;
      const saved = [...panel.querySelectorAll('[data-video-id]')].find(item => item.dataset.videoId === data.id);
      if (saved) saved.innerHTML = `<span>${esc(data.title)}</span><small>${esc(libraryLabel(data))}</small>`;
      const pending = ['queued', 'running', 'retrying'];
      const progress = `${data.videos_completed} of ${data.lessons.length} videos viewed · ${data.practice_completed} practices completed`;
      panel.querySelector('[data-video-course]').innerHTML = `<section class="panel"><h2>${esc(data.title)}</h2><p>${esc(data.introduction || (data.status === 'failed' ? 'We could not prepare this learning path after retries. Your existing courses are safe. Please try a new topic later.' : 'Researching sources and preparing your learning path. You can return later.'))}</p>${data.preparation_notice ? `<p role="status">${esc(data.preparation_notice)}</p>` : ''}${data.retry_available ? '<button type="button" class="button button-secondary" data-video-retry-course>Retry learning path</button>' : ''}${data.lessons.length ? `<p class="learning-meta">${esc(progress)}</p><progress aria-label="Videos viewed" max="${data.lessons.length}" value="${data.videos_completed}"></progress><ol class="learning-video-lessons">${data.lessons.map(item => `<li><div><h3>${esc(item.title)}</h3><p>${esc(item.objective)}</p><small>${item.video_completed ? 'Viewed' : 'Not completed'} · ${item.practice_completed ? 'Practice complete' : 'Practice pending'}${item.duration_seconds ? ` · ${Math.ceil(item.duration_seconds / 60)} min` : ''}</small></div><button type="button" class="button button-secondary" data-video-lesson="${item.position}" ${pending.includes(item.status) || (item.status === 'failed' && !item.retry_available) ? 'disabled' : ''}>${item.status === 'ready' ? (item.position_seconds ? 'Resume lesson' : 'Watch lesson') : item.status === 'failed' ? (item.retry_available ? 'Retry preparation' : 'Preparation unavailable') : pending.includes(item.status) ? (item.error_code === 'NARRATION_CAPACITY' ? 'Waiting for narration capacity' : 'Preparing…') : 'Prepare video'}</button></li>`).join('')}</ol>` : ''}<p class="learning-meta">AI-generated lessons use researched references and automated content checks. Examples have not been executed. Viewing progress is separate from practice completion.</p></section>`;
      clearTimeout(poll);
      if (pending.includes(data.status) || data.lessons.some(item => pending.includes(item.status))) {
        const id = current;
        poll = setTimeout(async () => { try { const next = await ctx.api(`${apiBase}/${encodeURIComponent(id)}`); if (active() && current === id) showCourse(next); } catch { status('Could not refresh preparation progress. Use Refresh to try again.'); } }, 8000);
      }
    }
    async function library() {
      const data = await ctx.api(apiBase);
      if (!active()) return;
      panel.querySelector('[data-video-library]').innerHTML = data.items.length ? data.items.map(item => `<button type="button" class="learning-library-item" data-video-id="${esc(item.id)}"><span>${esc(item.title)}</span><small>${esc(libraryLabel(item))}</small></button>`).join('') : '<p>Your saved video courses will appear here.</p>';
      if (!data.generation_available) status('New video preparation is temporarily unavailable. Your saved lessons remain accessible.');
      return data;
    }
    async function binary(path) {
      const response = await fetch(path, {credentials:'include', headers:ctx.state.token ? {Authorization:`Bearer ${ctx.state.token}`} : {}});
      if (!response.ok) throw new Error('The lesson could not be loaded. Refresh and try again.');
      return response.blob();
    }
    async function openLesson(index) {
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
      host.innerHTML = `<section class="panel"><h2>${esc(data.title)}</h2><p>${esc(content.objective)}</p><p class="learning-meta">AI-generated narration · Automatically timed captions · Full transcript below</p><video class="learning-video-player" controls playsinline preload="metadata" aria-label="${esc(data.title)}"><track kind="captions" srclang="en" label="English" default></video><label>Playback speed <select data-video-speed aria-label="Playback speed"><option value="0.75">0.75×</option><option value="1" selected>1×</option><option value="1.25">1.25×</option><option value="1.5">1.5×</option><option value="2">2×</option></select></label><p data-video-save-status role="status">Resume position is saved while you watch.</p><details><summary>Transcript and visual explanations</summary>${content.scenes.map(scene => `<section><h3>${esc(scene.title)}</h3><p>${esc(scene.narration)}</p>${scene.code ? `<pre><code>${esc(scene.code)}</code></pre>` : ''}${scene.diagram ? `<p>${esc(scene.diagram.explanation)}</p>` : ''}</section>`).join('')}</details><h3>Key takeaways</h3><ul>${content.takeaways.map(item => `<li>${esc(item)}</li>`).join('')}</ul><h3>Check your understanding</h3><form data-video-practice>${content.quiz.map((q,i) => `<fieldset><legend>${esc(q.question)}</legend>${q.options.map((option,j) => `<label class="learning-video-option"><input type="radio" name="q${i}" value="${j}" required> ${esc(option)}</label>`).join('')}</fieldset>`).join('')}<button class="button button-primary" type="submit">Check answers</button></form><div data-video-feedback aria-live="polite"></div><h3>Try it yourself</h3><p>${esc(content.exercise)}</p><div data-video-solution></div><h3>References</h3><ul>${content.sources.map(source => { let url; try { url = new URL(source.url); } catch { return ''; } return url.protocol === 'https:' && !url.username && !url.password ? `<li><a href="${esc(url.href)}" target="_blank" rel="noopener noreferrer">${esc(source.title)}</a></li>` : ''; }).join('')}</ul></section>`;
      player = host.querySelector('video'); position = index;
      player.src = videoUrl; player.querySelector('track').src = captionUrl;
      player.addEventListener('loadedmetadata', () => { if (player && isCurrent(id, version)) player.currentTime = data.position_seconds < data.duration_seconds - 2 ? data.position_seconds : 0; }, {once:true});
      player.addEventListener('error', () => status('Your browser could not play this video. Try an updated browser; the transcript and practice remain available below.'));
      player.addEventListener('timeupdate', () => { if (Date.now() - lastSaved >= 10000 && !player?.paused) saveProgress(); });
      player.addEventListener('pause', saveProgress); player.addEventListener('ended', saveProgress);
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
          stopPlayer(); current = data.id; showCourse(data); await library();
          status(data.status === 'ready' ? 'Course found. Saved videos are ready to reuse.' : 'Your course is saved. Matching requests share the same preparation.');
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
      const button = event.target.closest('[data-video-id],[data-video-lesson],[data-video-refresh],[data-video-retry-course]');
      if (!button || button.disabled) return; button.disabled = true;
      try {
        if (button.dataset.videoId) { await saveProgress(); stopPlayer(); current = button.dataset.videoId; const id = current; const data = await ctx.api(`${apiBase}/${encodeURIComponent(id)}`); if (active() && current === id) showCourse(data); }
        else if (button.hasAttribute('data-video-refresh')) { await library(); const id = current; if (id) { const data = await ctx.api(`${apiBase}/${encodeURIComponent(id)}`); if (active() && current === id) showCourse(data); } }
        else if (button.hasAttribute('data-video-retry-course')) { const id = current; const data = await ctx.api(`${apiBase}/${encodeURIComponent(id)}/retry`, {method:'POST'}); if (active() && current === id) showCourse(data); }
        else { const index = Number(button.dataset.videoLesson); const item = course.lessons[index];
          if (item.status === 'ready') await openLesson(index);
          else { const id = current; const data = await ctx.api(lessonPath(id,index), {method:'POST'}); if (active() && current === id) { showCourse(data); status('Your video is queued. Preparation can take several minutes; you can return later.'); } }
        }
      } catch (error) { status(error.message); }
      finally { if (button.isConnected) button.disabled = false; }
    });
    cleanup = () => { alive = false; clearTimeout(poll); observer?.disconnect(); stopPlayer(); };
    observer = new MutationObserver(() => { if (!hub.isConnected) cleanup(); });
    observer.observe(document.querySelector('#app-content'), {childList:true});
  }};
})();
