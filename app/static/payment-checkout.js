(() => {
  'use strict';
  if (window.__PLACEAI_PAYMENT_CHECKOUT_LOADED__) return;
  window.__PLACEAI_PAYMENT_CHECKOUT_LOADED__ = true;

  let accessToken = '';
  let sdkPromise = null;
  let decorateTimer = null;
  let returnHandled = false;

  const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

  function paymentToast(title, message = '', type = 'success') {
    const region = document.querySelector('#toast-region');
    if (!region) return;
    const node = document.createElement('div');
    node.className = `toast ${type}`;
    const strong = document.createElement('strong');
    strong.textContent = title;
    const wrapper = document.createElement('div');
    wrapper.appendChild(strong);
    if (message) {
      const span = document.createElement('span');
      span.textContent = message;
      wrapper.appendChild(span);
    }
    node.appendChild(wrapper);
    region.appendChild(node);
    setTimeout(() => node.remove(), 5000);
  }

  async function refreshAccessToken() {
    const response = await fetch('/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
      credentials: 'include'
    });
    if (!response.ok) throw new Error('Sign in again before opening secure checkout.');
    const data = await response.json();
    accessToken = String(data.access_token || '');
    if (!accessToken) throw new Error('Secure session refresh did not return an access token.');
    return accessToken;
  }

  async function api(path, options = {}, retry = true) {
    if (!accessToken) await refreshAccessToken();
    const headers = new Headers(options.headers || {});
    headers.set('Authorization', `Bearer ${accessToken}`);
    if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }
    const response = await fetch(path, { ...options, headers, credentials: 'include' });
    if (response.status === 401 && retry) {
      accessToken = '';
      await refreshAccessToken();
      return api(path, options, false);
    }
    const contentType = response.headers.get('content-type') || '';
    const data = contentType.includes('application/json') ? await response.json().catch(() => ({})) : {};
    if (!response.ok) {
      const detail = data && typeof data.detail === 'object' ? data.detail : {};
      const message = detail.message || data.detail || data.message || 'Payment request could not be completed.';
      const error = new Error(String(message));
      error.code = detail.code || data.code || '';
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function loadCashfreeSdk() {
    if (window.Cashfree) return Promise.resolve(window.Cashfree);
    if (sdkPromise) return sdkPromise;
    sdkPromise = new Promise((resolve, reject) => {
      const existing = document.querySelector('script[data-placeai-cashfree-sdk]');
      if (existing) {
        existing.addEventListener('load', () => window.Cashfree ? resolve(window.Cashfree) : reject(new Error('Cashfree checkout SDK did not initialize.')), { once: true });
        existing.addEventListener('error', () => reject(new Error('Cashfree checkout SDK could not be loaded.')), { once: true });
        return;
      }
      const script = document.createElement('script');
      script.src = 'https://sdk.cashfree.com/js/v3/cashfree.js';
      script.async = true;
      script.dataset.placeaiCashfreeSdk = '';
      script.onload = () => window.Cashfree ? resolve(window.Cashfree) : reject(new Error('Cashfree checkout SDK did not initialize.'));
      script.onerror = () => reject(new Error('Cashfree checkout SDK could not be loaded.'));
      document.head.appendChild(script);
    });
    return sdkPromise;
  }

  async function verifyOrder(orderId, attempts = 5) {
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      const result = await api(`/billing/verify/${encodeURIComponent(orderId)}`, { method: 'POST' });
      if (result.verified) return result;
      if (!result.pending) return result;
      if (attempt + 1 < attempts) await delay(1400);
    }
    return { verified: false, pending: true, order_id: orderId };
  }

  async function startCheckout(endpoint) {
    const trigger = document.activeElement;
    if (trigger instanceof HTMLButtonElement) trigger.disabled = true;
    try {
      const checkout = await api(endpoint, { method: 'POST' });
      if (checkout.already_unlocked) {
        paymentToast('Already unlocked', 'This feature is already available on your PlaceAI account.');
        location.reload();
        return;
      }
      if (!checkout.payment_session_id || !checkout.order_id) throw new Error('Secure checkout session was not created.');

      const Cashfree = await loadCashfreeSdk();
      const cashfree = Cashfree({ mode: checkout.sdk_mode === 'sandbox' ? 'sandbox' : 'production' });
      const result = await cashfree.checkout({
        paymentSessionId: checkout.payment_session_id,
        redirectTarget: '_modal'
      });
      if (result && result.error) throw new Error(result.error.message || 'Payment was not completed.');

      paymentToast('Verifying payment', 'PlaceAI is confirming the payment directly with Cashfree.');
      const verified = await verifyOrder(checkout.order_id);
      if (verified.verified) {
        paymentToast('Payment verified', 'Your PlaceAI access has been updated.');
        await delay(450);
        location.reload();
        return;
      }
      paymentToast('Payment pending', 'Cashfree has not confirmed a successful payment yet. No access was changed.', 'error');
    } catch (error) {
      paymentToast('Secure checkout unavailable', error.message || 'Payment could not be completed.', 'error');
    } finally {
      if (trigger instanceof HTMLButtonElement) trigger.disabled = false;
    }
  }

  async function decorateBillingView() {
    const root = document.querySelector('#app-content');
    if (!root || root.querySelector('[data-placeai-payment-plan]')) return;
    const text = root.textContent || '';
    if (!text.includes('Independent student access') || !text.includes('Online checkout is not available yet')) return;

    try {
      const plans = await api('/billing/plans');
      if (!plans.checkout_enabled || !plans.plans || !plans.plans.length) return;
      const intro = [...root.querySelectorAll('.form-intro')].find(node => (node.textContent || '').includes('Online checkout is not available yet'));
      if (!intro) return;
      const plan = plans.plans[0];
      intro.innerHTML = '';
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'button button-primary';
      button.dataset.placeaiPaymentPlan = '';
      button.textContent = `Activate 30-day access for ₹${Number(plan.price_inr || 299)}`;
      const note = document.createElement('span');
      note.className = 'table-secondary';
      note.textContent = ' Secure payment by Cashfree. Access is granted only after server-side payment verification.';
      intro.append(button, note);
    } catch {
      // Keep the existing fail-closed billing copy if checkout cannot be positively confirmed as ready.
    }
  }

  function scheduleDecorate() {
    clearTimeout(decorateTimer);
    decorateTimer = setTimeout(decorateBillingView, 120);
  }

  async function handleReturnOrder() {
    if (returnHandled) return;
    const url = new URL(location.href);
    const orderId = url.searchParams.get('order_id');
    if (url.searchParams.get('placeai_payment') !== '1' || !orderId) return;
    returnHandled = true;
    try {
      const result = await verifyOrder(orderId);
      if (result.verified) paymentToast('Payment verified', 'Your PlaceAI access has been updated.');
      else paymentToast('Payment pending', 'No successful Cashfree payment has been confirmed yet.', 'error');
    } catch (error) {
      paymentToast('Payment verification failed', error.message || 'Payment could not be verified.', 'error');
    } finally {
      url.searchParams.delete('placeai_payment');
      url.searchParams.delete('order_id');
      history.replaceState({}, '', url.pathname + url.search + url.hash);
      scheduleDecorate();
    }
  }

  document.addEventListener('click', event => {
    const roadmap = event.target.closest('[data-action="roadmap-checkout"]');
    if (roadmap && !roadmap.disabled) {
      event.preventDefault();
      event.stopImmediatePropagation();
      startCheckout('/billing/roadmap-checkout');
      return;
    }
    const plan = event.target.closest('[data-placeai-payment-plan]');
    if (plan && !plan.disabled) {
      event.preventDefault();
      event.stopImmediatePropagation();
      startCheckout('/billing/checkout');
    }
  }, true);

  const observer = new MutationObserver(scheduleDecorate);
  observer.observe(document.documentElement, { subtree: true, childList: true });
  addEventListener('DOMContentLoaded', () => {
    scheduleDecorate();
    handleReturnOrder();
  }, { once: true });
  if (document.readyState !== 'loading') {
    scheduleDecorate();
    handleReturnOrder();
  }
})();
