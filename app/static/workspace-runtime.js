(() => {
  'use strict';

  const originalFetch = window.fetch.bind(window);
  const inflight = new Map();
  const shortCache = new Map();
  const CACHE_MS = 1200;
  const CACHEABLE = new Set([
    '/auth/me',
    '/ai/status',
    '/students/profile',
    '/students/resume',
    '/enterprise/notifications',
    '/enterprise/student-campus-status'
  ]);
  let refreshPromise = null;
  let latestResume = null;

  function requestParts(input, init = {}) {
    const request = input instanceof Request ? input : null;
    const rawUrl = request ? request.url : String(input || '');
    const url = new URL(rawUrl, location.origin);
    const method = String(init.method || request?.method || 'GET').toUpperCase();
    const headers = new Headers(init.headers || request?.headers || {});
    const auth = headers.get('authorization') || '';
    return { url, method, auth };
  }

  function keyFor(parts) {
    return `${parts.method}:${parts.url.pathname}${parts.url.search}:${parts.auth}`;
  }

  function rememberResume(response, pathname) {
    if (pathname !== '/students/resume' || !response.ok) return;
    response.clone().json().then(data => {
      latestResume = data;
      enhanceResumeSkills();
    }).catch(() => {});
  }

  window.fetch = async function placeAIFetch(input, init = {}) {
    const parts = requestParts(input, init);
    const key = keyFor(parts);

    if (parts.url.pathname === '/auth/refresh') {
      if (refreshPromise) return (await refreshPromise).clone();
      refreshPromise = originalFetch(input, init)
        .then(response => response)
        .finally(() => { setTimeout(() => { refreshPromise = null; }, 0); });
      return (await refreshPromise).clone();
    }

    const cacheable = parts.method === 'GET' && CACHEABLE.has(parts.url.pathname);
    if (cacheable) {
      const cached = shortCache.get(key);
      if (cached && Date.now() - cached.at < CACHE_MS) return cached.response.clone();
      if (inflight.has(key)) return (await inflight.get(key)).clone();
      const promise = originalFetch(input, init).then(response => {
        if (response.ok) shortCache.set(key, { at: Date.now(), response: response.clone() });
        rememberResume(response, parts.url.pathname);
        return response;
      }).finally(() => inflight.delete(key));
      inflight.set(key, promise);
      return (await promise).clone();
    }

    const response = await originalFetch(input, init);
    rememberResume(response, parts.url.pathname);
    return response;
  };

  function enhanceResumeSkills() {
    const skills = latestResume?.ai_parsed_data?.skills;
    if (!Array.isArray(skills) || !skills.length) return;
    const boxes = [...document.querySelectorAll('.ai-box')];
    const parsedBox = boxes.find(box => {
      const header = box.querySelector('.ai-box-head span');
      return header && /PARSED R[ÉE]SUM[ÉE] DATA/i.test(header.textContent || '');
    });
    if (!parsedBox) return;
    const container = parsedBox.querySelector('.skill-tags');
    if (!container || container.dataset.allSkills === 'true') return;
    container.textContent = '';
    for (const skill of skills) {
      const value = String(skill || '').trim();
      if (!value) continue;
      const chip = document.createElement('span');
      chip.className = 'skill-tag';
      chip.textContent = value;
      container.appendChild(chip);
    }
    container.dataset.allSkills = 'true';
  }

  function loadHomepageEnhancements() {
    if (!document.querySelector('link[data-placeai-homepage-enhancements]')) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = '/static/homepage-enhancements.css';
      link.dataset.placeaiHomepageEnhancements = '';
      document.head.appendChild(link);
    }
    if (document.querySelector('script[data-placeai-homepage-enhancements]')) return;
    const script = document.createElement('script');
    script.src = '/static/homepage-enhancements.js';
    script.async = false;
    script.dataset.placeaiHomepageEnhancements = '';
    document.head.appendChild(script);
  }

  function loadInstitutionAccessWorkspace() {
    if (document.querySelector('script[data-placeai-institution-access]')) return;
    const script = document.createElement('script');
    script.src = '/static/institution-access.js';
    script.async = false;
    script.dataset.placeaiInstitutionAccess = '';
    document.head.appendChild(script);
  }

  const observer = new MutationObserver(() => enhanceResumeSkills());
  observer.observe(document.documentElement, { childList: true, subtree: true });
  document.addEventListener('DOMContentLoaded', enhanceResumeSkills, { once: true });
  loadHomepageEnhancements();
  loadInstitutionAccessWorkspace();
})();
