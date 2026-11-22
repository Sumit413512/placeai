(() => {
  'use strict';

  const endpoint = '/array-readiness';
  const stepLabels = {diagnostic:'1. Diagnostic', practice:'2. Guided practice', followup:'3. Independent follow-up'};

  function setup(host, onLoad) {
    if (!host) return;
    const content = host.querySelector('[data-array-content]');
    const status = host.querySelector('[data-array-status]');
    const showError = error => { status.textContent = error.message || 'Please try again.'; };
    const run = async (button, work) => {
      button.disabled = true;
      status.textContent = '';
      try { await work(); }
      catch (error) { showError(error); }
      finally { button.disabled = false; }
    };
    host.querySelector('[data-array-load]').addEventListener('click', event => {
      run(event.currentTarget, onLoad);
    });
    return {content, run};
  }

  function mountStudent(host, api, esc) {
    let track = '';
    const ui = setup(host, load);
    if (!ui) return;

    async function load() { render(await api(endpoint + '/me')); }

    function render(data) {
      track = data.track;
      const results = Object.entries(data.results).map(([step,result]) =>
        `<li><strong>${stepLabels[step]} · ${result.correct ? 'Correct' : 'Needs practice'}</strong><br>${esc(result.feedback)}</li>`).join('');
      const guidance = data.step === 'practice'
        ? `<p>Review <a href="${esc(data.lesson_url)}" target="_blank" rel="noopener">Indexed Access &amp; Safety (opens in a new tab)</a>, then try the guided question.</p>`
        : data.step === 'followup'
          ? '<p>Try this fresh question independently. Your first answer is saved for comparison.</p>' : '';
      const question = data.question;
      ui.content.innerHTML =
        `<p>${data.institution ? `This assignment shares completion and correctness with ${esc(data.institution)}.` : 'Your personal practice is visible only in your student workspace.'}</p>
        ${results ? `<ol class="array-results" aria-label="Saved answers">${results}</ol>` : ''}
        ${guidance}
        ${question ? `<form class="form-stack" data-array-answer data-step="${data.step}"><fieldset>
          <legend>${stepLabels[data.step]}</legend><p>${esc(question.prompt)}</p>
          <pre><code>${esc(question.code)}</code></pre>
          ${question.options.map((option,index) => `<label class="array-option"><input type="radio" name="choice" value="${index}" required> ${esc(option)}</label>`).join('')}
          </fieldset><button class="button button-primary" type="submit">Save answer</button></form>`
          : `<p><strong>Follow-up complete.</strong> ${data.results.followup.correct ? 'You answered the follow-up correctly.' : 'This skill would benefit from more practice.'}</p>
             <p><a href="${esc(data.lesson_url)}" target="_blank" rel="noopener">Revisit the lesson (opens in a new tab)</a></p>`}`;
      const heading = ui.content.querySelector('legend, strong');
      if (heading) {
        heading.tabIndex = -1;
        heading.focus({preventScroll:true});
      }
    }

    ui.content.addEventListener('submit', event => {
      const form = event.target.closest('[data-array-answer]');
      if (!form) return;
      event.preventDefault();
      event.stopPropagation();
      const choice = new FormData(form).get('choice');
      if (choice === null) return;
      ui.run(form.querySelector('button'), async () => {
        render(await api(endpoint + '/me/answers', {
          method:'POST', body:JSON.stringify({track, step:form.dataset.step, choice:Number(choice)}),
        }));
      });
    });
  }

  function mountInstitution(host, api, esc) {
    let offset = 0, search = '';
    const ui = setup(host, async () => display(0, ''));
    if (!ui) return;

    async function display(nextOffset, nextSearch) {
      const query = new URLSearchParams({offset:nextOffset, search:nextSearch});
      const data = await api(`${endpoint}/institution?${query}`);
      offset = nextOffset;
      search = nextSearch;
      const statusLabel = student => {
        if (!student.assigned) return 'Unassigned';
        if (student.diagnostic_correct === null) return 'Assigned · awaiting diagnostic';
        if (student.followup_correct === null) return 'Started · awaiting follow-up';
        if (!student.followup_correct) return 'Needs more help';
        return student.diagnostic_correct ? 'Correct on both tasks' : 'Improved on follow-up';
      };
      ui.content.innerHTML = `
        <dl class="array-metrics">
          ${[['Assigned',data.assigned],['Started',data.started],['Reassessed',data.reassessed],['Improved',data.improved],['Need help',data.needs_help]]
            .map(([label,value]) => `<div><dt>${label}</dt><dd>${value}</dd></div>`).join('')}
        </dl>
        <p class="learning-meta">Improved counts students who answered the initial question incorrectly and the independent follow-up correctly.</p>
        <form class="array-controls" data-array-search><label>Find a student <input name="search" value="${esc(search)}" maxlength="80"></label>
          <button class="button button-secondary" type="submit">Search</button></form>
        ${data.students.length ? `<div class="table-wrap"><table class="data-table"><caption>Arrays assignments</caption>
          <thead><tr><th scope="col">Student</th><th scope="col">Status</th><th scope="col">Next action</th></tr></thead>
          <tbody>${data.students.map(student => `<tr><td>${esc(student.name)}</td><td>${statusLabel(student)}</td><td>${
            student.assigned
              ? (student.followup_correct === false ? 'Review indexing with the student' : '—')
              : `<button class="button button-secondary" type="button" data-array-assign="${esc(student.id)}" aria-label="Assign Arrays practice to ${esc(student.name)}">Assign practice</button>`
          }</td></tr>`).join('')}</tbody></table></div>` : '<p>No matching students.</p>'}
        <div class="array-controls">
          ${offset > 0 ? '<button class="button button-secondary" type="button" data-array-page="-50">Previous</button>' : ''}
          ${data.has_more ? '<button class="button button-secondary" type="button" data-array-page="50">Next</button>' : ''}
        </div>`;
    }

    ui.content.addEventListener('submit', event => {
      if (!event.target.matches('[data-array-search]')) return;
      event.preventDefault();
      event.stopPropagation();
      const form = event.target;
      ui.run(form.querySelector('button'), () => display(0, new FormData(form).get('search')));
    });
    ui.content.addEventListener('click', event => {
      const button = event.target.closest('[data-array-assign], [data-array-page]');
      if (!button) return;
      ui.run(button, async () => {
        if (button.dataset.arrayAssign) {
          await api(endpoint + '/institution/assignments/' + encodeURIComponent(button.dataset.arrayAssign), {method:'PUT'});
          await display(offset, search);
          host.querySelector('[data-array-status]').textContent = 'Arrays practice assigned.';
        } else {
          await display(offset + Number(button.dataset.arrayPage), search);
        }
      });
    });
  }

  function panel(admin = false) {
    return `<section class="panel array-readiness" data-array-panel>
      <h2>Arrays readiness</h2>
      <p>${admin ? 'Assign Arrays practice to your students, then review who improved and who needs help.'
        : 'Find a gap in your array indexing skills, practise it, and try a fresh problem.'}</p>
      <button class="button button-secondary" type="button" data-array-load>${admin ? 'View assignments' : 'Open Arrays practice'}</button>
      <p role="status" data-array-status></p><div data-array-content></div>
    </section>`;
  }

  window.PlaceAIArrayReadiness = {panel, mountStudent, mountInstitution};
})();
