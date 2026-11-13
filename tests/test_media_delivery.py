from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.media_delivery import private_media_response


def client_for(data=b"0123456789"):
    app = FastAPI()

    @app.get("/video")
    def video(request: Request):
        return private_media_response(data, request)

    return TestClient(app)


def test_private_media_supports_browser_byte_ranges():
    with client_for() as client:
        response = client.get("/video", headers={"Range": "bytes=2-5"})
        assert response.status_code == 206
        assert response.content == b"2345"
        assert response.headers["content-range"] == "bytes 2-5/10"
        assert response.headers["accept-ranges"] == "bytes"
        assert response.headers["content-length"] == "4"
        assert response.headers["cache-control"] == "private, no-store"


def test_private_media_supports_suffix_and_rejects_invalid_ranges():
    with client_for() as client:
        suffix = client.get("/video", headers={"Range": "bytes=-3"})
        assert suffix.status_code == 206 and suffix.content == b"789"
        invalid = client.get("/video", headers={"Range": "bytes=20-30"})
        assert invalid.status_code == 416
        assert invalid.headers["content-range"] == "bytes */10"


def test_private_media_full_response_is_seekable():
    with client_for() as client:
        response = client.get("/video")
        assert response.status_code == 200 and response.content == b"0123456789"
        assert response.headers["accept-ranges"] == "bytes"
        assert response.headers["content-length"] == "10"



def test_admin_video_preview_never_uses_unauthenticated_native_media_src():
    """The staff preview must use api() to attach its private Bearer token.

    This is the frontend/backend contract that previously caused MP4 playback
    to fail despite a valid admin session.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    app = (root / "app/static/app.js").read_text(encoding="utf-8")
    mirrored = (root / "public/static/app-core.js").read_text(encoding="utf-8")
    assert app == mirrored
    assert "async function loadLearningVideoPreview(id, button)" in app
    assert "await api(url,{headers:{Range:" in app
    assert "data-action=\"load-learning-video-preview\"" in app
    assert "releaseLearningVideoPreview();" in app
    assert 'src="/platform/learning-content-review/lesson/' not in app


def test_platform_review_distinguishes_AI_checks_from_human_approval():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    app = (root / 'app/static/app.js').read_text(encoding='utf-8')
    mirror = (root / 'public/static/app-core.js').read_text(encoding='utf-8')
    assert app == mirror
    assert 'Independent video review pending' in app
    assert 'Human approval needed' in app
    assert 'Provider capacity / generation retry' in app
    assert "?'Checks passed':'Check required'" not in app
