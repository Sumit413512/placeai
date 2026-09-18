(() => {
  'use strict';
  const $ = (s, root = document) => root.querySelector(s);
  const esc = (value = '') => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const apiErrors = window.PlaceAIApiErrors;
  const state = { token:'', jobs:[], session:null };

  function toast(message, type='') {
    const node = $('#toast');
    node.textContent = message;
    node.className = `toast ${type}`.trim();
    setTimeout(() => node.classList.add('hidden'), 4200);
  }

  let refreshPromise = null;
  async function refreshToken() {
    if (refreshPromise) return refreshPromise;
    refreshPromise = (async () => {
      const response = await fetch('/auth/refresh', {
        method:'POST', headers:{'Content-Type':'application/json'}, credentials:'include', body:'{}'
      });
      if (!response.ok) return false;
      const data = await response.json();
      state.token = data.access_token || '';
      return Boolean(state.token);
    })().finally(() => { refreshPromise = null; });
    return refreshPromise;
  }

  async function api(path, options={}) {
    if (!state.token && !(await refreshToken())) throw new Error('Your PlaceAI session has expired. Sign in as a student and try again.');
    const headers = new Headers(options.headers || {});
    headers.set('Authorization', `Bearer ${state.token}`);
    if (options.body && !headers.has('Content-Type')) headers.set('Content-Type','application/json');
    let response = await fetch(path, {...options, headers, credentials:'include'});
    if (response.status === 401 && await refreshToken()) {
      headers.set('Authorization', `Bearer ${state.token}`);
      response = await fetch(path, {...options, headers, credentials:'include'});
    }
    const contentType = response.headers.get('content-type') || '';
    const data = contentType.includes('application/json') ? await response.json().catch(()=>({})) : null;
    if (!response.ok) throw apiErrors.createError(data || {}, response.status);
    return data;
  }

  async function aiReady() {
    try {
      const response = await fetch('/ai/status', {credentials:'include', cache:'no-store'});
      if (!response.ok) return false;
      const data = await response.json();
      return Boolean(data.configured && data.sdk_available);
    } catch { return false; }
  }

  function setBusy(form, busy, label='Working…') {
    const button = form.querySelector('button[type="submit"]');
    if (!button) return;
    if (busy) { button.dataset.label = button.textContent; button.textContent = label; button.disabled = true; }
    else { button.textContent = button.dataset.label || button.textContent; button.disabled = false; }
  }

  async function loadJobs() {
    const jobs = await api('/mock-interview/jobs');
    state.jobs = jobs;
    const select = $('#job-select');
    select.innerHTML = `<option value="">Select an opportunity…</option>${jobs.map(j => `<option value="${esc(j.id)}">${esc(j.title)}${j.company_name ? ` · ${esc(j.company_name)}` : ''}</option>`).join('')}`;
    if (!jobs.length) select.innerHTML = '<option value="">No approved opportunities available</option>';
  }

  async function loadHistory() {
    try {
      const rows = await api('/mock-interview/history');
      const panel = $('#history-panel');
      panel.classList.remove('hidden');
      $('#history-list').innerHTML = rows.length ? rows.map(row => `<article class="history-item"><div><strong>${esc(row.job_title)}</strong><span>${esc(row.company_name || 'Company')} · ${row.created_at ? new Date(row.created_at).toLocaleString('en-IN') : 'Saved attempt'}</span></div><div class="history-score">${row.overall_score ?? '—'}</div></article>`).join('') : '<p class="disclaimer">No saved attempts yet. Your evaluated rounds will appear here.</p>';
    } catch (_) {}
  }

  function renderQuestions(data) {
    state.session = data;
    $('#interview-title').textContent = `${data.job_title} mock interview`;
    const avoided = Number(data.previous_questions_avoided || 0);
    const mode = data.generation_mode === 'ai'
      ? `Live AI${data.model ? ` · ${data.model}` : ''}`
      : data.generation_mode === 'ai_plus_fallback'
        ? 'Live AI + resilient grounding'
        : 'Resilient role-grounded practice';
    const latency = Number(data.generation_ms || 0);
    $('#interview-context').textContent = `${data.company_name || 'Opportunity'} · ${data.focus} · ${data.difficulty || 'mixed'} difficulty · ${data.questions.length} fresh questions · ${mode}${latency ? ` · ${(latency / 1000).toFixed(1)}s` : ''}${avoided ? ` · avoided ${avoided} prior questions` : ''}`;
    if (data.generation_mode === 'resilient_fallback') {
      toast('Live AI was temporarily unavailable. PlaceAI generated a role-grounded practice set so your session can continue.');
    } else if (data.generation_mode === 'ai_plus_fallback') {
      toast('PlaceAI completed the AI set with grounded fallback questions for reliability.');
    }
    $('#question-list').innerHTML = data.questions.map((q, index) => `<article class="question-card"><div class="question-meta"><span class="question-number">${index + 1}</span><span class="category">${esc(q.category || 'interview')}</span><span class="category">${esc(q.difficulty || 'medium')}</span></div><h3>${esc(q.question)}</h3><label>Your answer<textarea name="answer-${q.question_id}" data-question-id="${q.question_id}" required maxlength="8000" placeholder="Answer as you would in the interview. Use concrete examples and explain your reasoning."></textarea></label></article>`).join('');
    $('#setup-panel').classList.add('hidden');
    $('#result-panel').classList.add('hidden');
    $('#interview-panel').classList.remove('hidden');
    window.scrollTo({top:$('#interview-panel').offsetTop - 90,behavior:'smooth'});
  }

  const listHtml = (values, fallback) => (values || []).map(x => `<li>${esc(x)}</li>`).join('') || `<li>${esc(fallback)}</li>`;

  function renderResult(result) {
    if (result.evaluation_mode === 'resilient_baseline') {
      toast('Live AI analysis was unavailable. PlaceAI preserved the session with a clearly labelled completeness/relevance baseline.');
    }
    $('#overall-score').textContent = result.overall_score;
    $('#overall-feedback').textContent = result.overall_feedback || 'Evaluation complete.';
    $('#dimension-grid').innerHTML = Object.entries(result.dimensions || {}).map(([key, score]) => `<article class="dimension"><small>${esc(key.replaceAll('_',' '))}</small><strong>${score}</strong><div class="meter"><i style="width:${Math.max(0,Math.min(100,Number(score)||0))}%"></i></div></article>`).join('');
    $('#strength-list').innerHTML = listHtml(result.strengths, 'No specific strength returned.');
    $('#improvement-list').innerHTML = listHtml(result.improvements, 'No specific improvement returned.');
    $('#weak-topic-list').innerHTML = listHtml(result.weak_topics, 'No major weak topic detected in this round.');
    $('#practice-plan-list').innerHTML = listHtml(result.next_practice_plan, 'Run another role-specific round and improve the lowest-scoring dimension.');
    $('#answer-feedback').innerHTML = (result.evaluations || []).map((item, index) => {
      const missing = (item.missing_points || []).length ? `<div class="outline"><strong>Missing points</strong><ul>${item.missing_points.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>` : '';
      const keyPoints = (item.key_points || []).length ? `<div class="outline"><strong>Key points to cover</strong><ul>${item.key_points.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>` : '';
      const outline = item.better_answer_outline ? `<div class="outline"><strong>Better answer structure</strong><br>${esc(item.better_answer_outline)}</div>` : '';
      const ideal = item.ideal_answer ? `<div class="outline"><strong>Example strong answer / solution</strong><p>${esc(item.ideal_answer)}</p></div>` : '';
      return `<article class="answer-review"><header><strong>Q${index + 1}. ${esc(item.question || '')}</strong><b>${item.score}/100</b></header><p>${esc(item.feedback || '')}</p>${missing}${keyPoints}${outline}${ideal}</article>`;
    }).join('');
    $('#result-disclaimer').textContent = result.disclaimer || '';
    $('#interview-panel').classList.add('hidden');
    $('#result-panel').classList.remove('hidden');
    window.scrollTo({top:$('#result-panel').offsetTop - 90,behavior:'smooth'});
    loadHistory();
  }

  $('#setup-form').addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form).entries());
    data.question_count = Number(data.question_count);
    setBusy(form, true, 'Generating fresh questions…');
    try {
      const result = await api('/mock-interview/start',{method:'POST',body:JSON.stringify(data)});
      renderQuestions(result);
    } catch (error) {
      apiErrors.applyToForm(form, error);
      toast(error.message,'error');
    } finally { setBusy(form,false); }
  });

  $('#interview-form').addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    if (!state.session?.interview_id) return;
    const answers = [...form.querySelectorAll('textarea[data-question-id]')].map(node => ({
      question_id:Number(node.dataset.questionId), answer:node.value.trim()
    }));
    if (answers.some(item => !item.answer)) { toast('Answer every question before evaluation.','error'); return; }
    setBusy(form,true,'Analysing the full interview…');
    try {
      const result = await api('/mock-interview/evaluate',{method:'POST',body:JSON.stringify({interview_id:state.session.interview_id,answers})});
      renderResult(result);
    } catch (error) {
      apiErrors.applyToForm(form, error);
      toast(error.message,'error');
    } finally { setBusy(form,false); }
  });

  function restart() {
    state.session = null;
    $('#interview-panel').classList.add('hidden');
    $('#result-panel').classList.add('hidden');
    $('#setup-panel').classList.remove('hidden');
    window.scrollTo({top:$('#setup-panel').offsetTop - 90,behavior:'smooth'});
  }
  $('#restart-button').addEventListener('click', restart);
  $('#practice-again').addEventListener('click', restart);

  (async () => {
    const authState = $('#auth-state');
    try {
      if (!(await refreshToken())) {
        authState.innerHTML = 'No active student session. <a href="/?portal=student">Sign in to PlaceAI</a>, then return to the Mock Interview Coach.';
        return;
      }
      const me = await api('/auth/me');
      if (me.role !== 'student') {
        authState.textContent = 'Mock Interview Coach is available to student accounts only.';
        return;
      }
      const liveAIReady = await aiReady();
      if (liveAIReady) {
        authState.classList.add('hidden');
      } else {
        authState.textContent = "Live AI is temporarily degraded. The Mock Interview Coach remains available and will automatically use PlaceAI's role-grounded resilient practice mode if needed.";
      }
      $('#setup-panel').classList.remove('hidden');
      await Promise.all([loadJobs(), loadHistory()]);
    } catch (error) {
      authState.textContent = error.message;
      toast(error.message,'error');
    }
  })();
})();
