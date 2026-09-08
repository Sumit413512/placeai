(() => {
  'use strict';
  const $ = (s, root = document) => root.querySelector(s);
  const esc = (value = '') => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const state = { token:'', jobs:[], session:null };

  function toast(message, type='') {
    const node = $('#toast');
    node.textContent = message;
    node.className = `toast ${type}`.trim();
    setTimeout(() => node.classList.add('hidden'), 3600);
  }

  async function refreshToken() {
    const response = await fetch('/auth/refresh', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      credentials:'include',
      body:'{}'
    });
    if (!response.ok) return false;
    const data = await response.json();
    state.token = data.access_token || '';
    return Boolean(state.token);
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
    if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : `Request failed (${response.status})`);
    return data;
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
    $('#interview-context').textContent = `${data.company_name || 'Opportunity'} · ${data.focus} focus · ${data.questions.length} questions`;
    $('#question-list').innerHTML = data.questions.map((q, index) => `<article class="question-card"><div class="question-meta"><span class="question-number">${index + 1}</span><span class="category">${esc(q.category || 'interview')}</span></div><h3>${esc(q.question)}</h3><label>Your answer<textarea name="answer-${q.question_id}" data-question-id="${q.question_id}" required maxlength="8000" placeholder="Answer as you would in the interview. Use concrete examples and explain your reasoning."></textarea></label></article>`).join('');
    $('#setup-panel').classList.add('hidden');
    $('#result-panel').classList.add('hidden');
    $('#interview-panel').classList.remove('hidden');
    window.scrollTo({top:$('#interview-panel').offsetTop - 90,behavior:'smooth'});
  }

  function renderResult(result) {
    $('#overall-score').textContent = result.overall_score;
    $('#overall-feedback').textContent = result.overall_feedback || 'Evaluation complete.';
    $('#dimension-grid').innerHTML = Object.entries(result.dimensions || {}).map(([key, score]) => `<article class="dimension"><small>${esc(key.replaceAll('_',' '))}</small><strong>${score}</strong><div class="meter"><i style="width:${Math.max(0,Math.min(100,Number(score)||0))}%"></i></div></article>`).join('');
    $('#strength-list').innerHTML = (result.strengths || []).map(x => `<li>${esc(x)}</li>`).join('') || '<li>No specific strength returned.</li>';
    $('#improvement-list').innerHTML = (result.improvements || []).map(x => `<li>${esc(x)}</li>`).join('') || '<li>No specific improvement returned.</li>';
    $('#answer-feedback').innerHTML = (result.evaluations || []).map((item, index) => `<article class="answer-review"><header><strong>Q${index + 1}. ${esc(item.question || '')}</strong><b>${item.score}/100</b></header><p>${esc(item.feedback || '')}</p>${item.better_answer_outline ? `<div class="outline"><strong>Better answer outline</strong><br>${esc(item.better_answer_outline)}</div>` : ''}</article>`).join('');
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
    setBusy(form, true, 'Generating…');
    try {
      const result = await api('/mock-interview/start',{method:'POST',body:JSON.stringify(data)});
      renderQuestions(result);
    } catch (error) {
      toast(error.message,'error');
    } finally {
      setBusy(form,false);
    }
  });

  $('#interview-form').addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    if (!state.session?.interview_id) return;
    const answers = [...form.querySelectorAll('textarea[data-question-id]')].map(node => ({
      question_id:Number(node.dataset.questionId),
      answer:node.value.trim()
    }));
    if (answers.some(item => !item.answer)) { toast('Answer every question before evaluation.','error'); return; }
    setBusy(form,true,'Evaluating…');
    try {
      const result = await api('/mock-interview/evaluate',{method:'POST',body:JSON.stringify({interview_id:state.session.interview_id,answers})});
      renderResult(result);
    } catch (error) {
      toast(error.message,'error');
    } finally {
      setBusy(form,false);
    }
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
      authState.classList.add('hidden');
      $('#setup-panel').classList.remove('hidden');
      await Promise.all([loadJobs(), loadHistory()]);
    } catch (error) {
      authState.textContent = error.message;
      toast(error.message,'error');
    }
  })();
})();