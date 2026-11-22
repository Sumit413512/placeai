(() => {
  'use strict';
  const get = window.fetch.bind(window);
  const base = '/workspace-review';
  const fixture = get(base + '/sample-data.json').then(response => response.json());
  const key = 'placeai-design-review-role';
  const roles = {
    student: 'Student', recruiter: 'Recruiter',
    institution_admin: 'Institution admin', platform_admin: 'Platform admin',
  };
  const json = (value, status = 200) => new Response(JSON.stringify(value), {
    status, headers: {'Content-Type':'application/json'},
  });
  window.fetch = async (input, options) => {
    const url = new URL(input instanceof Request ? input.url : input, location.origin);
    const method = (options?.method || (input instanceof Request && input.method) || 'GET').toUpperCase();
    if (url.origin !== location.origin || url.pathname.startsWith(base + '/')) return get(input, options);
    const path = url.pathname;
    const data = await fixture;
    const role = sessionStorage.getItem(key);
    const sample = Object.hasOwn(roles, role) ? data[role] : undefined;
    if (path === '/auth/refresh') return sample ? json({access_token:'design-review'}) : json({}, 401);
    if (path === '/auth/me') return sample ? json(sample.profile) : json({}, 401);
    if (path === '/auth/logout') {
      sessionStorage.removeItem(key);
      return new Response(null, {status:204});
    }
    if (path === '/intelligence/institution/actions/sync' && sample) return json({});
    if (method === 'GET' && sample && Object.hasOwn(sample.responses,path)) return json(sample.responses[path]);
    return json({detail:'This action is unavailable in the design review.'}, 503);
  };
  document.addEventListener('DOMContentLoaded', () => {
    if (!location.pathname.endsWith(base) && !location.pathname.endsWith(base + '/')) return;
    const section = document.createElement('section');
    section.className = 'review-switcher';
    section.setAttribute('aria-label','Sample workspace selection');
    const text = document.createElement('p');
    text.textContent = 'Design review · Sample data';
    section.append(text);
    for (const [role,label] of Object.entries(roles)) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = label;
      button.addEventListener('click', () => {
        sessionStorage.setItem(key, role);
        location.href = base + '/';
      });
      section.append(button);
    }
    document.body.prepend(section);
  });
})();
