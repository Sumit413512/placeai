(() => {
  const nav = document.querySelector('#app-nav');
  const sections = document.querySelector('#feature-groups');
  if (!nav || !sections) return;
  let selection = '';
  let lastActive;
  let signature;
  function showGroup(group) {
    selection = group;
    for (const button of nav.querySelectorAll('button[data-view]')) {
      button.toggleAttribute('data-group-hidden', button.dataset.featureGroup !== group);
    }
    for (const button of sections.children) {
      button.setAttribute('aria-pressed', String(button.dataset.group === group));
    }
  }
  function sync() {
    let group = '';
    const groups = new Set();
    for (const child of nav.children) {
      if (child.classList.contains('nav-group-label')) group = child.textContent.trim();
      if (!child.matches('button[data-view]')) continue;
      child.dataset.featureGroup = group;
      groups.add(group);
    }
    const active = nav.querySelector('button.active[data-view]');
    const key = JSON.stringify([...groups]);
    if (key !== signature) {
      signature = key;
      sections.replaceChildren(...[...groups].map(name => {
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = name;
        button.dataset.group = name;
        button.onclick = () => {
          showGroup(name);
          const links = [...nav.querySelectorAll('button[data-view]')];
          const first = links.find(link => link.dataset.featureGroup === name);
          if (first && !links.some(link => link.dataset.featureGroup === name && link.classList.contains('active'))) {
            first.click();
          }
        };
        return button;
      }));
    }
    if (active && active !== lastActive) selection = active.dataset.featureGroup;
    lastActive = active;
    showGroup(groups.has(selection) ? selection : [...groups][0]);
  }
  new MutationObserver(sync).observe(nav, {childList:true, subtree:true, attributes:true, attributeFilter:['class']});
  sync();
})();
