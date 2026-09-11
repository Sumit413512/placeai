from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_notification_links_resolve_to_role_scoped_workspace_views() -> None:
    js = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert "function notificationTarget(link)" in js
    assert "split(':', 1)[0]" in js
    assert "await navigate(notificationTarget(val))" in js
    assert "if (view === 'notifications') { await renderNotifications(); return; }" in js


def test_unique_announcement_notification_links_remain_supported() -> None:
    backend = (ROOT / "app/routers/enterprise.py").read_text(encoding="utf-8")
    frontend = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert 'link = f"announcements:{row.id}"' in backend
    assert "function notificationTarget(link)" in frontend
