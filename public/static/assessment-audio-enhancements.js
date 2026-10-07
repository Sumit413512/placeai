(() => {
  'use strict';

  const ASSESSMENT_AUDIO_SECTIONS = new Set(['resume', 'role', 'situational']);
  const START_PATH = '/mock-interview/start';
  const SPOKEN_BLUEPRINT_LABELS = new Set(['Resume & Project Defence', 'Role / JD / Company', 'Situational & Decision']);
  const LEGACY_GRADING_METHOD_LABEL = 'Answer key + sandbox execution + answer and HR video analysis';
  const COMPLETE_GRADING_METHOD_LABEL = 'Answer key + sandbox execution + spoken and HR video analysis';

  function decorateAssessmentSession(payload) {
    if (!payload || payload.mode !== 'assessment' || !Array.isArray(payload.questions)) return payload;
    payload.questions = payload.questions.map(question => {
      if (!question || typeof question !== 'object') return question;
      const next = {...question};
      const section = String(next.section || '').trim().toLowerCase();
      const answerType = String(next.answer_type || 'text').trim().toLowerCase();
      // Standardized open-ended non-HR sections are private audio answers.
      // Behavioural/HR keeps its existing continuous video experience.
      if (ASSESSMENT_AUDIO_SECTIONS.has(section)) {
        next.answer_type = 'audio';
        next.response_mode = 'audio';
        next.narration_enabled = true;
        if (!next.answer_time_seconds) next.answer_time_seconds = section === 'resume' ? 120 : section === 'role' ? 90 : 120;
        next.options = [];
      }
      return next;
    });
    return payload;
  }

  function requestPath(input) {
    try {
      if (input instanceof Request) return new URL(input.url, window.location.origin).pathname;
      return new URL(String(input), window.location.origin).pathname;
    } catch {
      return '';
    }
  }

  function requestMethod(input, init) {
    return String(init?.method || (input instanceof Request ? input.method : 'GET')).toUpperCase();
  }

  function installAssessmentResponseDecorator() {
    if (window.__placeAIAssessmentAudioFetchInstalled) return;
    window.__placeAIAssessmentAudioFetchInstalled = true;
    const nativeFetch = window.fetch.bind(window);
    window.fetch = async function placeAIAssessmentFetch(input, init) {
      const response = await nativeFetch(input, init);
      if (!response.ok || requestMethod(input, init) !== 'POST' || requestPath(input) !== START_PATH) {
        return response;
      }
      const contentType = response.headers.get('content-type') || '';
      if (!contentType.includes('application/json')) return response;
      try {
        const payload = decorateAssessmentSession(await response.clone().json());
        const headers = new Headers(response.headers);
        headers.delete('content-length');
        headers.delete('content-encoding');
        headers.set('content-type', 'application/json');
        return new Response(JSON.stringify(payload), {
          status: response.status,
          statusText: response.statusText,
          headers,
        });
      } catch {
        return response;
      }
    };
  }

  function visibleQuestionText() {
    const question = document.querySelector('#question-text')?.textContent?.trim() || '';
    if (!question) return '';
    const optionText = [...document.querySelectorAll('#answer-area .option-button')]
      .map((node, index) => `Option ${String.fromCharCode(65 + index)}. ${node.querySelector('.option-text')?.textContent?.trim() || ''}`)
      .filter(Boolean);
    const codingMeta = document.querySelector('#answer-area .code-problem-meta')?.textContent?.replace(/\s+/g, ' ')?.trim() || '';
    return [question, ...optionText, codingMeta].filter(Boolean).join('. ');
  }

  function spokenRecorderBusy() {
    const status = document.querySelector('#spoken-answer-status');
    if (!status) return false;
    const text = (status.textContent || '').toLowerCase();
    return text.includes('reading') || text.includes('recording') || text.includes('upload') || text.includes('saving');
  }

  function legacyHrReaderPresent() {
    return Boolean(document.querySelector('#repeat-hr-question'));
  }

  function syncBlueprintVoiceLabels(root = document) {
    root.querySelectorAll?.('.blueprint-row')?.forEach(row => {
      const label = row.querySelector('strong')?.textContent?.trim() || '';
      if (!SPOKEN_BLUEPRINT_LABELS.has(label)) return;
      const meta = row.querySelector('small');
      if (!meta) return;
      const minutes = (meta.textContent || '').split('·')[0].trim();
      const desired = `${minutes} · Private spoken answer`;
      if (meta.textContent?.trim() !== desired) meta.textContent = desired;
    });
  }

  function syncReadButton(button = document.querySelector('#read-question-aloud')) {
    if (!button) return;
    const supported = 'speechSynthesis' in window && typeof window.SpeechSynthesisUtterance === 'function';
    const hasQuestion = Boolean(document.querySelector('#question-text')?.textContent?.trim());
    const automaticSpokenQuestion = Boolean(document.querySelector('#spoken-answer-status'));
    const legacyReader = legacyHrReaderPresent();
    button.hidden = legacyReader || automaticSpokenQuestion;
    button.disabled = !supported || !hasQuestion || spokenRecorderBusy();
    if (!supported) {
      button.title = 'Read aloud is not supported by this browser.';
    } else {
      button.title = 'Read the current question aloud.';
    }
  }

  let manualReadGeneration = 0;

  function cancelManualReading(button) {
    manualReadGeneration += 1;
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    if (button) {
      button.textContent = 'Read question aloud';
      syncReadButton(button);
    }
  }

  function speakText(text, button) {
    if (!text || !('speechSynthesis' in window) || typeof window.SpeechSynthesisUtterance !== 'function') return;
    cancelManualReading(button);
    const generation = ++manualReadGeneration;
    const chunks = text.match(/.{1,230}(?:\s|$)/g) || [text];
    let index = 0;
    button.disabled = true;
    button.textContent = 'Reading aloud…';

    const finish = () => {
      if (generation !== manualReadGeneration) return;
      button.textContent = 'Read question aloud';
      syncReadButton(button);
    };
    const next = () => {
      if (generation !== manualReadGeneration) return;
      if (index >= chunks.length) {
        finish();
        return;
      }
      const utterance = new SpeechSynthesisUtterance(chunks[index++].trim());
      utterance.lang = 'en-IN';
      utterance.rate = 0.95;
      utterance.onend = next;
      utterance.onerror = finish;
      window.speechSynthesis.speak(utterance);
    };
    next();
  }

  function installBlueprintVoiceLabels() {
    const list = document.querySelector('#blueprint-list');
    if (!list) return;
    syncBlueprintVoiceLabels(list);
    const observer = new MutationObserver(() => syncBlueprintVoiceLabels(list));
    observer.observe(list, {childList: true, subtree: true});
  }

  function installGradingMethodLabel() {
    const label = document.querySelector('#grading-method-label');
    if (!label) return;
    const sync = () => {
      if (label.textContent?.trim() === LEGACY_GRADING_METHOD_LABEL) {
        label.textContent = COMPLETE_GRADING_METHOD_LABEL;
      }
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(label, {childList: true, subtree: true, characterData: true});
  }

  function installReadAloudControl() {
    const questionWrap = document.querySelector('#question-canvas-wrap');
    if (!questionWrap || document.querySelector('#read-question-aloud')) return;
    const button = document.createElement('button');
    button.id = 'read-question-aloud';
    button.type = 'button';
    button.className = 'button secondary';
    button.textContent = 'Read question aloud';
    button.setAttribute('aria-label', 'Read current assessment question aloud');
    button.style.marginTop = '0.75rem';
    button.addEventListener('click', () => {
      if (button.disabled || spokenRecorderBusy()) return;
      speakText(visibleQuestionText(), button);
    });
    questionWrap.insertAdjacentElement('afterend', button);
    syncReadButton(button);

    const target = document.querySelector('#answer-area');
    const question = document.querySelector('#question-text');
    let lastQuestion = question?.textContent?.trim() || '';
    const syncForMutation = () => {
      const currentQuestion = question?.textContent?.trim() || '';
      // Never let manual narration from the previous MCQ/coding/text question
      // continue after navigation. Spoken-answer sections own their automatic
      // narration lifecycle in mock-interview.js and are deliberately left alone.
      if (currentQuestion !== lastQuestion) {
        lastQuestion = currentQuestion;
        if (!document.querySelector('#spoken-answer-status') && button.textContent === 'Reading aloud…') {
          cancelManualReading(button);
        }
      }
      syncReadButton(button);
    };
    const observer = new MutationObserver(syncForMutation);
    if (target) observer.observe(target, {childList: true, subtree: true, characterData: true});
    if (question) observer.observe(question, {childList: true, subtree: true, characterData: true});
    document.addEventListener('visibilitychange', () => {
      if (document.hidden && button.textContent === 'Reading aloud…') cancelManualReading(button);
    });
  }

  function installAssessmentAudioEnhancements() {
    installBlueprintVoiceLabels();
    installGradingMethodLabel();
    installReadAloudControl();
  }

  installAssessmentResponseDecorator();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', installAssessmentAudioEnhancements, {once: true});
  } else {
    installAssessmentAudioEnhancements();
  }
})();
