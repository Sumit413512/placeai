from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.ai_rate_limit import (
    AI_STUDENT_ENDPOINT_LIMIT_PER_10_MIN,
    _enforce_ai_budget,
)
from app.database import Base, SessionLocal, engine
from app.models import RateLimitBucket
from app.rate_limit import enforce_rate_limit


def request_for(path: str = "/ai/test", client_host: str = "127.0.0.1") -> Request:
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": [],
        "client": (client_host, 45678),
        "server": ("testserver", 80),
    })


def _clear_scope(db, prefix: str) -> None:
    db.query(RateLimitBucket).filter(RateLimitBucket.scope.like(f"{prefix}%")).delete(synchronize_session=False)
    db.commit()


def test_ai_budget_allows_bounded_requests_then_returns_429():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    user = SimpleNamespace(id="ai-budget-test-user")
    try:
        _clear_scope(db, "ai:")
        for _ in range(AI_STUDENT_ENDPOINT_LIMIT_PER_10_MIN):
            _enforce_ai_budget(
                request_for("/ai/test"),
                db,
                user,
                endpoint_limit=AI_STUDENT_ENDPOINT_LIMIT_PER_10_MIN,
            )

        with pytest.raises(HTTPException) as exc:
            _enforce_ai_budget(
                request_for("/ai/test"),
                db,
                user,
                endpoint_limit=AI_STUDENT_ENDPOINT_LIMIT_PER_10_MIN,
            )
        assert exc.value.status_code == 429
        assert exc.value.headers and int(exc.value.headers["Retry-After"]) > 0
    finally:
        _clear_scope(db, "ai:")
        db.close()


def test_ai_endpoint_buckets_are_path_scoped_but_share_aggregate_budget():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    user = SimpleNamespace(id="ai-path-test-user")
    try:
        _clear_scope(db, "ai:")
        _enforce_ai_budget(request_for("/ai/generate-summary"), db, user, endpoint_limit=12)
        _enforce_ai_budget(request_for("/mock-interview/start"), db, user, endpoint_limit=12)

        rows = db.query(RateLimitBucket).filter(RateLimitBucket.scope.like("ai:%")).all()
        scopes = {row.scope for row in rows}
        assert "ai:aggregate" in scopes
        assert "ai:/ai/generate-summary" in scopes
        assert "ai:/mock-interview/start" in scopes
        aggregate = next(row for row in rows if row.scope == "ai:aggregate")
        assert aggregate.request_count == 2
    finally:
        _clear_scope(db, "ai:")
        db.close()


def test_ai_budget_cannot_be_reset_by_changing_client_ip():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    user = SimpleNamespace(id="ai-ip-rotation-user")
    try:
        _clear_scope(db, "ai:")
        for index in range(AI_STUDENT_ENDPOINT_LIMIT_PER_10_MIN):
            host = f"10.20.0.{index + 1}"
            _enforce_ai_budget(
                request_for("/ai/generate-summary", client_host=host),
                db,
                user,
                endpoint_limit=AI_STUDENT_ENDPOINT_LIMIT_PER_10_MIN,
            )

        rows = db.query(RateLimitBucket).filter(RateLimitBucket.scope.like("ai:%")).all()
        assert len(rows) == 2
        endpoint = next(row for row in rows if row.scope == "ai:/ai/generate-summary")
        assert endpoint.request_count == AI_STUDENT_ENDPOINT_LIMIT_PER_10_MIN

        with pytest.raises(HTTPException) as exc:
            _enforce_ai_budget(
                request_for("/ai/generate-summary", client_host="203.0.113.250"),
                db,
                user,
                endpoint_limit=AI_STUDENT_ENDPOINT_LIMIT_PER_10_MIN,
            )
        assert exc.value.status_code == 429
    finally:
        _clear_scope(db, "ai:")
        db.close()


def test_default_limiter_remains_client_address_aware():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _clear_scope(db, "auth-ip-test")
        enforce_rate_limit(
            db,
            request_for("/auth/test", client_host="10.0.0.1"),
            scope="auth-ip-test",
            identifier="same-account",
            limit=1,
            window_seconds=600,
        )
        enforce_rate_limit(
            db,
            request_for("/auth/test", client_host="10.0.0.2"),
            scope="auth-ip-test",
            identifier="same-account",
            limit=1,
            window_seconds=600,
        )
        rows = db.query(RateLimitBucket).filter(RateLimitBucket.scope == "auth-ip-test").all()
        assert len(rows) == 2

        with pytest.raises(HTTPException) as exc:
            enforce_rate_limit(
                db,
                request_for("/auth/test", client_host="10.0.0.1"),
                scope="auth-ip-test",
                identifier="same-account",
                limit=1,
                window_seconds=600,
            )
        assert exc.value.status_code == 429
    finally:
        _clear_scope(db, "auth-ip-test")
        db.close()


def test_cost_generating_routes_are_guarded_but_status_and_history_are_not():
    ai_source = open("app/routers/ai.py", encoding="utf-8").read()
    mock_source = open("app/routers/mock_interview.py", encoding="utf-8").read()
    compat_source = open("app/routers/interview_compat.py", encoding="utf-8").read()

    expected_student = [
        "/parse-resume",
        "/match-jobs",
        "/generate-summary",
        "/skill-gap/{job_id}",
    ]
    for route in expected_student:
        anchor = f'"{route}"'
        pos = ai_source.index(anchor)
        window = ai_source[pos:pos + 260]
        assert "student_ai_guard" in window

    rank_pos = ai_source.index('"/rank-candidates/{job_id}"')
    assert "recruiter_ai_guard" in ai_source[rank_pos:rank_pos + 280]
    assistant_pos = ai_source.index('@router.post("/assistant"')
    assert "authenticated_ai_guard" in ai_source[assistant_pos:assistant_pos + 260]

    status_pos = ai_source.index('@router.get("/status"')
    assert "ai_guard" not in ai_source[status_pos:status_pos + 180]
    assert '@router.post("/start", dependencies=[Depends(student_ai_guard)])' in mock_source
    assert '@router.post("/evaluate", dependencies=[Depends(student_ai_guard)])' in mock_source
    assert '@router.get("/history")' in mock_source

    # The legacy interview write endpoints are authenticated 410 compatibility
    # shims now; they perform no model call and therefore must not consume an AI budget.
    for route in ("/ai/interview/questions", "/ai/interview/evaluate"):
        anchor = f'@router.post("{route}", deprecated=True)'
        pos = compat_source.index(anchor)
        window = compat_source[pos:pos + 420]
        assert "Depends(require_student)" in window
        assert "student_ai_guard" not in window
