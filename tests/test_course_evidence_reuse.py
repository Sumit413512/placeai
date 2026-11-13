"""Source-grounded research reuse for fast course preparation without extra AI quota."""
import pytest

from app import learning_ai


def _course():
    pages = [
        ("Python Lists", "https://docs.python.org/3/tutorial/datastructures.html",
         "Python list comprehensions filter list values with an expression. "
         "A list comprehension consists of brackets containing an expression followed by a for clause. "
         "Python lists contain elements. List comprehensions can contain for and if clauses. " * 13),
        ("Go Slices", "https://go.dev/blog/slices-intro",
         "Go slices are views of underlying arrays, with length and capacity. "
         "Reslicing a slice creates a new slice descriptor pointing to an underlying array. "
         "Appending may allocate a new backing array. " * 16),
        ("MDN Map", "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Map",
         "JavaScript Map holds keyed collections of values with unique keys and insertion order. "
         "Map provides get set delete and has. " * 18),
    ]
    evidence = "\n\n".join(
        f"LIVE REFERENCE {index}: {title}\nURL: {url}\nEXCERPT:\n{body}"
        for index, (title, url, body) in enumerate(pages, 1))
    sources = [{"title": title, "url": url} for title, url, _ in pages]
    return evidence, sources


def test_cited_course_research_is_reused_with_short_topic_specific_passages():
    evidence, sources = _course()
    original_bytes = len(evidence)
    result = learning_ai.reusable_course_research(
        evidence, sources,
        {"title": "Slice Internals and Reslicing",
         "objective": "Explain slice capacity and re-slicing using Go arrays",
         "module_title": "Slices and Vectors"})
    assert result is not None
    memo, selected, provenance = result
    assert provenance == "course-evidence-cache"
    assert len(memo) < original_bytes
    assert len(memo) <= 13500
    assert selected[0]["url"] == "https://go.dev/blog/slices-intro"
    assert "capacity" in memo
    assert "URL: https://" in memo
    assert "OFFICIAL SOURCE 1:" in memo
    assert "new and fabricated" not in memo


def test_cited_course_research_fails_closed_without_relevance_or_source_integrity():
    evidence, sources = _course()
    unrelated = {"title":"Quantum entanglement in spin systems",
                 "objective":"Explain a Bell state measurement and entangled photons"}
    assert learning_ai.reusable_course_research(evidence, sources, unrelated) is None
    assert learning_ai.reusable_course_research(evidence, sources[:1], unrelated) is None
    assert learning_ai.reusable_course_research("short", sources, unrelated) is None
    polluted = [{"title":"malicious","url":"file:///tmp/stolen"}] + sources[1:]
    assert all(source["url"].startswith("https://") for source in
               learning_ai.reusable_course_research(
                   evidence, polluted,
                   {"title": "Slice Internals and Reslicing",
                    "objective": "Explain slice capacity in Go arrays"})[1])


def test_course_evidence_reuse_never_requires_a_provider_api_key(monkeypatch):
    evidence, sources = _course()
    monkeypatch.setattr(learning_ai.ai_provider,"_gemini_key",
                        lambda: pytest.fail("Should not invoke Gemini"))
    monkeypatch.setattr(learning_ai.ai_provider,"_openai_keys",
                        lambda: pytest.fail("Should not invoke OpenAI"))
    assert learning_ai.reusable_course_research(
        evidence,sources,
        {"title":"Python list comprehensions",
         "objective":"Use filtering in a Python list comprehension",
         "module_title":"Lists"}) is not None
