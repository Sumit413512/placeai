(() => {
  'use strict';

  function loadScriptOnce(src, dataAttribute, loadedFlag) {
    if (window[loadedFlag] || document.querySelector(`script[${dataAttribute}]`)) return;
    const script = document.createElement('script');
    script.src = src;
    script.defer = true;
    script.setAttribute(dataAttribute, '');
    document.head.appendChild(script);
  }

  loadScriptOnce('/static/production-polish.js', 'data-placeai-production-polish', '__PLACEAI_PRODUCTION_POLISH_LOADED__');
  loadScriptOnce('/static/payment-checkout.js', 'data-placeai-payment-checkout', '__PLACEAI_PAYMENT_CHECKOUT_LOADED__');

  const footer = document.querySelector('.site-footer');
  if (!footer || footer.querySelector('[data-placeai-legal-links]')) return;
  const nav = document.createElement('nav');
  nav.setAttribute('data-placeai-legal-links', '');
  nav.setAttribute('aria-label', 'Company and legal');
  nav.style.display = 'flex';
  nav.style.gap = '12px';
  nav.style.flexWrap = 'wrap';
  nav.style.fontSize = '13px';
  nav.innerHTML = '<a href="/static/pricing.html">Pricing</a><a href="/static/about.html">About</a><a href="/static/contact.html">Contact</a><a href="/static/service-delivery.html">Service delivery</a><a href="/static/refund-cancellation.html">Refunds & cancellation</a><a href="/privacy">Privacy</a><a href="/terms">Terms</a><a href="/acceptable-use">Acceptable Use</a>';
  footer.appendChild(nav);
})();
