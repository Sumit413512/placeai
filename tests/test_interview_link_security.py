import pytest
from pydantic import ValidationError

from app.schemas import InterviewScheduleCreate, InterviewScheduleUpdate
from test_browser_smoke import BASE_URL, browser, local_server  # noqa: F401


@pytest.mark.parametrize("value", ["javascript:alert(1)", "data:text/html,unsafe", "file:///tmp/test", "//example.com/meeting",
                                  "https://user:password@example.com/meeting", "java\nscript:alert(1)", "https://example.com/\tmeeting"])
@pytest.mark.parametrize("model", [InterviewScheduleCreate, InterviewScheduleUpdate])
def test_meeting_links_cannot_store_executable_or_credential_urls(value, model):
    data = {"meeting_url": value}
    if model == InterviewScheduleCreate:
        data.update(application_id="isolated-application", round_name="Technical round", scheduled_at="2026-10-15T10:00:00Z")
    with pytest.raises(ValidationError): model(**data)


def test_meeting_link_query_and_optional_clear_are_preserved():
    url = "https://meet.example.com/room?code=abc&passcode=def"
    assert InterviewScheduleUpdate(meeting_url=url).meeting_url == url
    assert InterviewScheduleUpdate(meeting_url="").meeting_url is None
    assert InterviewScheduleUpdate(meeting_url=None).meeting_url is None


def test_legacy_links_are_filtered_by_the_actual_reader(browser):  # noqa: F811
    page = browser.new_page()
    entries = [{"id": str(index), "round_name": title, "meeting_url": url, "status": "scheduled",
                "scheduled_at": "2026-10-15T10:00:00Z", "mode": "online"} for index, (title, url) in enumerate([
                    ("Unsafe legacy meeting", "javascript:alert(1)"),
                    ("Credential-bearing legacy meeting", "https://user:password@example.com/meeting"),
                    ("Valid meeting", "https://meet.example.com/room?code=abc&passcode=def"),
                ])]
    def api(route):
        if route.request.resource_type not in {"fetch", "xhr"}:
            route.continue_(); return
        path = route.request.url.split(BASE_URL)[-1].split("?")[0]
        data = {"items": [], "summary": {}, "actions": []}
        if path == "/auth/refresh": data = {"access_token": "isolated-preview-token"}
        elif path == "/auth/me": data = {"id": "isolated-student", "role": "student", "email": "test@example.invalid", "username": "Test student"}
        elif path in {"/students/applications", "/students/jobs"}: data = []
        elif path == "/billing/status": data = {"student_kind": "university", "premium_access": True, "access_mode": "institution_sponsored"}
        elif path == "/enterprise/interviews": data = entries
        route.fulfill(json=data)
    page.route(BASE_URL + "/**", api)
    page.goto(BASE_URL, wait_until="networkidle")
    page.locator('#app-nav [data-view="interviews"]').click()
    page.get_by_text("Valid meeting", exact=True).wait_for(state="visible")
    links = page.get_by_role("link", name="Join meeting", exact=True)
    assert links.count() == 1
    assert links.get_attribute("href") == entries[-1]["meeting_url"]
    assert page.get_by_text("Unsafe legacy meeting", exact=True).is_visible()
    assert page.get_by_text("Credential-bearing legacy meeting", exact=True).is_visible()
    page.close()
