from unittest.mock import Mock

import httpx
import pytest

from app import opportunity_insights


@pytest.fixture(autouse=True)
def clear_search_keys(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)


def _rows_for_query(query: str, text_key: str) -> list[dict]:
    if "official company" in query:
        return [{
            "title": "Example Systems careers",
            "url": "https://example.com/careers",
            text_key: "Example Systems careers and hiring information.",
        }]
    if "interview experience" in query:
        return [{
            "title": "Example Systems Java Developer interview",
            "url": "https://review.example.org/java",
            text_key: "Example Systems Java Developer interview experience with technical questions and rounds.",
        }]
    return []


def test_tavily_runs_multi_lane_research_and_filters_sources(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", " test-tavily ")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test-brave")

    def reply(url, **options):
        rows = _rows_for_query(options["json"]["query"], "content")
        for row in rows:
            if options["json"]["search_depth"] == "advanced":
                row["raw_content"] = row["content"]
        return httpx.Response(200, request=httpx.Request("POST", url), json={"results": rows})

    post = Mock(side_effect=reply)
    brave = Mock(side_effect=AssertionError("Tavily must be the only search provider called."))
    monkeypatch.setattr(opportunity_insights.httpx, "post", post)
    monkeypatch.setattr(opportunity_insights.httpx, "get", brave)

    sources, note = opportunity_insights.retrieve_evidence(
        "Example Systems", "Java Developer", "https://example.com"
    )

    assert "2 public sources" in note
    assert [source["kind"] for source in sources] == [
        "Official company source", "Public interview account - unverified",
    ]
    assert [source["id"] for source in sources] == ["S1", "S2"]
    assert post.call_count == 4
    payloads = [call.kwargs["json"] for call in post.call_args_list]
    assert sum(payload["search_depth"] == "advanced" for payload in payloads) == 3
    assert all(payload["auto_parameters"] is False for payload in payloads)
    assert all(payload["include_answer"] is False for payload in payloads)
    brave.assert_not_called()


@pytest.mark.parametrize("status,payload", [(429, {}), (200, {"results": None})])
def test_tavily_failure_returns_unavailable_without_spending_brave_credit(monkeypatch, status, payload):
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test-brave")
    post = Mock(return_value=httpx.Response(
        status, request=httpx.Request("POST", "https://api.tavily.com/search"), json=payload,
    ))
    brave = Mock(side_effect=AssertionError("Search must not fall through to a second provider."))
    monkeypatch.setattr(opportunity_insights.httpx, "post", post)
    monkeypatch.setattr(opportunity_insights.httpx, "get", brave)

    sources, note = opportunity_insights.retrieve_evidence("Example Systems", "Java Developer", "")

    assert not sources
    assert "temporarily unavailable" in note
    assert post.call_count == 4
    brave.assert_not_called()


def test_brave_only_configuration_runs_same_research_lanes(monkeypatch):
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test-brave")

    def reply(url, **options):
        rows = _rows_for_query(options["params"]["q"], "description")
        return httpx.Response(200, request=httpx.Request("GET", url), json={"web": {"results": rows}})

    get = Mock(side_effect=reply)
    monkeypatch.setattr(opportunity_insights.httpx, "get", get)

    sources, note = opportunity_insights.retrieve_evidence(
        "Example Systems", "Java Developer", "https://example.com"
    )

    assert "2 public sources" in note
    assert sources[0]["excerpt"] == "Example Systems careers and hiring information."
    assert get.call_count == 4

