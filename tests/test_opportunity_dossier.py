from io import BytesIO
from unittest.mock import Mock

import httpx
from pypdf import PdfReader

from app import opportunity_insights
from app.opportunity_insights_pdf import render_guide


def _demo_job():
    return {
        "title": "Graduate Software Engineer - Demo",
        "company_name": "TechNova Demo",
        "is_demo": True,
        "description": "Build and test backend services and deliver reliable product features.",
        "required_skills": ["Java", "Data Structures", "SQL", "REST APIs", "Git", "Testing"],
        "selection_process": ["Online assessment", "Technical interview", "HR interview"],
        "company": {
            "name": "TechNova Demo",
            "industry": "Software",
            "about": "A fictional product engineering company used only to demonstrate PlaceAI.",
            "website": "",
        },
    }


def test_demo_dossier_is_comprehensive_without_external_calls(monkeypatch):
    monkeypatch.setattr(
        opportunity_insights,
        "retrieve_evidence",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Demo must not search")),
    )
    monkeypatch.setattr(
        opportunity_insights,
        "call_ai_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Demo must not call AI")),
    )
    guide = opportunity_insights.build_guide(_demo_job())
    content = render_guide(guide)
    reader = PdfReader(BytesIO(content))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert content.startswith(b"%PDF")
    assert 9 <= len(reader.pages) <= 16
    for heading in (
        "Company intelligence",
        "Role decoding",
        "Engineering context and technology stack",
        "Interview history and reported patterns",
        "Technical rehearsal bank",
        "Behavioural interview",
        "HR conversation and role fit",
        "Communication and professional presence",
        "Seven-day preparation plan",
        "Sources and evidence notes",
    ):
        assert heading in text
    assert "Fictional demonstration" in text
    assert "No employer history is claimed" in text


def test_multi_lane_research_keeps_provenance_and_advanced_depth(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily")
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)

    def search(url, **options):
        query = options["json"]["query"]
        if "interview experience" in query:
            results = [{
                "title": "Example Systems Java Developer interview experience",
                "url": "https://interviews.example.org/example-systems-java",
                "content": "Example Systems Java Developer interview questions and technical rounds.",
                "raw_content": "A candidate reported an assessment and technical interview questions.",
                "published_date": "2026-08-01",
            }]
        elif "official company" in query:
            results = [{
                "title": "Example Systems careers",
                "url": "https://example.com/careers",
                "content": "Example Systems products, careers, and engineering teams.",
            }]
        else:
            results = []
        return httpx.Response(
            200,
            request=httpx.Request("POST", "https://api.tavily.com/search"),
            json={"results": results},
        )

    post = Mock(side_effect=search)
    monkeypatch.setattr(opportunity_insights.httpx, "post", post)
    sources, note = opportunity_insights.retrieve_evidence(
        "Example Systems", "Java Developer", "https://example.com"
    )

    assert "2 public sources" in note
    assert [item["id"] for item in sources] == ["S1", "S2"]
    assert [item["kind"] for item in sources] == [
        "Official company source",
        "Public interview account - unverified",
    ]
    assert post.call_count == 4
    payloads = [call.kwargs["json"] for call in post.call_args_list]
    assert sum(payload["search_depth"] == "advanced" for payload in payloads) == 3
    assert all(payload["auto_parameters"] is False for payload in payloads)
    assert all(payload["include_answer"] is False for payload in payloads)
    assert all(payload["include_raw_content"] == "text" for payload in payloads if payload["search_depth"] == "advanced")


def test_model_output_cannot_reference_unknown_sources(monkeypatch):
    baseline = opportunity_insights._baseline(
        "Java Developer",
        "Example Systems",
        ["Java", "SQL", "REST APIs"],
        ["Assessment", "Technical interview", "HR interview"],
        True,
        False,
    )
    payload = baseline.model_dump()
    payload["company_intelligence"][0]["source_ids"] = ["S999"]
    monkeypatch.setattr(opportunity_insights, "call_ai_text", lambda *args, **kwargs: __import__("json").dumps(payload))
    result, tailored = opportunity_insights._model_preparation(
        {
            "role": "Java Developer",
            "company": "Example Systems",
            "description": "Build APIs.",
            "skills": ["Java", "SQL", "REST APIs"],
            "rounds": ["Assessment", "Technical interview", "HR interview"],
            "published_rounds": True,
            "public_evidence": [{"id": "S1"}],
        },
        baseline,
    )
    assert tailored is False
    assert result == baseline

