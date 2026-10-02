from __future__ import annotations

import json
import subprocess
import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import roadmap_public_market
from app import roadmap_service


@pytest.mark.parametrize("skill_count", [3, 7])
@pytest.mark.parametrize("all_known", [False, True])
def test_small_valid_skill_sample_terminates_without_inventing_skills(skill_count, all_known):
    skills = ["SQL", "Python", "Excel", "Tableau", "Pandas", "NumPy", "Docker"][:skill_count]
    request = _request()
    request["current_skills"] = skills if all_known else []
    jobs = [{
        "title": "Data Analyst",
        "description": " ".join(skills),
        "url": f"https://example.com/jobs/{index}",
        "source": "Test feed",
        "location": "India",
    } for index in range(3)]
    # A subprocess deadline makes an infinite-loop regression fail rather than
    # hanging the whole CI worker. The feed is replaced; no network is used.
    result = subprocess.run(
        [sys.executable, "-c", """
import json, sys
from app import roadmap_public_market as market
data = json.load(sys.stdin)
market._fetch_jobs = lambda request: data['jobs']
payload, sources, _ = market.build_public_market_roadmap(data['request'])
print(json.dumps({'phases': payload['phases'], 'sources': sources}))
"""],
        input=json.dumps({"request": request, "jobs": jobs}),
        text=True, capture_output=True, timeout=10, check=True,
    )
    payload = json.loads(result.stdout)
    assert len(payload["phases"]) == 4
    assert len(payload["sources"]) == 3
    assert {skill["name"] for phase in payload["phases"] for skill in phase["skills"]} <= set(skills)


def _request() -> dict:
    return {
        "target_roles": ["Data Analyst"],
        "target_fields": ["Data Analytics"],
        "interests": ["business intelligence", "automation"],
        "current_skills": ["Python", "SQL", "Power BI"],
        "experience_level": "advanced",
        "market_region": "India",
        "hours_per_week": 10,
        "desired_timeline_days": 120,
        "learning_style": "project-first, visual, structured",
        "goals_constraints": "placement preparation and internship readiness",
    }


def _remote_ok_payload() -> list[dict]:
    return [
        {"last_updated": 1790000000, "legal": "link back"},
        {
            "position": "Data Analyst",
            "company": "Acme Analytics",
            "location": "Worldwide",
            "description": "Use SQL, Python, Excel, Tableau and statistics to build dashboards and communicate findings to stakeholders.",
            "tags": ["data", "sql", "python", "tableau"],
            "url": "https://remoteok.com/remote-jobs/1",
            "date": "2026-10-01T09:00:00+00:00",
        },
        {
            "position": "Business Data Analyst",
            "company": "Metric Labs",
            "location": "Remote",
            "description": "Build Power BI dashboards, SQL models, ETL pipelines and stakeholder reporting. Git experience preferred.",
            "tags": ["analytics", "power-bi", "etl"],
            "url": "https://remoteok.com/remote-jobs/2",
            "date": "2026-09-30T09:00:00+00:00",
        },
        {
            "position": "Product Data Analyst",
            "company": "Signal Co",
            "location": "Asia",
            "description": "Python pandas SQL statistics experimentation, Tableau dashboards and communication with product stakeholders.",
            "tags": ["data", "python", "sql"],
            "url": "https://remoteok.com/remote-jobs/3",
            "date": "2026-09-29T09:00:00+00:00",
        },
        {
            "position": "Analytics Engineer",
            "company": "Warehouse Works",
            "location": "India / Remote",
            "description": "SQL dbt Snowflake data modeling Git and business intelligence workflows.",
            "tags": ["data", "dbt", "snowflake"],
            "url": "https://remoteok.com/remote-jobs/4",
            "date": "2026-09-28T09:00:00+00:00",
        },
    ]


def _arbeitnow_payload() -> dict:
    return {
        "data": [
            {
                "title": "Junior Data Analyst",
                "company_name": "Example GmbH",
                "location": "Remote",
                "description": "<p>Analyze data with SQL, Excel, Python and Tableau. Present dashboards to stakeholders.</p>",
                "tags": ["IT", "Data"],
                "url": "https://www.arbeitnow.com/jobs/example-data-analyst",
                "created_at": 1790000000,
            },
            {
                "title": "Software Engineer",
                "company_name": "Other Co",
                "location": "Berlin",
                "description": "<p>Java and Kubernetes services.</p>",
                "tags": ["Engineering"],
                "url": "https://www.arbeitnow.com/jobs/example-engineer",
                "created_at": 1790000000,
            },
        ]
    }


def test_public_market_fallback_builds_cited_market_roadmap(monkeypatch):
    def fake_fetch(url: str):
        if "remoteok.com" in url:
            return _remote_ok_payload()
        if "arbeitnow.com" in url:
            return _arbeitnow_payload()
        raise AssertionError(url)

    monkeypatch.setattr(roadmap_public_market, "_fetch_json", fake_fetch)
    payload, sources, model = roadmap_public_market.build_public_market_roadmap(_request())

    assert model == "public_market:remote_feeds_v1"
    assert payload["title"].startswith("Data Analyst")
    assert len(payload["phases"]) == 4
    assert sum(phase["days"] for phase in payload["phases"]) >= 42
    assert payload["weekly_hours"] == 10

    snapshot = payload["market_snapshot"]
    assert snapshot["region"] == "India"
    assert "SQL" in snapshot["in_demand_skills"]
    assert "Python" in snapshot["in_demand_skills"]
    assert any(skill in snapshot["in_demand_skills"] for skill in ("Tableau", "Excel", "Statistics"))
    assert any("matched current public job listings" in signal for signal in snapshot["demand_signals"])
    assert any("public feeds" in note.lower() for note in snapshot["market_notes"])

    assert len(sources) >= 3
    assert all(source["url"].startswith("https://") for source in sources)
    assert any(source["title"].startswith("Remote OK") for source in sources)
    assert any(source["title"].startswith("Arbeitnow") for source in sources)


def test_public_market_fallback_does_not_promote_unseen_skills(monkeypatch):
    monkeypatch.setattr(roadmap_public_market, "_fetch_json", lambda url: (
        _remote_ok_payload() if "remoteok.com" in url else _arbeitnow_payload()
    ))
    payload, _, _ = roadmap_public_market.build_public_market_roadmap(_request())

    skills = payload["market_snapshot"]["in_demand_skills"]
    assert "TensorFlow" not in skills
    assert "Kubernetes" not in skills
    assert "React" not in skills


def test_public_market_fallback_fails_closed_without_enough_market_evidence(monkeypatch):
    monkeypatch.setattr(
        roadmap_public_market,
        "_fetch_json",
        lambda url: [{"position": "Unrelated Role", "url": "https://remoteok.com/remote-jobs/x"}]
        if "remoteok.com" in url else {"data": []},
    )

    with pytest.raises(roadmap_public_market.PublicMarketFallbackUnavailable):
        roadmap_public_market.build_public_market_roadmap(_request())


def test_generate_market_roadmap_recovers_from_all_provider_failure(monkeypatch):
    request = _request()
    profile = SimpleNamespace()
    db = SimpleNamespace()

    monkeypatch.setattr(roadmap_service, "_profile_context", lambda profile: {})
    monkeypatch.setattr(roadmap_service, "_public_market_context", lambda db: {})
    monkeypatch.setattr(
        roadmap_service,
        "search_current_market",
        lambda prompt, gateway_token=None: (_ for _ in ()).throw(
            HTTPException(
                status_code=503,
                detail={
                    "code": "CURRENT_MARKET_GATEWAY_AUTH",
                    "message": "provider unavailable",
                    "diagnostics": {
                        "primary_code": "CURRENT_MARKET_PROVIDER_QUOTA",
                        "fallback_code": "CURRENT_MARKET_FALLBACK_QUOTA",
                        "gateway_code": "CURRENT_MARKET_GATEWAY_AUTH",
                        "gateway_http_status": 403,
                        "gateway_error_type": "customer_verification_required",
                        "gateway_credential_source": "runtime_oidc",
                        "response": "private upstream response",
                        "token": "private upstream token",
                    },
                },
            )
        ),
    )

    public_payload = {
        "title": "Data Analyst Public Market Roadmap",
        "market_snapshot": {
            "region": "India",
            "target_roles": ["Data Analyst"],
            "demand_signals": ["SQL appears in current listings"],
            "in_demand_skills": ["SQL", "Python", "Tableau"],
            "tools_and_technologies": ["SQL", "Python", "Tableau"],
            "entry_level_expectations": ["Build practical evidence"],
            "market_notes": ["Live public feed fallback"],
        },
        "estimated_days": 60,
        "weekly_hours": 10,
        "learning_pattern": {
            "recommended_style": "project-first",
            "weekly_cycle": "learn, build, review",
            "daily_session": "practice then build",
            "revision_strategy": "weekly review",
        },
        "phases": [
            {
                "phase": 1,
                "name": "Foundations",
                "days": 30,
                "outcomes": ["Working foundation"],
                "skills": [{"name": "Tableau", "level": "working", "why": "current listings"}],
                "projects": [],
                "practice": ["Practice"],
                "milestone": "Complete",
            },
            {
                "phase": 2,
                "name": "Portfolio",
                "days": 30,
                "outcomes": ["Portfolio evidence"],
                "skills": [{"name": "SQL", "level": "working", "why": "current listings"}],
                "projects": [],
                "practice": ["Build"],
                "milestone": "Publish",
            },
        ],
        "advanced_next_steps": ["Refresh evidence"],
        "portfolio_plan": ["Publish project"],
        "interview_preparation": ["Practice SQL"],
    }
    public_sources = [
        {"title": "Remote OK — Example", "url": "https://remoteok.com/remote-jobs/1"},
        {"title": "Remote OK — Example 2", "url": "https://remoteok.com/remote-jobs/2"},
        {"title": "Arbeitnow — Example", "url": "https://www.arbeitnow.com/jobs/example"},
    ]
    monkeypatch.setattr(
        roadmap_service,
        "build_public_market_roadmap",
        lambda request_data: (public_payload, public_sources, "public_market:remote_feeds_v1"),
    )

    diagnostics = {}
    roadmap, sources, model = roadmap_service.generate_market_roadmap(
        db=db,
        profile=profile,
        request_data=request,
        gateway_token="test-oidc",
        provider_diagnostics=diagnostics,
    )

    assert model == "public_market:remote_feeds_v1"
    assert roadmap["title"] == "Data Analyst Public Market Roadmap"
    assert len(roadmap["phases"]) == 2
    assert sources == public_sources
    assert diagnostics == {
        "gateway_http_status": 403,
        "gateway_error_type": "customer_verification_required",
        "gateway_credential_source": "runtime_oidc",
    }
    assert "gateway_http_status" not in roadmap
    assert "private upstream" not in json.dumps(roadmap)
