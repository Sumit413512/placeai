from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen

import pytest
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
PORT = 8766
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
    raise RuntimeError("PlaceAI auth-shell regression server did not become healthy")


@pytest.fixture(scope="module")
def auth_shell_server(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("auth-shell") / "placeai.db"
    env = os.environ.copy()
    env.update(
        {
            "ENVIRONMENT": "development",
            "DATABASE_URL": f"sqlite:///{db_path}",
            "AUTO_CREATE_SCHEMA": "true",
            "DEV_SHOW_RESET_TOKEN": "false",
            "JWT_SECRET_KEY": "auth-shell-access-secret-abcdefghijklmnopqrstuvwxyz",
            "JWT_REFRESH_SECRET_KEY": "auth-shell-refresh-secret-abcdefghijklmnopqrstuvwxyz",
            "BASE_URL": BASE_URL,
            "ALLOWED_ORIGINS": BASE_URL,
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.app:app", "--host", HOST, "--port", str(PORT)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
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
def browser(auth_shell_server):
    del auth_shell_server
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            yield browser
        finally:
            browser.close()


def test_auth_portal_source_mirrors_and_handlers_are_singleton() -> None:
    portal = (ROOT / "app/static/access-portal.js").read_text(encoding="utf-8")
    public_portal = (ROOT / "public/static/access-portal.js").read_text(encoding="utf-8")
    ui_state = (ROOT / "app/static/ui-state-fixes.js").read_text(encoding="utf-8")
    public_ui_state = (ROOT / "public/static/ui-state-fixes.js").read_text(encoding="utf-8")
    core = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    public_core = (ROOT / "public/static/app-core.js").read_text(encoding="utf-8")

    assert portal == public_portal
    assert ui_state == public_ui_state
    assert core == public_core
    assert portal.count("document.addEventListener('click'") == 1
    assert portal.count("document.addEventListener('submit'") == 1
    assert "if (window.__PLACEAI_ACCESS_PORTAL_LOADED__) return;" in portal
    assert "if (window.__PLACEAI_UI_STATE_SHIM_LOADED__) return;" in ui_state
    assert "if (window.__PLACEAI_APP_CORE_LOADED__) return;" in core
    assert "function updateLoginRole(roleKey)" in portal
    assert "updateLoginRole(roleButton.dataset.accessRole);" in portal
    login_role_branch = portal.split("if (roleButton.dataset.accessRoleMode === 'login')", 1)[1].split("} else {", 1)[0]
    assert "renderLogin();" not in login_role_branch
    assert "firstInput.removeAttribute('tabindex');" in portal


@pytest.mark.parametrize(
    "viewport",
    [
        {"width": 1280, "height": 900},
        {"width": 390, "height": 844},
    ],
    ids=["desktop", "mobile"],
)
def test_auth_role_switching_is_immediate_responsive_and_accessible(browser, viewport) -> None:
    page = browser.new_page(viewport=viewport)
    page.goto(BASE_URL, wait_until="domcontentloaded")

    script_counts = page.evaluate(
        """() => [...document.scripts].reduce((counts, script) => {
            if (!script.src) return counts;
            const path = new URL(script.src).pathname;
            counts[path] = (counts[path] || 0) + 1;
            return counts;
        }, {})"""
    )
    assert script_counts.get("/static/access-portal.js") == 1
    assert script_counts.get("/static/ui-state-fixes.js") == 1
    assert script_counts.get("/static/app.js") == 1
    assert page.evaluate("window.__PLACEAI_ACCESS_PORTAL_LOADED__ === true")
    assert page.evaluate("window.__PLACEAI_UI_STATE_SHIM_LOADED__ === true")
    assert page.evaluate("window.__PLACEAI_APP_CORE_LOADED__ === true")

    opener = page.locator('.hero button[data-open-auth="login"]')
    opener.click()
    page.locator("#auth-overlay").wait_for(state="visible")
    page.wait_for_timeout(80)
    assert page.evaluate("document.body.classList.contains('modal-open')")

    student_login = page.locator('#login-view [data-access-role="student"][data-access-role-mode="login"]')
    recruiter_login = page.locator('#login-view [data-access-role="recruiter"][data-access-role-mode="login"]')
    email = page.locator('#role-login-form input[name="email"]')
    password = page.locator('#role-login-form input[name="password"]')
    hidden_role = page.locator('#role-login-form input[name="role"]')

    assert student_login.get_attribute("aria-selected") == "true"
    assert hidden_role.input_value() == "student"
    assert email.get_attribute("tabindex") != "-1"
    assert page.evaluate("document.activeElement === document.querySelector('#role-login-form input[name=\"email\"]')")
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement === document.querySelector('#role-login-form input[name=\"password\"]')")

    email.fill("recruiter.qa@example.invalid")
    password.fill("NoSubmit#12345")
    recruiter_login.click(timeout=3000)
    page.wait_for_timeout(80)
    assert recruiter_login.get_attribute("aria-selected") == "true"
    assert "is-selected" in (recruiter_login.get_attribute("class") or "")
    assert student_login.get_attribute("aria-selected") == "false"
    assert hidden_role.input_value() == "recruiter"
    assert email.input_value() == "recruiter.qa@example.invalid"
    assert password.input_value() == "NoSubmit#12345"
    assert email.is_editable()
    assert email.get_attribute("tabindex") != "-1"
    assert page.evaluate("document.activeElement === document.querySelector('#role-login-form input[name=\"email\"]')")
    assert page.locator('#role-login-form button[type="submit"]').inner_text() == "Continue to Recruiter"

    student_login.click(timeout=3000)
    page.wait_for_timeout(80)
    assert student_login.get_attribute("aria-selected") == "true"
    assert recruiter_login.get_attribute("aria-selected") == "false"
    assert hidden_role.input_value() == "student"
    assert email.input_value() == "recruiter.qa@example.invalid"
    assert password.input_value() == "NoSubmit#12345"

    page.locator('#login-view [data-access-switch="create"]').click()
    page.wait_for_timeout(80)
    student_create = page.locator('#signup-view [data-access-role="student"][data-access-role-mode="create"]')
    recruiter_create = page.locator('#signup-view [data-access-role="recruiter"][data-access-role-mode="create"]')
    assert student_create.get_attribute("aria-selected") == "true"
    assert page.locator("#role-student-signup-form").is_visible()

    recruiter_create.click(timeout=3000)
    page.wait_for_timeout(80)
    request_form = page.locator("#role-access-request-form")
    request_first = page.locator('#role-access-request-form input[name="full_name"]')
    assert request_form.is_visible()
    assert recruiter_create.get_attribute("aria-selected") == "true"
    assert student_create.get_attribute("aria-selected") == "false"
    assert page.locator('#role-access-request-form input[name="requested_role"]').input_value() == "recruiter"
    assert request_first.is_editable()
    assert request_first.get_attribute("tabindex") != "-1"
    assert page.evaluate("document.activeElement === document.querySelector('#role-access-request-form input[name=\"full_name\"]')")

    page.locator('#signup-view [data-access-role="student"][data-access-role-mode="create"]').click(timeout=3000)
    page.wait_for_timeout(80)
    assert page.locator("#role-student-signup-form").is_visible()
    assert page.locator('#signup-view [data-access-role="student"][data-access-role-mode="create"]').get_attribute("aria-selected") == "true"

    page.evaluate("document.querySelector('.auth-form-panel').scrollTop = document.querySelector('.auth-form-panel').scrollHeight")
    cancel = page.locator("#signup-view .auth-inline-cancel")
    cancel.wait_for(state="visible")
    cancel.click()
    page.wait_for_timeout(100)
    assert page.locator("#auth-overlay").evaluate("element => element.classList.contains('hidden')")
    assert page.evaluate("document.querySelector('.auth-form-panel').scrollTop === 0")
    assert not page.evaluate("document.body.classList.contains('modal-open')")
    assert page.evaluate("document.activeElement?.getAttribute('data-open-auth') === 'login'")

    opener.click()
    page.locator("#auth-overlay").wait_for(state="visible")
    page.wait_for_timeout(80)
    page.locator('#auth-overlay [data-action="close-auth"]').click()
    page.wait_for_timeout(100)
    assert page.locator("#auth-overlay").evaluate("element => element.classList.contains('hidden')")
    assert not page.evaluate("document.body.classList.contains('modal-open')")

    opener.click()
    page.locator("#auth-overlay").wait_for(state="visible")
    page.wait_for_timeout(80)
    page.keyboard.press("Escape")
    page.wait_for_timeout(100)
    assert page.locator("#auth-overlay").evaluate("element => element.classList.contains('hidden')")
    assert not page.evaluate("document.body.classList.contains('modal-open')")
    page.close()
