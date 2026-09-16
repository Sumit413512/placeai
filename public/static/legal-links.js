(() => {
  'use strict';

  function loadProductionPolish() {
    if (window.__PLACEAI_PRODUCTION_POLISH_LOADED__ || document.querySelector('script[data-placeai-production-polish]')) return;
    const script = document.createElement('script');
    script.src = '/static/production-polish.js';
    script.defer = true;
    script.dataset.placeaiProductionPolish = '';
    document.head.appendChild(script);
  }

  loadProductionPolish();

  const footer = document.querySelector('.site-footer');
  if (!footer || footer.querySelector('[data-placeai-legal-links]')) return;
  const nav = document.createElement('nav');
  nav.setAttribute('data-placeai-legal-links', '');
  nav.setAttribute('aria-label', 'Legal');
  nav.style.display = 'flex';
  nav.style.gap = '12px';
  nav.style.flexWrap = 'wrap';
  nav.style.fontSize = '13px';
  nav.innerHTML = '<a href="/privacy">Privacy</a><a href="/terms">Terms</a><a href="/acceptable-use">Acceptable Use</a>';
  footer.appendChild(nav);
})();
