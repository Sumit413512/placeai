(() => {
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const header = document.querySelector('#marketing-site .site-header');
  const syncHeader = () => header?.classList.toggle('is-premium-scrolled', window.scrollY > 18);
  syncHeader();
  window.addEventListener('scroll', syncHeader, { passive: true });

  const selectors = [
    '#marketing-site .journey-card',
    '#marketing-site .bento-card',
    '#marketing-site .premium-insight-card',
    '#marketing-site .premium-feature-card',
    '#marketing-site .preparation-grid article',
    '#marketing-site .security-grid > div',
    '#marketing-site .premium-faq-list details',
    '#marketing-site .production-surface-card'
  ];
  const nodes = [...document.querySelectorAll(selectors.join(','))];
  nodes.forEach(node => node.classList.add('premium-reveal'));
  if (reduce || !('IntersectionObserver' in window)) {
    nodes.forEach(node => node.classList.add('premium-visible'));
    return;
  }
  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('premium-visible');
      observer.unobserve(entry.target);
    });
  }, { threshold: 0.12, rootMargin: '0px 0px -6% 0px' });
  nodes.forEach(node => observer.observe(node));
})();