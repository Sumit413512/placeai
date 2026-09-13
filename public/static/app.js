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
    const script = document.createElement('script');
    script.src = scripts[index];
    script.async = false;
    script.onload = () => loadNext(index + 1);
    script.onerror = () => {
      console.error(`PlaceAI production asset failed to load: ${scripts[index]}`);
      loadNext(index + 1);
    };
    document.head.appendChild(script);
  };

  loadNext(0);
})();
