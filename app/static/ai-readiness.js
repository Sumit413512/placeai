(() => {
  'use strict';

  const AI_ACTIONS = new Set(['parse-resume', 'generate-summary', 'rank-candidates']);
  const AI_FORM_IDS = new Set(['assistant-form']);
  const UNAVAILABLE = 'AI features are temporarily unavailable until an AI provider is configured.';
  const state = { checked: false, ready: false, configured: false, sdkAvailable: false, model: '' };
  let checkPromise = null;

  function setControlAvailability(control, ready) {
    if (!(control instanceof HTMLElement)) return;
    if (ready) {
      if (control.dataset.placeaiAiDisabled === '1') {
        control.removeAttribute('aria-disabled');
        control.removeAttribute('title');
        if ('disabled' in control) control.disabled = false;
        delete control.dataset.placeaiAiDisabled;
      }
      return;
    }
    control.dataset.placeaiAiDisabled = '1';
    control.setAttribute('aria-disabled', 'true');
    control.setAttribute('title', UNAVAILABLE);
    if ('disabled' in control) control.disabled = true;
  }

  function ensureUnavailableNote(form) {
    if (!(form instanceof HTMLFormElement) || form.querySelector('.placeai-ai-unavailable-note')) return;
    const note = document.createElement('div');
    note.className = 'note-box placeai-ai-unavailable-note';
    note.setAttribute('role', 'status');
    note.innerHTML = '<strong>AI temporarily unavailable</strong><p>Core placement workflows remain available. An administrator must configure OpenAI or the Gemini fallback before this AI feature can run.</p>';
    form.prepend(note);
  }

  function removeUnavailableNote(form) {
    form?.querySelector?.('.placeai-ai-unavailable-note')?.remove();
  }

  function apply(root = document) {
    const actionNodes = [];
    if (root instanceof HTMLElement && root.dataset?.action && AI_ACTIONS.has(root.dataset.action)) actionNodes.push(root);
    root.querySelectorAll?.('[data-action]')?.forEach(node => {
      if (AI_ACTIONS.has(node.dataset.action)) actionNodes.push(node);
    });
    actionNodes.forEach(node => setControlAvailability(node, state.ready));

    const forms = [];
    if (root instanceof HTMLFormElement && AI_FORM_IDS.has(root.id)) forms.push(root);
    root.querySelectorAll?.('form[id]')?.forEach(form => {
      if (AI_FORM_IDS.has(form.id)) forms.push(form);
    });
    for (const form of forms) {
      form.querySelectorAll('input, textarea, select, button').forEach(control => setControlAvailability(control, state.ready));
      if (state.ready) removeUnavailableNote(form);
      else ensureUnavailableNote(form);
    }
  }

  async function check() {
    if (checkPromise) return checkPromise;
    checkPromise = (async () => {
      try {
        const response = await fetch('/ai/status', { credentials: 'include', cache: 'no-store' });
        const payload = response.ok ? await response.json() : {};
        state.configured = Boolean(payload.configured);
        state.sdkAvailable = Boolean(payload.sdk_available);
        state.model = String(payload.model || '');
        state.ready = response.ok && state.configured && state.sdkAvailable;
      } catch {
        state.ready = false;
        state.configured = false;
        state.sdkAvailable = false;
      } finally {
        state.checked = true;
        apply(document);
        checkPromise = null;
      }
      return {...state};
    })();
    return checkPromise;
  }

  function install() {
    apply(document);
    check();
    const observer = new MutationObserver(records => {
      for (const record of records) {
        record.addedNodes.forEach(node => {
          if (node instanceof Element) apply(node);
        });
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });

    document.addEventListener('click', event => {
      const action = event.target.closest?.('[data-action]');
      if (!action || !AI_ACTIONS.has(action.dataset.action) || state.ready) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      setControlAvailability(action, false);
    }, true);

    document.addEventListener('submit', event => {
      const form = event.target instanceof HTMLFormElement ? event.target : null;
      if (!form || !AI_FORM_IDS.has(form.id) || state.ready) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      ensureUnavailableNote(form);
    }, true);
  }

  window.PlaceAIAIReadiness = Object.freeze({
    refresh: check,
    snapshot: () => ({...state}),
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, {once: true});
  else install();
})();
