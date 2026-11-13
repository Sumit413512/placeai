"""Browser regression: platform staff must actually load private MP4s via bearer auth.

Synthetic media and an isolated mocked admin session avoid using real accounts,
production user data, or paid AI providers.
"""
from io import BytesIO

import av
from PIL import Image
from playwright.sync_api import expect

from test_browser_smoke import BASE_URL, browser, local_server  # noqa: F401


def _sample_mp4():
    output = BytesIO()
    with av.open(output, mode="w", format="mp4") as container:
        stream = container.add_stream("libx264", rate=12)
        stream.width = stream.height = 64
        stream.pix_fmt = "yuv420p"
        for i in range(24):
            frame = av.VideoFrame.from_image(Image.new("RGB", (64, 64), (40 + i * 3, 75, 95)))
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return output.getvalue()


def test_platform_admin_preview_uses_authenticated_byte_ranges(browser):
    media = _sample_mp4()
    assert media[:4] != b"" and len(media) > 500
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    seen_requests = []

    def respond(route):
        request = route.request
        if request.resource_type not in {"fetch", "xhr"}:
            route.continue_()
            return
        path = request.url.split(BASE_URL)[-1].split("?")[0]
        authorization = request.headers.get("authorization", "")
        if path == "/auth/me":
            if authorization != "Bearer isolated-admin-video-token":
                route.fulfill(status=401, json={"detail": "Sign in"})
                return
            data = {"id": "test-admin", "username": "Test admin", "email": "test@example.invalid",
                    "role": "platform_admin"}
        elif path == "/platform/learning-content-review":
            data = {"items": [{"kind": "course", "id": "test-course",
                     "title": "Sample course", "parent_title": None,
                     "generation_status": "ready", "editorial_status": "pending_review",
                     "review_ready": True, "checked_count": 1, "planned_count": 1,
                     "updated_at": "2026-11-12T09:00:00"}], "pending_count": 1}
        elif path == "/platform/learning-content-review/course/test-course":
            data = {"id": "test-course", "title": "Sample course",
                    "editorial_status": "pending_review", "plan": {"lessons": [{}]},
                    "sources": [], "planned_count": 1, "ready_count": 1,
                    "lessons": [{"id": "test-lesson", "position": 0, "title": "CSS rules",
                                 "generation_status": "ready", "editorial_status": "pending_review",
                                 "media_available": True, "duration_seconds": 2,
                                 "content": {"objective": "Understand style rules",
                                             "content_review": {"passed": True},
                                             "media_review": {"passed": True},
                                             "audiovisual_review": {"passed": True}}}]}
        elif path == "/platform/learning-content-review/lesson/test-lesson/media":
            seen_requests.append({"auth": authorization, "range": request.headers.get("range")})
            if authorization != "Bearer isolated-admin-video-token":
                route.fulfill(status=401, json={"detail": "Authentication required"})
                return
            value = request.headers.get("range", "")
            import re
            parsed = re.fullmatch(r"bytes=(\d+)-(\d+)", value)
            if not parsed:
                route.fulfill(status=416)
                return
            start, last = map(int, parsed.groups())
            end = min(last, len(media) - 1)
            route.fulfill(status=206, body=media[start:end + 1],
                          headers={"Content-Type": "video/mp4", "Accept-Ranges": "bytes",
                                   "Content-Range": f"bytes {start}-{end}/{len(media)}",
                                   "Cache-Control": "private, no-store",
                                   "Content-Length": str(end - start + 1)})
            return
        elif path == "/auth/refresh":
            route.fulfill(status=401, json={"detail": "No refresh"})
            return
        elif path == "/platform/overview":
            data = {"organizations": 0, "students": 0, "recruiters": 0,
                    "institution_admins": 0, "active_jobs": 0,
                    "applications": 0, "access_requests": 0}
        elif path == "/enterprise/notifications":
            data = {"items": [], "unread": 0}
        else:
            data = {"items": [], "summary": {}, "actions": []}
        route.fulfill(json=data)

    page.route(BASE_URL + "/**", respond)
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.wait_for_function("Boolean(window.PlaceAIAuth?.completeSignIn)")
    page.evaluate("""async () => {
        await window.PlaceAIAuth.completeSignIn({access_token: 'isolated-admin-video-token'});
    }""")
    expect(page.locator("#app-shell")).to_be_visible()
    page.locator('#app-nav [data-view="content-review"]').click()
    page.get_by_role("button", name="Review full course").click()
    preview = page.locator('video[data-learning-video-preview="test-lesson"]')
    expect(preview).to_be_visible()
    assert not preview.get_attribute("src")
    page.get_by_role("button", name="Load and play video").click()
    page.wait_for_function("""() => {
        const node = document.querySelector('video[data-learning-video-preview="test-lesson"]');
        return node?.getAttribute('src')?.startsWith('blob:');
    }""")
    assert seen_requests
    assert all(req["auth"] == "Bearer isolated-admin-video-token"
               and req["range"].startswith("bytes=") for req in seen_requests)
    assert preview.get_attribute("src").startswith("blob:")
    if page.evaluate("""() => Boolean(document.createElement('video')
              .canPlayType('video/mp4; codecs="avc1.42E01E"'))"""):
        page.wait_for_function("""() => document.querySelector(
          'video[data-learning-video-preview="test-lesson"]').videoWidth === 64""", timeout=15000)
    page.locator('#generic-modal-cancel').click()
    page.wait_for_function("""() => !document.querySelector(
          'video[data-learning-video-preview="test-lesson"]')""")
    context.close()
