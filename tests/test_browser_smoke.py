from __future__ import annotations

import os
from pathlib import Path
import socket
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

    page.locator('button[data-open-auth="login"]').first.click()
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
