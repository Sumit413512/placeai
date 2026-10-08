from datetime import datetime, timedelta, timezone

from test_browser_smoke import BASE_URL, ROOT, browser, local_server  # noqa: F401


def test_question_reading_precedes_separate_audio_and_video_and_capacity_stops_retry(browser):  # noqa: F811
    page = browser.new_page()
    script = (ROOT / "app/static/mock-interview.js").read_text(encoding="utf-8")
    script = script.rsplit("})();", 1)[0] + "window.questionTest={state,renderQuestion,submitAndContinue,finishAssessment};})();"
    page.route("**/static/mock-interview.js*", lambda route: route.fulfill(body=script, content_type="application/javascript"))
    page.route("**/auth/refresh", lambda route: route.fulfill(json={"access_token": "test-token"}))
    page.route("**/auth/me", lambda route: route.fulfill(json={"id": "synthetic", "role": "student"}))
    page.route("**/mock-interview/jobs", lambda route: route.fulfill(json=[]))
    page.route("**/mock-interview/history", lambda route: route.fulfill(json=[]))
    page.route("**/mock-interview/clip-test/result", lambda route: route.fulfill(json={"status": "pending"}))
    events, clips, evaluations = [], {}, []
    def recording(route):
        path = route.request.url.split(BASE_URL)[-1]
        events.append(path)
        qid = int(path.split("/answers/")[1].split("/")[0])
        if path.endswith("/start"):
            assert route.request.post_data_json["mime_type"] == ("audio/webm" if qid == 1 else "video/webm")
            now = datetime.now(timezone.utc)
            seconds = {1: 120, 2: 90, 3: 120}[qid]
            route.fulfill(json={"status": "recording", "server_time": now.isoformat(),
                                "question_deadline_at": (now + timedelta(seconds=seconds)).isoformat(), "max_bytes": 7*1024*1024})
        elif "/chunks/" in path:
            clips.setdefault(qid, []).append(route.request.post_data_buffer)
            route.fulfill(json={"saved": True})
        else:
            assert route.request.post_data_json["chunks"] == len(clips[qid])
            route.fulfill(json={"status": "submitted"})
    def evaluate(route):
        evaluations.append(route.request.post_data_json)
        route.fulfill(status=503, json={"detail": {"code": "VIDEO_PROVIDER_CAPACITY", "message": "Your exam and recording are saved. Analysis capacity is unavailable."}})
    page.route("**/mock-interview/clip-test/answers/**", recording)
    page.route("**/mock-interview/evaluate", evaluate)
    page.goto(f"{BASE_URL}/mock-interview", wait_until="domcontentloaded")
    page.wait_for_function("() => questionTest.state.me")
    page.evaluate("""() => {
      window.readings=[];
      window.SpeechSynthesisUtterance=class {constructor(text){this.text=text;}};
      Object.defineProperty(window,'speechSynthesis',{value:{cancel(){},speak(u){readings.push(u.text);setTimeout(()=>u.onend(),5);}}});
      const canvas=document.createElement('canvas');canvas.width=160;canvas.height=120;
      const context=canvas.getContext('2d');let frame=0;
      window.paint=setInterval(()=>{context.fillStyle=frame++%2?'blue':'green';context.fillRect(0,0,160,120);},30);
      const audio=new AudioContext(),osc=audio.createOscillator(),gain=audio.createGain(),out=audio.createMediaStreamDestination();
      osc.connect(gain).connect(out);osc.start();window.audio=audio;window.osc=osc;window.gain=gain;
      const stream=canvas.captureStream(10);stream.addTrack(out.stream.getAudioTracks()[0]);
      const s=questionTest.state;s.mediaStream=stream;s.session={interview_id:'clip-test'};s.answers=new Array(3);
      s.questions=[{question_id:1,question:'Explain your project. '+('Describe your contribution. '.repeat(12)),section:'resume',answer_type:'text',response_mode:'audio',answer_time_seconds:120},
        {question_id:2,question:'Describe a time you worked with a team.',section:'behavioral',answer_type:'video',response_mode:'video',answer_time_seconds:90},
        {question_id:3,question:'How did you handle difficult feedback?',section:'behavioral',answer_type:'video',response_mode:'video',answer_time_seconds:120}];
      s.assessmentActive=true;s.examDeadline=Date.now()+600000;
      document.querySelector('#consent-check').checked=true;document.querySelector('#interview-panel').classList.remove('hidden');
      questionTest.renderQuestion();
    }""")
    page.wait_for_function("() => questionTest.state.answerClip?.recorder.state === 'recording'")
    assert page.evaluate("readings.join('').includes(questionTest.state.questions[0].question)")
    assert page.evaluate("readings.join('').endsWith('Record your answer.')")
    assert page.locator("#spoken-listening-indicator").evaluate("node => node.classList.contains('listening')")
    assert page.locator("#spoken-mic-label").inner_text().lower().startswith("microphone on")
    assert page.locator("#spoken-question-timer").inner_text() in {"02:00", "01:59"}
    page.wait_for_function("""() => [...document.querySelectorAll('.spoken-frequency-bars i')]
      .some(bar => Number((bar.style.transform.match(/[0-9.]+/)||['0'])[0]) > .2)""")
    assert page.locator("#spoken-listening-indicator").evaluate("node => node.classList.contains('voice-active')")
    page.wait_for_function("() => questionTest.state.answerClip.chunks.length > 0")
    page.evaluate("gain.gain.value=0")
    page.wait_for_function("() => !document.querySelector('#spoken-listening-indicator').classList.contains('voice-active')")
    assert page.evaluate("questionTest.state.answerClip.recorder.stream.getVideoTracks().length") == 0
    page.evaluate("window.firstRecorder=questionTest.state.answerClip.recorder")
    page.locator("#next-question").click()
    page.wait_for_function("() => questionTest.state.answerClip?.questionId===2 && questionTest.state.answerClip.recorder.state==='recording'")
    assert page.evaluate("readings.join('').includes(questionTest.state.questions[1].question)")
    assert page.evaluate("questionTest.state.answerClip.recorder !== firstRecorder")
    assert page.evaluate("questionTest.state.answerClip.recorder.stream.getVideoTracks().length") == 1
    assert page.locator("#spoken-question-timer").inner_text() in {"01:30", "01:29"}
    page.evaluate("window.secondRecorder=questionTest.state.answerClip.recorder")
    page.wait_for_function("() => questionTest.state.answerClip.chunks.length > 0")
    page.locator("#next-question").click()
    page.wait_for_function("() => questionTest.state.answerClip?.questionId===3 && questionTest.state.answerClip.recorder.state==='recording'")
    assert page.evaluate("readings.join('').includes(questionTest.state.questions[2].question)")
    assert page.evaluate("questionTest.state.answerClip.recorder !== secondRecorder")
    assert page.evaluate("questionTest.state.answerClip.recorder.stream.getVideoTracks().length") == 1
    assert page.locator("#spoken-question-timer").inner_text() in {"02:00", "01:59"}
    page.wait_for_function("() => questionTest.state.answerClip.chunks.length > 0")
    page.locator("#next-question").click()
    page.locator("#retry-analysis").wait_for(state="visible")
    assert len(evaluations) == 1
    assert set(clips) == {1, 2, 3}
    assert all(b''.join(chunks).startswith(b'\x1a\x45\xdf\xa3') for chunks in clips.values())
    assert events.index('/mock-interview/clip-test/answers/1/submit') < events.index('/mock-interview/clip-test/answers/2/start')
    assert events.index('/mock-interview/clip-test/answers/2/submit') < events.index('/mock-interview/clip-test/answers/3/start')
    assert page.locator("#return-to-setup").is_visible()
    assert page.locator("#result-panel").is_hidden()
    assert page.locator(".analysis-step.done").count() == 0
    page.evaluate("clearInterval(paint);audio.close()")
    page.close()


def test_spoken_answer_submit_drains_final_media_chunk_before_sealing():
    script = (ROOT / "app/static/mock-interview.js").read_text(encoding="utf-8")
    public_script = (ROOT / "public/static/mock-interview.js").read_text(encoding="utf-8")
    assert script == public_script
    assert "async function drainQuestionAnswerUploads(clip)" in script
    assert "while(clip.uploading || clip.uploaded<clip.chunks.length)await uploadQuestionAnswer(clip);" in script
    assert "await drainQuestionAnswerUploads(clip);" in script
    assert "if(clip.uploaded!==clip.chunks.length)throw new Error('The spoken answer has not finished uploading." in script
    drain_at = script.index("await drainQuestionAnswerUploads(clip);")
    submit_at = script.index("/submit`,{method:'POST'", drain_at)
    assert drain_at < submit_at


def test_spoken_recorder_is_retryable_when_mediarecorder_start_throws():
    script = (ROOT / "app/static/mock-interview.js").read_text(encoding="utf-8")
    public_script = (ROOT / "public/static/mock-interview.js").read_text(encoding="utf-8")
    assert script == public_script
    assert "if(!window.MediaRecorder)throw new Error('This browser cannot record this answer. Use a supported browser.');" in script
    start = script.index("async function startQuestionRecorder(q)")
    end = script.index("async function finishQuestionAnswer()", start)
    block = script[start:end]
    recorder_start = block.index("recorder.start(4000);")
    publish_clip = block.index("state.answerClip=clip;")
    assert recorder_start < publish_clip
