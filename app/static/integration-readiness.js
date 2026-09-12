(() => {
  'use strict';

  let scheduled = false;
  let inFlight = false;

  const text = node => String(node?.textContent || '').trim();
  const byLabel = (root, selector, label) => [...root.querySelectorAll(selector)]
    .find(node => text(node).toLowerCase() === label.toLowerCase()) || null;

  function setStatus(cell, ok, label) {
    if (!cell) return;
    cell.textContent = '';
    const badge = document.createElement('span');
    badge.className = `status-badge status-${ok ? 'approved' : 'pending'}`;
    badge.textContent = label;
    cell.appendChild(badge);
  }

  function setRow(root, oldLabel, newLabel, ok, value) {
    const labelCell = byLabel(root, 'th', oldLabel);
    if (!labelCell) return;
    labelCell.textContent = newLabel;
    setStatus(labelCell.nextElementSibling, ok, value);
  }

  function activeTransport(summary, reset) {
    const smtp = Boolean(summary?.brevo_smtp || reset?.smtp_transport_configured);
    const api = Boolean(summary?.brevo_api || reset?.brevo_api_configured);
    if (smtp && api) return {smtp, api, label: 'SMTP + Brevo HTTPS API fallback'};
    if (api) return {smtp, api, label: 'Brevo HTTPS API'};
    if (smtp) return {smtp, api, label: 'SMTP'};
    return {smtp, api, label: 'No transport configured'};
  }

  async function reconcile() {
    scheduled = false;
    if (inFlight) return;
    const title = text(document.querySelector('#page-title'));
    const root = document.querySelector('#app-content');
    if (title !== 'Integrations' || !root || root.dataset.placeaiIntegrationReconciled === '1') return;

    const emailCard = [...root.querySelectorAll('.metric-card')]
      .find(card => ['Brevo SMTP', 'Transactional email'].includes(text(card.querySelector('small'))));
    if (!emailCard) return;

    inFlight = true;
    try {
      const [summaryResponse, resetResponse] = await Promise.all([
        fetch('/platform/integrations/status', {credentials: 'include'}),
        fetch('/platform/integrations/password-reset-email', {credentials: 'include'})
      ]);
      if (!summaryResponse.ok || !resetResponse.ok) return;

      const [summary, reset] = await Promise.all([summaryResponse.json(), resetResponse.json()]);
      const transport = activeTransport(summary, reset);
      const ready = Boolean(summary.transactional_email || reset.transactional_email_configured);

      const cardTitle = emailCard.querySelector('small');
      const cardValue = emailCard.querySelector('strong');
      const cardCopy = emailCard.querySelector('span');
      if (cardTitle) cardTitle.textContent = 'Transactional email';
      if (cardValue) cardValue.textContent = ready ? 'Ready' : 'Not ready';
      if (cardCopy) cardCopy.textContent = ready ? transport.label : 'No configured delivery transport';

      setRow(root, 'SMTP transport', 'Delivery transport', ready, transport.label);

      const securityReady = transport.api || (transport.smtp && Boolean(reset.tls_enabled));
      setRow(
        root,
        'TLS',
        'Transport security',
        securityReady,
        transport.api ? 'HTTPS / TLS' : (reset.tls_enabled ? 'TLS enabled' : 'TLS not enabled')
      );

      const authLabel = byLabel(root, 'th', 'SMTP authentication');
      if (authLabel) {
        authLabel.textContent = 'Provider authentication';
        const authCell = authLabel.nextElementSibling;
        if (transport.api && transport.smtp) {
          setStatus(authCell, true, 'SMTP credentials + Brevo API key');
        } else if (transport.api) {
          setStatus(authCell, true, 'Brevo API key configured');
        } else if (transport.smtp && reset.smtp_authentication_enabled) {
          setStatus(authCell, Boolean(reset.smtp_authentication_configured), reset.smtp_authentication_configured ? 'SMTP credentials configured' : 'SMTP credentials incomplete');
        } else if (transport.smtp) {
          setStatus(authCell, true, 'SMTP login not required');
        } else {
          setStatus(authCell, false, 'Not configured');
        }
      }

      const notConfigured = byLabel(root, 'th', 'Not configured (24h)');
      if (notConfigured) notConfigured.textContent = 'Historical not configured (24h)';

      const secondary = root.querySelector('.table-secondary');
      if (secondary && !secondary.textContent.includes('Historical failures')) {
        secondary.textContent += ' Historical failures are retained for audit and do not override a healthy latest delivery.';
      }

      root.dataset.placeaiIntegrationReconciled = '1';
    } catch {
      // The existing screen remains available if the supplemental readiness check fails.
    } finally {
      inFlight = false;
    }
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    setTimeout(reconcile, 0);
  }

  const start = () => {
    const content = document.querySelector('#app-content');
    const title = document.querySelector('#page-title');
    if (!content) return;
    const observer = new MutationObserver(schedule);
    observer.observe(content, {subtree: true, childList: true});
    if (title) observer.observe(title, {subtree: true, childList: true, characterData: true});
    schedule();
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once: true});
  else start();
})();
