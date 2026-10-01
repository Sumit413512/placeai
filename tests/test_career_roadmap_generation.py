from __future__ import annotations

from app.roadmap_market import _extract_sources
from app.roadmap_service import normalize_roadmap_payload


def test_normalize_roadmap_uses_phase_duration_as_canonical_total():
    request = {
        "target_roles": ["Data Engineer"],
        "target_fields": ["Data"],
        "market_region": "India",
        "hours_per_week": 12,
        "desired_timeline_days": 60,
    }
    payload = {
        "title": "Data Engineer Roadmap",
        "estimated_days": 999,
        "market_snapshot": {
            "region": "India",
            "target_roles": ["Data Engineer"],
            "in_demand_skills": ["SQL", "Python"],
        },
        "weekly_hours": 12,
        "learning_pattern": {"weekly_cycle": "Learn, build, review"},
        "phases": [
            {"phase": 1, "name": "Foundations", "days": 30, "skills": ["SQL"]},
            {"phase": 2, "name": "Build", "days": 45, "skills": [{"name": "Python", "level": "working"}]},
        ],
    }
    result = normalize_roadmap_payload(payload, request_data=request)
    assert result["estimated_days"] == 75
    assert result["market_snapshot"]["in_demand_skills"] == ["SQL", "Python"]
    assert len(result["phases"]) == 2


def test_web_search_source_extraction_deduplicates_and_rejects_unsafe_urls():
    payload = {
        "output": [
            {
                "type": "web_search_call",
                "action": {
                    "sources": [
                        {"title": "Employer careers", "url": "https://example.com/jobs"},
                        {"title": "Employer careers duplicate", "url": "https://example.com/jobs"},
                        {"title": "Unsafe", "url": "javascript:alert(1)"},
                    ]
                },
            },
            {
                "type": "message",
                "content": [{
                    "type": "output_text",
                    "text": "{}",
                    "annotations": [{"type": "url_citation", "title": "Report", "url": "https://example.org/report"}],
                }],
            },
        ]
    }
    sources = _extract_sources(payload)
    assert sources == [
        {"title": "Employer careers", "url": "https://example.com/jobs"},
        {"title": "Report", "url": "https://example.org/report"},
    ]
