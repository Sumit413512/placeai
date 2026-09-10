(() => {
  'use strict';

  const STORAGE_KEY = 'placeai.workspace.view.v1';
  const VIEW_PARAM = 'view';
  const SAFE_VIEW = /^[a-z0-9-]{1,48}$/;

  const safeSessionGet = key => {
    try { return sessionStorage.getItem(key); } catch { return null; }
  };
  const safeSessionSet = (key, value) => {
    try { sessionStorage.setItem(key, value); } catch {}
  };
  const safeSessionRemove = key => {
    try { sessionStorage.removeItem(key); } catch {}
  };

  const normalizeView = value => {
    const view = String(value || '').trim().toLowerCase();
    return SAFE_VIEW.test(view) ? view : '';
  };

  const viewFromUrl = () => {
    try { return normalizeView(new URL(location.href).searchParams.get(VIEW_PARAM)); }
    catch { return ''; }
  };

  const initialDesiredView = viewFromUrl() || normalizeView(safeSessionGet(STORAGE_KEY));
  let restoringInitialView = Boolean(initialDesiredView && initialDesiredView !== 'dashboard');
  let restoreTimer = null;

  function writeViewUrl(view) {
    try {
      const url = new URL(location.href);
      if (!view || view === 'dashboard') url.searchParams.delete(VIEW_PARAM);
      else url.searchParams.set(VIEW_PARAM, view);
      history.replaceState(
        {...(history.state || {}), placeaiView: view || 'dashboard'},
        '',
        `${url.pathname}${url.search}${url.hash}`
      );
    } catch {}
  }

  function rememberView(value) {
    const view = normalizeView(value);
    if (!view || view === 'mock-interview') return;
    safeSessionSet(STORAGE_KEY, view);
    writeViewUrl(view);
  }

  function clearView() {
    safeSessionRemove(STORAGE_KEY);
    writeViewUrl('');
  }

  function workspaceVisible() {
    const shell = document.querySelector('#app-shell');
    return Boolean(shell && !shell.classList.contains('hidden'));
  }

  function workspaceReady() {
    const content = document.querySelector('#app-content');
    return workspaceVisible() && Boolean(content) && !content.querySelector('.loading-state');
  }

  function findNavButton(view) {
    return [...document.querySelectorAll('#app-nav button[data-view]')]
      .find(item => item.dataset.view === view) || null;
  }

  function restoreInitialView() {
    if (!restoringInitialView || restoreTimer) return;
    const deadline = Date.now() + 30000;

    const attempt = () => {
      restoreTimer = null;
      if (!restoringInitialView) return;
      const button = findNavButton(initialDesiredView);

      if (workspaceReady() && button) {
        restoringInitialView = false;
        if (!button.classList.contains('active')) button.click();
        else rememberView(initialDesiredView);
        return;
      }

      if (Date.now() < deadline) {
        restoreTimer = setTimeout(attempt, 80);
      } else {
        restoringInitialView = false;
        clearView();
      }
    };

    restoreTimer = setTimeout(attempt, 0);
  }

  function rememberActiveWorkspaceView() {
    if (restoringInitialView || !workspaceReady()) return;
    const active = document.querySelector('#app-nav button.active[data-view]');
    if (active) rememberView(active.dataset.view);
  }

  document.addEventListener('click', event => {
    const logout = event.target.closest?.('[data-action="logout"]');
    if (logout) {
      clearView();
      return;
    }

    const viewButton = event.target.closest?.('[data-view]');
    if (viewButton?.dataset.view) rememberView(viewButton.dataset.view);

    if (event.target?.id === 'auth-overlay') {
      document.querySelector('#auth-overlay [data-action="close-auth"]')?.click();
    } else if (event.target?.id === 'generic-modal') {
      document.querySelector('#generic-modal [data-action="close-generic-modal"]')?.click();
    }
  }, true);

  function init() {
    const nav = document.querySelector('#app-nav');
    const shell = document.querySelector('#app-shell');
    const content = document.querySelector('#app-content');

    const observer = new MutationObserver(() => {
      if (restoringInitialView) restoreInitialView();
      else rememberActiveWorkspaceView();
    });

    if (nav) observer.observe(nav, {subtree: true, childList: true, attributes: true, attributeFilter: ['class']});
    if (shell) observer.observe(shell, {attributes: true, attributeFilter: ['class']});
    if (content) observer.observe(content, {subtree: true, childList: true});

    restoreInitialView();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, {once: true});
  } else {
    init();
  }
})();
