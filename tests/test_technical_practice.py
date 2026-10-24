"""Retired standalone practice must not remain reachable."""
from pathlib import Path
from fastapi.testclient import TestClient
from app.app import app


def test_standalone_technical_practice_is_removed():
    client=TestClient(app)
    for path in ['/technical-practice','/technical-practice/anything','/static/technical-practice.js','/static/technical-practice.css']:
        assert client.get(path).status_code == 404
    assert client.post('/technical-practice/start',json={}).status_code == 404
    root=Path(__file__).resolve().parents[1]
    for name in ['app/static/app.js','public/static/app-core.js','app/templates/index.html','public/index.html','app/templates/mock-interview.html']:
        source=(root/name).read_text(encoding='utf8')
        assert 'view=technical-practice' not in source and '/static/technical-practice.' not in source
    assert 'Technical practice' not in (root/'app/static/app.js').read_text(encoding='utf8')
