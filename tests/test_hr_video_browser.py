"""Browser regression checks with synthetic media and stubbed provider responses."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from test_browser_smoke import BASE_URL, ROOT, browser, local_server  # noqa: F401


def test_saved_pending_attempt_never_hijacks_lab_entry_and_history_does_not_retry(browser):
    page = browser.new_page()
    requests = []
    page.add_init_script("sessionStorage.setItem('placeai-assessment-result:student', 'saved')")
    page.route("**/auth/refresh", lambda route: route.fulfill(json={"access_token": "test-token"}))
    page.route("**/auth/me", lambda route: route.fulfill(json={"id": "student", "role": "student"}))
    page.route("**/mock-interview/jobs", lambda route: route.fulfill(json=[]))
    page.route("**/mock-interview/history", lambda route: route.fulfill(json=[{
        "id": "saved", "job_title": "Analyst", "overall_score": None, "analysis_status": "pending"}]))
    def pending(route):
        requests.append(route.request.method)
        route.fulfill(json={"status": "pending", "queued": False})
    page.route("**/mock-interview/saved/result", pending)
    page.route("**/mock-interview/saved/retry", lambda route: requests.append("UNEXPECTED_RETRY"))
    page.goto(f"{BASE_URL}/mock-interview", wait_until="domcontentloaded")
    page.locator('[data-saved-result="saved"]').wait_for()
    assert page.locator("#setup-panel").is_visible()
    assert page.locator("#analysis-panel").is_hidden()
    assert requests == []
    page.locator('[data-saved-result="saved"]').click()
    page.locator("#retry-analysis").wait_for(state="visible")
    assert requests == ["GET"]
    assert "report is pending" in page.locator("#analysis-message").inner_text()
    assert page.locator(".analysis-step.done").count() == 0
    page.locator("#return-to-setup").click()
    assert page.locator("#setup-panel").is_visible()
    assert page.locator("#analysis-panel").is_hidden()
    page.locator('[data-saved-result="saved"]').click()
    page.locator("#retry-analysis").wait_for(state="visible")
    page.route("**/mock-interview/saved/retry", lambda route: route.fulfill(json={"queued": True}, status=202))
    page.clock.install()
    page.locator("#retry-analysis").click()
    page.wait_for_function("() => document.querySelector('#analysis-message').textContent.includes('saved securely')")
    page.locator("#return-to-setup").click()
    prior_reads = len(requests)
    page.clock.fast_forward(15000)
    assert page.locator("#setup-panel").is_visible()
    assert page.locator("#analysis-panel").is_hidden()
    assert len(requests) == prior_reads
    page.close()


def test_continuous_hr_video_auto_submits_and_withholds_partial_results(browser):
    page = browser.new_page()
    script = (ROOT / "app/static/mock-interview.js").read_text(encoding="utf-8")
    # Test-only access to the existing controller; no production test hook is shipped.
    script = script.rsplit("})();", 1)[0] + "window.hrTest={state,renderQuestion,startTimer};})();"
    page.route("**/static/mock-interview.js*", lambda route: route.fulfill(body=script, content_type="application/javascript"))
    page.route("**/auth/refresh", lambda route: route.fulfill(json={"access_token": "test-token"}))
    page.route("**/auth/me", lambda route: route.fulfill(json={"id": "synthetic-student", "role": "student"}))
    page.route("**/mock-interview/jobs", lambda route: route.fulfill(body="[]", content_type="application/json"))
    page.route("**/mock-interview/history", lambda route: route.fulfill(body="[]", content_type="application/json"))
    events, chunks, ready = [], [], {"value": False}

    def clock(status="recording"):
        now = datetime.now(timezone.utc)
        return {"status": status, "chunk_count": 0, "server_time": now.isoformat(),
                "question_deadline_at": (now + timedelta(seconds=150)).isoformat(),
                "deadline_at": (now + timedelta(seconds=600)).isoformat(), "max_bytes": 28 * 1024 * 1024}

    def api(route):
        path = route.request.url.split(BASE_URL)[-1]
        events.append(path)
        if path.endswith("/start"):
            assert route.request.post_data_json["consent"] is True
            route.fulfill(json=clock())
        elif "/chunks/" in path:
            chunks.append(route.request.post_data_buffer)
            route.fulfill(json={"saved": True})
        elif path.endswith("/advance"):
            qid = route.request.post_data_json["question_id"]
            route.fulfill(json=clock("recorded" if qid == 4 else "recording"))
        elif path.endswith("/submit"):
            assert route.request.post_data_json["chunks"] == len(chunks)
            assert chunks and b"".join(chunks).startswith(b"\x1a\x45\xdf\xa3")
            route.fulfill(json=clock("submitted"))
        elif path.endswith("/result"):
            route.fulfill(json={"status": "pending", "result": None})
        elif path.endswith("/recording"):
            video = b"".join(chunks)
            route.fulfill(body=video, content_type="video/webm", status=206,
                          headers={"Content-Range": f"bytes 0-{len(video)-1}/{len(video)}"})
        elif path.endswith("/retry") and ready["value"]:
            route.fulfill(json={"analysis_status": "complete", "overall_score": 78,
                                "overall_feedback": "Complete report", "evaluations": [],
                                "hr_video": {"summary": "Clear examples; practice shorter conclusions.",
                                             "retention_days": 30, "mime_type": "video/webm",
                                             "size_bytes": sum(map(len, chunks)),
                                             "recording_url": "/mock-interview/synthetic/hr/recording"}})
        else:
            route.fulfill(status=503, json={"detail": "Your exam is saved. Analysis is pending."})

    page.route("**/mock-interview/synthetic/hr/**", api)
    page.route("**/mock-interview/synthetic/result", api)
    page.route("**/mock-interview/synthetic/retry", api)
    page.route("**/mock-interview/evaluate", api)
    page.goto(f"{BASE_URL}/mock-interview", wait_until="domcontentloaded")
    page.wait_for_function("() => window.hrTest && window.hrTest.state.me")
    page.evaluate("""() => {
        const canvas=document.createElement('canvas');canvas.width=160;canvas.height=120;
        const context=canvas.getContext('2d');let frame=0;
        window.syntheticTimer=setInterval(()=>{context.fillStyle=frame++%2?'blue':'green';context.fillRect(0,0,160,120);},50);
        const audio=new AudioContext();const oscillator=audio.createOscillator();
        const output=audio.createMediaStreamDestination();oscillator.connect(output);oscillator.start();
        window.syntheticAudio=audio;
        const stream=canvas.captureStream(10);stream.addTrack(output.stream.getAudioTracks()[0]);
        const s=hrTest.state;s.mediaStream=stream;s.session={interview_id:'synthetic'};
        s.questions=[1,2,3,4].map(id=>({question_id:id,question:'Describe example '+id,section:'behavioral',answer_type:'video'}));
        s.answers=new Array(4);s.assessmentActive=true;s.examDeadline=Date.now()+600000;
        document.querySelector('#consent-check').checked=true;
        document.querySelector('#interview-panel').classList.remove('hidden');
        hrTest.renderQuestion();hrTest.startTimer();
    }""")
    assert "/mock-interview/synthetic/hr/start" not in events
    assert page.locator("#hr-answer-preview").is_visible()
    assert page.locator("#next-question").is_disabled()
    page.locator("#start-hr-recording").click()
    page.wait_for_function("() => hrTest.state.hr?.recorder?.state === 'recording'")
    page.wait_for_function("() => hrTest.state.hr.chunks.length > 0")
    assert page.locator("#repeat-hr-question").is_disabled()
    page.evaluate("window.firstRecorder=hrTest.state.hr.recorder")
    for question in range(4):
        page.wait_for_function("q=>hrTest.state.current===q && !hrTest.state.hr.transitioning", arg=question)
        assert page.evaluate("hrTest.state.hr.recorder === window.firstRecorder")
        page.evaluate("hrTest.state.hr.questionDeadline=Date.now()-1")
        if question < 3:
            page.wait_for_function("q=>hrTest.state.current===q+1", arg=question)
    page.locator("#analysis-panel").wait_for(state="visible")
    page.wait_for_function("() => hrTest.state.hr.submitted")
    assert page.locator("#result-panel").is_hidden()
    assert events.count("/mock-interview/synthetic/hr/start") == 1
    assert events.count("/mock-interview/synthetic/hr/submit") == 1
    assert len([e for e in events if e.endswith("/advance")]) == 4
    ready["value"] = True
    page.locator("#result-panel").wait_for(state="visible", timeout=30000)
    assert page.locator("#overall-score").inner_text() == "78"
    assert page.locator("#hr-video-report").is_visible()
    page.locator("#load-hr-recording").click()
    page.locator("#hr-result-video").wait_for(state="visible")
    assert page.locator("#hr-result-video").get_attribute("src").startswith("blob:")
    assert page.evaluate("hrTest.state.hr.recorder.state") == "inactive"
    page.evaluate("clearInterval(window.syntheticTimer);window.syntheticAudio.close()")
    page.close()


def test_google_sign_in_uses_selected_role_and_password_link_challenge(browser):
    page = browser.new_page()
    page.route("**/auth/google-config", lambda route: route.fulfill(json={
        "enabled": True, "client_id": "test.apps.googleusercontent.com", "nonce": "test-nonce"}))
    page.route("https://accounts.google.com/gsi/client", lambda route: route.fulfill(
        content_type="application/javascript", body="""
        window.google={accounts:{id:{initialize(config){window.googleConfig=config;},renderButton(area, options){window.googleButtonWidth=options.width;
          const button=document.createElement('button');button.textContent='Test Google sign-in';
          button.onclick=()=>window.googleConfig.callback({credential:'synthetic-google-token'});area.append(button);
        }}}};"""))
    calls = []

    def login(route):
        calls.append(route.request.post_data_json)
        route.fulfill(status=409, json={"detail": "Confirm your existing PlaceAI password to link this account.",
                                      "code": "GOOGLE_LINK_PASSWORD_REQUIRED"})

    page.route("**/auth/google", login)
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.locator('.hero button[data-open-auth="login"]').click()
    page.locator('#login-view [data-access-role="institution_admin"]').click()
    page.get_by_text("Test Google sign-in", exact=True).wait_for(state="visible")
    page.evaluate("async () => { await document.fonts.ready; }")
    # Measure one layout frame: role selection can scroll the dialog and load
    # fonts between two separate browser calls, producing a false inversion.
    google_box, email_box = page.evaluate("""() => [
        document.querySelector('.google-sign-in button').getBoundingClientRect().toJSON(),
        document.querySelector('#role-login-form [name="email"]').getBoundingClientRect().toJSON()
    ]""")
    assert google_box["y"] < email_box["y"]
    for width in (390, 320, 1440):
        page.set_viewport_size({"width": width, "height": 900})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.wait_for_function("() => googleButtonWidth <= document.querySelector('.google-sign-in').clientWidth")
        cards = page.locator('#login-view .access-role-card')
        assert cards.nth(0).bounding_box()["y"] == cards.nth(1).bounding_box()["y"]
    page.get_by_text("Test Google sign-in", exact=True).click()
    page.get_by_text("Link Google account and sign in", exact=True).wait_for()
    assert calls[-1]["role"] == "institution_admin"
    assert page.evaluate("googleConfig.nonce") == "test-nonce"
    page.locator('#role-login-form [name="password"]').fill("Synthetic#Password123")
    page.get_by_text("Link Google account and sign in", exact=True).click()
    page.wait_for_function("() => document.querySelector('.google-sign-in button')?.textContent.includes('Link')")
    assert calls[-1]["password"] == "Synthetic#Password123"
    page.close()
