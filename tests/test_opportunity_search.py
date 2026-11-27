from unittest.mock import Mock

import httpx
import pytest

from app import opportunity_insights


@pytest.fixture(autouse=True)
def clear_search_keys(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)


def test_tavily_uses_one_basic_request_and_filters_sources(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", " test-tavily ")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test-brave")
    post = Mock(return_value=httpx.Response(
        200, request=httpx.Request("POST", "https://api.tavily.com/search"),
        json={"results": [
            {"title": "Example Systems careers", "url": "https://example.com/careers",
             "content": "Example Systems careers and hiring information."},
            {"title": "Example Systems Java developer interview", "url": "https://review.example.org/java",
             "content": "A candidate reported one interview round with technical questions."},
            {"title": "Other Systems Java developer interview", "url": "https://review.example.org/other",
             "content": "A candidate reported one interview round."},
            {"title": "Example Systems analyst interview", "url": "https://review.example.org/analyst",
             "content": "A candidate reported an analyst interview round."},
        ]},
    ))
    brave = Mock(side_effect=AssertionError("Tavily must be the only search provider called."))
    monkeypatch.setattr(opportunity_insights.httpx, "post", post)
    monkeypatch.setattr(opportunity_insights.httpx, "get", brave)

    sources, note = opportunity_insights.retrieve_evidence("Example Systems", "Java Developer", "https://example.com")

    assert not note
    assert [source["kind"] for source in sources] == [
        "Listed company website", "Public interview account (unverified)",
    ]
    assert sources[1]["excerpt"] == "A candidate reported one interview round with technical questions."
    post.assert_called_once()
    assert post.call_args.args == ("https://api.tavily.com/search",)
    options = post.call_args.kwargs
    assert options["headers"]["Authorization"] == "Bearer test-tavily"
    assert options["json"]["search_depth"] == "basic"
    assert options["json"]["auto_parameters"] is False
    assert options["json"]["include_answer"] is False
    assert '"Example Systems" Java Developer' in options["json"]["query"]
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
    post.assert_called_once()
    brave.assert_not_called()


def test_brave_only_configuration_still_reads_descriptions(monkeypatch):
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test-brave")
    get = Mock(return_value=httpx.Response(
        200, request=httpx.Request("GET", "https://api.search.brave.com/res/v1/web/search"),
        json={"web": {"results": [
            {"title": "Example Systems careers", "url": "https://example.com/careers",
             "description": "Example Systems open positions."},
        ]}},
    ))
    monkeypatch.setattr(opportunity_insights.httpx, "get", get)

    sources, note = opportunity_insights.retrieve_evidence("Example Systems", "Java Developer", "https://example.com")

    assert not note
    assert sources[0]["excerpt"] == "Example Systems open positions."
    get.assert_called_once()
