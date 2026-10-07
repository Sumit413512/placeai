(() => {
  'use strict';

  const POST_HR_VOICE_SECTIONS = new Set(['role', 'situational']);
  const START_PATH = '/mock-interview/start';

  function decorateAssessmentSession(payload) {
    if (!payload || payload.mode !== 'assessment' || !Array.isArray(payload.questions)) return payload;
    payload.questions = payload.questions.map(question => {
      if (!question || typeof question !== 'object') return question;
      const next = {...question};
      const section = String(next.section || '').trim().toLowerCase();
      const answerType = String(next.answer_type || 'text').trim().toLowerCase();
      // Keep Resume & Project Defence as text and preserve the current continuous
      // Behavioural/HR video experience. Only the two post-HR response sections
      // become private audio answers while the broad recording rollout is disabled.
      if (POST_HR_VOICE_SECTIONS.has(section) && answerType === 'text' && !next.response_mode) {
        next.response_mode = 'audio';
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

  function speakText(text, button) {
    if (!text || !('speechSynthesis' in window) || typeof window.SpeechSynthesisUtterance !== 'function') return;
    window.speechSynthesis.cancel();
    const chunks = text.match(/.{1,230}(?:\s|$)/g) || [text];
    let index = 0;
    button.disabled = true;
    button.textContent = 'Reading aloud…';

    const finish = () => {
      button.textContent = 'Read question aloud';
      syncReadButton(button);
    };
    const next = () => {
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
    const observer = new MutationObserver(() => syncReadButton(button));
    if (target) observer.observe(target, {childList: true, subtree: true, characterData: true});
    if (question) observer.observe(question, {childList: true, subtree: true, characterData: true});
  }

  installAssessmentResponseDecorator();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', installReadAloudControl, {once: true});
  } else {
    installReadAloudControl();
  }
})();
