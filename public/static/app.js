(() => {
  'use strict';
  if (window.__PLACEAI_PRODUCTION_BOOTSTRAP__) return;
  window.__PLACEAI_PRODUCTION_BOOTSTRAP__ = true;

  const styles = [
    '/static/api-errors.css',
    '/static/access-portal.css',
    '/static/ui-fixes.css',
    '/static/account-security.css'
  ];
  for (const href of styles) {
    if (document.querySelector(`link[href="${href}"]`)) continue;
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    document.head.appendChild(link);
  }

  const scripts = [
    '/static/workspace-runtime.js',
    '/static/api-errors.js',
    '/static/access-portal.js',
    '/static/ui-state-fixes.js',
    '/static/account-security.js',
    '/static/provisioning-password-fix.js',
    '/static/release-ux-fixes.js',
    '/static/integration-readiness.js',
    '/static/ai-readiness.js',
    '/static/legal-links.js',
    '/static/app-core.js'
  ];

  const loadNext = (index) => {
    if (index >= scripts.length) return;
    const candidateSrc = new URL(scripts[index], document.baseURI).href;
    const existing = [...document.scripts].find(script => script.src === candidateSrc);
    if (existing) {
      const state = existing.dataset.placeaiLoaderState;
      const parsedBeforeLoader = document.readyState !== 'loading' && !existing.async && existing !== document.currentScript;
      const alreadySettled = state === 'loaded' || state === 'error' || existing.readyState === 'complete' || (!state && (document.readyState === 'complete' || parsedBeforeLoader));
      if (alreadySettled) {
        loadNext(index + 1);
        return;
      }
      const settle = () => {
        existing.removeEventListener('load', settle);
        existing.removeEventListener('error', settle);
        loadNext(index + 1);
      };
      existing.addEventListener('load', settle, {once: true});
      existing.addEventListener('error', settle, {once: true});
      if (existing.readyState === 'complete') settle();
      return;
    }
    const script = document.createElement('script');
    script.src = scripts[index];
    script.async = false;
    script.dataset.placeaiLoaderState = 'loading';
    script.onload = () => {
      script.dataset.placeaiLoaderState = 'loaded';
      loadNext(index + 1);
    };
    script.onerror = () => {
      script.dataset.placeaiLoaderState = 'error';
      console.error(`PlaceAI production asset failed to load: ${scripts[index]}`);
      loadNext(index + 1);
    };
    document.head.appendChild(script);
  };

  loadNext(0);
})();
