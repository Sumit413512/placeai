from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.request import urlopen

import pytest
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
PORT = 8765
BASE_URL = f"http://{HOST}:{PORT}"


def _wait_until_ready(timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urlopen(f"{BASE_URL}/health", timeout=1.5) as response:  # noqa: S310 - local test server only
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("PlaceAI browser-smoke server did not become healthy")


@pytest.fixture(scope="module")
def local_server(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("browser-smoke") / "placeai.db"
    env = os.environ.copy()
    env.update(
        {
            "ENVIRONMENT": "development",
            "DATABASE_URL": f"sqlite:///{db_path}",
            "AUTO_CREATE_SCHEMA": "true",
            "DEV_SHOW_RESET_TOKEN": "false",
            "JWT_SECRET_KEY": "browser-smoke-access-secret-abcdefghijklmnopqrstuvwxyz",
            "JWT_REFRESH_SECRET_KEY": "browser-smoke-refresh-secret-abcdefghijklmnopqrstuvwxyz",
            "BASE_URL": BASE_URL,
            "ALLOWED_ORIGINS": BASE_URL,
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.app:app", "--host", HOST, "--port", str(PORT)],
        cwd=ROOT,
        env=env,
        # Browser pages generate enough access-log output to fill an unread PIPE on
        # Windows, which blocks uvicorn and turns later navigations into timeouts.
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_until_ready()
        yield
    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()


@pytest.fixture(scope="module")
def browser(local_server):
    del local_server
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            yield browser
        finally:
            browser.close()


def test_public_shell_auth_modal_and_mobile_layout(browser) -> None:
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(BASE_URL, wait_until="domcontentloaded")
    assert "PlaceAI" in page.title()
    assert page.locator(".site-header .brand").is_visible()
    assert page.locator('link[rel="icon"][href="/static/placeai-icon.svg"]').count() == 1

    # The compact header intentionally hides desktop actions. Exercise the visible
    # hero CTA that mobile users actually receive instead of forcing a hidden node.
    mobile_sign_in = page.locator('.hero button[data-open-auth="login"]')
    assert mobile_sign_in.is_visible()
    mobile_sign_in.click()
    page.locator("#auth-overlay").wait_for(state="visible")
    box = page.locator("#auth-overlay .auth-modal").bounding_box()
    assert box is not None
    assert box["x"] >= -1
    assert box["x"] + box["width"] <= 391
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    page.close()


def test_password_recovery_token_survives_reload_and_enforces_rules(browser) -> None:
    token = "A" * 32
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(f"{BASE_URL}/?reset_token={token}", wait_until="domcontentloaded")
    page.locator("#placeai-password-recovery").wait_for(state="visible")
    assert "reset_token" not in page.url
    assert page.evaluate("sessionStorage.getItem('placeai.password.reset.v1')") == token

    page.reload(wait_until="domcontentloaded")
    page.locator("#placeai-password-recovery").wait_for(state="visible")
    assert page.evaluate("sessionStorage.getItem('placeai.password.reset.v1')") == token

    submit = page.locator("#password-recovery-submit")
    page.locator("#password-recovery-new").fill("weakpassword")
    page.locator("#password-recovery-confirm").fill("weakpassword")
    assert submit.is_disabled()

    strong = "Production#Pass123"
    page.locator("#password-recovery-new").fill(strong)
    page.locator("#password-recovery-confirm").fill(strong)
    assert submit.is_enabled()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    page.close()


def test_generated_temporary_password_survives_submit_capture_race(browser) -> None:
    page = browser.new_page()
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.add_script_tag(url=f"{BASE_URL}/static/provisioning-password-fix.js")
    page.evaluate(
        """
        () => {
          const host = document.createElement('div');
          host.innerHTML = '<form id="admin-form"><label>Temporary password<input name="temporary_password" type="password" minlength="12" required></label><button type="submit">Create</button></form>';
          document.body.appendChild(host);
        }
        """
    )
    field = page.locator('#admin-form input[name="temporary_password"]')
    field.wait_for(state="attached")
    page.wait_for_function("document.querySelector('#admin-form input[name=\"temporary_password\"]')?.dataset.placeaiAutoTempPassword === '1'")
    password = field.input_value()
    assert 12 <= len(password) <= 128
    assert re.search(r"[a-z]", password)
    assert re.search(r"[A-Z]", password)
    assert re.search(r"[0-9]", password)
    assert re.search(r"[^A-Za-z0-9]", password)
    assert field.is_editable() is False

    page.evaluate(
        """
        () => document.querySelector('#admin-form').dispatchEvent(
          new SubmitEvent('submit', {bubbles: true, cancelable: true})
        )
        """
    )
    page.wait_for_timeout(50)
    assert field.input_value() == password
    page.close()


def test_unconfigured_ai_is_disabled_in_workspace_controls(browser) -> None:
    page = browser.new_page()
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.add_script_tag(url=f"{BASE_URL}/static/ai-readiness.js")
    page.evaluate(
        """
        () => {
          const host = document.createElement('div');
          host.innerHTML = '<button data-action="parse-resume">Parse resume</button><form id="assistant-form"><textarea name="message"></textarea><button type="submit">Ask</button></form>';
          document.body.appendChild(host);
        }
        """
    )
    page.wait_for_function("window.PlaceAIAIReadiness?.snapshot().checked === true")
    snapshot = page.evaluate("window.PlaceAIAIReadiness.snapshot()")
    assert snapshot["ready"] is False
    assert page.locator('[data-action="parse-resume"]').is_disabled()
    assert page.locator('#assistant-form button[type="submit"]').is_disabled()
    assert page.locator('#assistant-form .placeai-ai-unavailable-note').count() == 1
    page.close()


def test_auth_modal_focus_lock_escape_and_opener_restoration(browser) -> None:
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(BASE_URL, wait_until="domcontentloaded")
    opener = page.locator('.hero button[data-open-auth="login"]')
    opener.click()
    dialog = page.locator("#auth-overlay")
    dialog.wait_for(state="visible")
    page.wait_for_timeout(50)
    assert page.evaluate("document.body.classList.contains('modal-open')")

    page.evaluate(
        """() => {
            const dialog = document.querySelector('#auth-overlay');
            const items = [...dialog.querySelectorAll('input:not([type="hidden"]):not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])')].filter(item => item.getClientRects().length);
            items[items.length - 1].focus();
        }"""
    )
    page.keyboard.press("Tab")
    assert page.evaluate(
        """() => {
            const dialog = document.querySelector('#auth-overlay');
            const items = [...dialog.querySelectorAll('input:not([type="hidden"]):not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])')].filter(item => item.getClientRects().length);
            return dialog.contains(document.activeElement) && document.activeElement === items[0];
        }"""
    )

    page.evaluate(
        """() => {
            const generic = document.querySelector('#generic-modal');
            generic.querySelector('#generic-modal-content').innerHTML = '<h2 id="smoke-generic-title">Smoke dialog</h2>';
            generic.classList.remove('hidden');
            window.PlaceAIModalState.sync();
        }"""
    )
    page.keyboard.press("Escape")
    page.wait_for_timeout(50)
    assert not page.locator("#auth-overlay").evaluate("element => element.classList.contains('hidden')")
    assert page.evaluate("document.body.classList.contains('modal-open')")

    page.keyboard.press("Escape")
    page.wait_for_timeout(100)
    assert not page.evaluate("document.body.classList.contains('modal-open')")
    page.wait_for_timeout(100)
    assert page.evaluate("document.activeElement?.getAttribute('data-open-auth') === 'login'")
    page.close()


def test_privileged_role_rerender_focuses_visible_form_on_mobile(browser) -> None:
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.locator('.hero button[data-open-auth="login"]').click()
    page.locator("#auth-overlay").wait_for(state="visible")
    page.locator('#login-view [data-access-switch="create"]').click()
    page.wait_for_timeout(50)

    for role in ("recruiter", "institution_admin", "platform_admin"):
        page.locator(f'#signup-view [data-access-role="{role}"][data-access-role-mode="create"]').click()
        page.wait_for_timeout(80)
        state = page.evaluate(
            """() => {
                const panel = document.querySelector('.auth-form-panel');
                const input = document.querySelector('#role-access-request-form input:not([type="hidden"]):not([disabled])');
                const panelRect = panel.getBoundingClientRect();
                const inputRect = input.getBoundingClientRect();
                return {
                    focused: document.activeElement === input,
                    scrollTop: panel.scrollTop,
                    inputTop: inputRect.top,
                    inputBottom: inputRect.bottom,
                    panelTop: panelRect.top,
                    panelBottom: panelRect.bottom,
                };
            }"""
        )
        assert state["focused"], role
        assert state["inputTop"] >= state["panelTop"] - 1, (role, state)
        assert state["inputBottom"] <= state["panelBottom"] + 1, (role, state)
        assert state["scrollTop"] >= 0
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    page.close()
