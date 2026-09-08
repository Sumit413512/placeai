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


def request_for(path: str = "/ai/test") -> Request:
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 45678),
        "server": ("testserver", 80),
    })


def test_ai_budget_allows_bounded_requests_then_returns_429():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    user = SimpleNamespace(id="ai-budget-test-user")
    try:
        db.query(RateLimitBucket).filter(RateLimitBucket.scope.like("ai:%")).delete(synchronize_session=False)
        db.commit()

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
        db.query(RateLimitBucket).filter(RateLimitBucket.scope.like("ai:%")).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_ai_endpoint_buckets_are_path_scoped_but_share_aggregate_budget():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    user = SimpleNamespace(id="ai-path-test-user")
    try:
        db.query(RateLimitBucket).filter(RateLimitBucket.scope.like("ai:%")).delete(synchronize_session=False)
        db.commit()
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
        db.query(RateLimitBucket).filter(RateLimitBucket.scope.like("ai:%")).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_cost_generating_routes_are_guarded_but_status_and_history_are_not():
    ai_source = open("app/routers/ai.py", encoding="utf-8").read()
    mock_source = open("app/routers/mock_interview.py", encoding="utf-8").read()

    expected_student = [
        "/parse-resume",
        "/match-jobs",
        "/generate-summary",
        "/skill-gap/{job_id}",
        "/interview/questions",
        "/interview/evaluate",
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
