from fastapi.testclient import TestClient
from app.app import app

client = TestClient(app)


def test_browser_404_preserves_status_without_changing_api_errors():
    response = client.get("/unknown-launch-page", headers={"Accept": "text/html"})
    assert response.status_code == 404
    assert "Let’s get you back" in response.text
    assert response.headers["x-robots-tag"] == "noindex"
    assert client.get("/unknown-launch-page").json() == {"detail": "Not Found"}
    assert client.get("/auth/me").status_code == 401


def test_sharing_metadata_never_contains_private_report_query():
    response = client.get("/mock-interview?result=private-assessment-reference")
    assert 'content="noindex, nofollow"' in response.text
    assert 'href="https://www.placeai.in/mock-interview"' in response.text
    assert "private-assessment-reference" not in response.text
    homepage = client.get("/").text
    assert 'property="og:image"' in homepage
    assert homepage.count("/static/privacy-preferences.js") == 1


def test_static_crawler_documents_match_backend_routes():
    from pathlib import Path

    public = Path(__file__).resolve().parents[1] / "public"
    with TestClient(app, base_url="https://www.placeai.in") as canonical_client:
        for name in ("robots.txt", "sitemap.xml"):
            assert canonical_client.get("/" + name).text == (public / name).read_text(encoding="utf-8")
