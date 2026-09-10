from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _app_js() -> str:
    return (ROOT / "app/static/app.js").read_text(encoding="utf-8")


def test_notification_mark_all_uses_persistent_backend_action_once() -> None:
    js = _app_js()
    assert "await api('/enterprise/notifications/read-all',{method:'POST'})" in js
    assert "state.notificationsRead=true;updateNotificationBadge();renderNotifications();toast('Notifications marked as read')" not in js


def test_recruiter_pipeline_is_read_only_in_frontend() -> None:
    js = _app_js()
    assert "const canEdit=state.me?.role==='institution_admin'" in js
    assert "Pipeline structure is controlled by the institution placement office." in js
    assert "Recruiters can review stages and move authorized applicants, but cannot alter the institution-owned stage design." in js


def test_student_opportunities_show_existing_application_state() -> None:
    js = _app_js()
    assert "Promise.all([api('/students/jobs'),api('/students/applications')])" in js
    assert "state.appliedJobIds=new Set(apps.map(a=>a.job_id))" in js
    assert "state.appliedJobIds?.has(j.id)" in js
    assert ">Applied</button>" in js


def test_nonfunctional_external_notification_channels_are_not_advertised() -> None:
    js = _app_js()
    assert "Future provider integration" not in js
    assert "WhatsApp</strong>" not in js
    assert ">SMS</strong>" not in js
    assert "In-app notifications" in js
