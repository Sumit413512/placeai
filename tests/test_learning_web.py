from types import SimpleNamespace

import httpx
import pytest

from app import learning_ai, learning_web


def test_public_reference_validation_blocks_private_and_unapproved_targets(monkeypatch):
    monkeypatch.setattr(learning_web.socket, "getaddrinfo", lambda *_args, **_kw: [(2, 1, 6, "", ("93.184.216.34", 443))])
    assert learning_web.validate_url("https://www.postgresql.org/docs/current/sql-select.html")
    for url in ["http://www.postgresql.org/docs/", "https://localhost/", "https://127.0.0.1/",
                "https://www.postgresql.org.attacker.invalid/", "https://user:secret@www.postgresql.org/",
                "https://www.postgresql.org:8443/", "https://www.postgresql.org/?user=private"]:
        with pytest.raises(ValueError): learning_web.validate_url(url)
    monkeypatch.setattr(learning_web.socket, "getaddrinfo", lambda *_args, **_kw: [(2, 1, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(ValueError): learning_web.validate_url("https://www.postgresql.org/")


def test_document_parser_keeps_teaching_and_removes_scripts_navigation_and_footer():
    parser = learning_web.DocumentText()
    parser.feed("<html><head><title>SQL reference</title><script>secret navigation script</script></head>"
                "<body><nav>Unrelated navigation</nav><main><h1>SELECT</h1><p>Read rows.</p>"
                "<pre>SELECT name FROM students;</pre></main><footer>Advertising footer</footer></body></html>")
    text = "".join(parser.parts)
    assert "SELECT name FROM students;" in text
    assert "SQL reference" == "".join(parser.title_parts)
    assert "secret" not in text and "navigation" not in text and "Advertising" not in text


def test_research_cites_only_fetched_documents_and_refuses_insufficient_evidence(monkeypatch):
    urls = ["https://www.postgresql.org/docs/current/" + page for page in ["tutorial.html", "queries.html", "sql-select.html", "invented-page.html"]]
    def fetch(url):
        if url.endswith("invented-page.html"): raise httpx.HTTPError("Not found")
        return {"url": url, "title": "Official SQL teaching"}, "A live verified educational excerpt. " * 30
    monkeypatch.setattr(learning_web, "fetch_document", fetch)
    memo, sources, model = learning_web.research_documents("SQL", lambda *_args, **_kwargs: ({"urls": urls}, "gemini:test"))
    assert 3 <= len(sources) <= 5 and "LIVE REFERENCE 3" in memo
    assert all(not source["url"].endswith("invented-page.html") for source in sources)
    assert model == "verified-web:gemini:test"
    monkeypatch.setattr(learning_web, "fetch_document", lambda _: (_ for _ in ()).throw(httpx.HTTPError("Unavailable")))
    with pytest.raises(RuntimeError):
        learning_web.research_documents("SQL", lambda *_args, **_kwargs: ({"urls": urls[-2:]}, "gemini:test"))


def test_gemini_writer_uses_learning_model_without_changing_other_ai_features(monkeypatch):
    monkeypatch.setenv("LEARNING_GEMINI_MODEL", "gemini-3.5-flash-lite")
    monkeypatch.setattr(learning_ai.ai_provider, "_openai_keys", lambda: [])
    monkeypatch.setattr(learning_ai.ai_provider, "_gemini_key", lambda: "isolated-test-key")
    requests = []
    def generate(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(text='{"title":"SQL"}')
    monkeypatch.setattr(learning_ai.ai_provider, "genai", SimpleNamespace(Client=lambda **_kwargs: SimpleNamespace(models=SimpleNamespace(generate_content=generate))))
    original = learning_ai.get_settings().gemini_model
    data, model = learning_ai.generate_json("Teach SQL", {"type": "object"}, max_output_tokens=1200)
    assert data == {"title": "SQL"} and model == "gemini:gemini-3.5-flash-lite"
    assert requests[0]["config"].response_mime_type == "application/json"
    assert requests[0]["config"].max_output_tokens == 1200
    assert requests[0]["config"].response_json_schema == {"type": "object"}
    assert learning_ai.get_settings().gemini_model == original


def test_schema_transport_fallback_keeps_the_full_validation_contract_in_prompt(monkeypatch):
    monkeypatch.setattr(learning_ai.ai_provider, '_openai_keys', lambda: [])
    monkeypatch.setattr(learning_ai.ai_provider, '_gemini_key', lambda: 'isolated-test-key')
    schema = {'type': 'object', 'properties': {'explanation': {'type': 'string', 'minLength': 1600}},
              'required': ['explanation'], 'additionalProperties': False}
    calls = []
    def generate(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            response = httpx.Response(400, request=httpx.Request('POST', 'https://provider.invalid/'))
            raise httpx.HTTPStatusError('Unsupported schema grammar', request=response.request, response=response)
        return SimpleNamespace(text='{"explanation":"Draft requiring application validation"}')
    monkeypatch.setattr(learning_ai.ai_provider, 'genai', SimpleNamespace(Client=lambda **_: SimpleNamespace(models=SimpleNamespace(generate_content=generate))))
    result, _ = learning_ai.generate_json('Write teaching material', schema)
    assert result['explanation']
    assert '1600' in calls[0]['contents'] and '1600' in calls[1]['contents']
    assert 'minLength' not in calls[0]['config'].response_json_schema['properties']['explanation']
    assert calls[1]['config'].response_json_schema is None
    assert schema['properties']['explanation']['minLength'] == 1600
    shape = learning_ai.provider_schema({'type': 'object', 'title': 'Metadata', 'properties': {
        'title': {'type': 'string', 'minLength': 3}, 'description': {'type': 'string'}},
        'required': ['title', 'description']})
    assert set(shape['properties']) == {'title', 'description'} and 'title' not in shape


def test_rate_limit_is_distinct_from_invalid_content_and_does_not_loop(monkeypatch):
    monkeypatch.setattr(learning_ai.ai_provider, '_openai_keys', lambda: [])
    monkeypatch.setattr(learning_ai.ai_provider, '_gemini_key', lambda: 'isolated-test-key')
    calls = []
    def limited(**kwargs):
        calls.append(kwargs)
        response = httpx.Response(429, request=httpx.Request('POST', 'https://provider.invalid/'))
        raise httpx.HTTPStatusError('Quota unavailable', request=response.request, response=response)
    monkeypatch.setattr(learning_ai.ai_provider, 'genai', SimpleNamespace(Client=lambda **_: SimpleNamespace(models=SimpleNamespace(generate_content=limited))))
    with pytest.raises(learning_ai.LearningCapacityError) as error:
        learning_ai.generate_json('Teach SQL', {'type': 'object'})
    assert len(calls) == 1 and error.value.retry_seconds >= 3600
