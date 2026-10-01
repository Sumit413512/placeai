from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_release_ux_access_request_decorator_is_idempotent() -> None:
    app_js = (ROOT / "app/static/release-ux-fixes.js").read_text(encoding="utf-8")
    public_js = (ROOT / "public/static/release-ux-fixes.js").read_text(encoding="utf-8")

    assert app_js == public_js
    assert "const desiredLabel = currentStatus === 'provisioned' ? 'Resend password setup link' : 'Provision recruiter';" in app_js
    assert "if (!busy && button.textContent !== desiredLabel) button.textContent = desiredLabel;" in app_js
    assert "button.textContent = currentStatus === 'provisioned' ? 'Resend password setup link' : 'Provision recruiter';" not in app_js
    assert "button.dataset.busy = 'true';" in app_js
    assert "button.dataset.busy = 'false';" in app_js
    assert "if (button.isConnected) decorateAccessRows(row || document);" in app_js


def test_release_ux_observer_ignores_text_only_feedback_mutations() -> None:
    js = (ROOT / "app/static/release-ux-fixes.js").read_text(encoding="utf-8")

    assert "let relevant = false;" in js
    assert "if (node instanceof Element)" in js
    assert "if (!relevant) return;" in js
    assert "observer.observe(document.body, {childList: true, subtree: true});" in js
