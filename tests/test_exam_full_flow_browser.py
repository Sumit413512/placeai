"""Take both complete exams with isolated accounts and generated device streams.

Real auth/start/exam clock/recording/chunk/seal APIs and database are exercised.
Only narration, detector predictions and external code/AI analysis are simulated.
"""
import json
from io import BytesIO

import av

import pytest
from playwright.sync_api import expect
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models import AnswerRecording, AnswerRecordingChunk, Job, RecruiterProfile
from app.zensar_practice import JOB_ID
from test_browser_smoke import BASE_URL, ROOT, browser, local_server  # noqa: F401
from test_page_layout_browser import layout_accounts  # noqa: F401
from test_zensar_practice import seed_sql


@pytest.fixture(scope="module")
def exams(layout_accounts, local_server):
    engine = create_engine("sqlite:///" + str(local_server))
    with Session(engine) as db:
        recruiter = db.query(RecruiterProfile).one()
        recruiter.company_name = "TechNova Solutions — Demo"
        job = Job(recruiter_id=recruiter.id, title="PlaceAI TechNova Demo Assessment",
                  description="Fictional local demo", visibility="public")
        db.add(job); db.flush(); technova = job.id
        db.execute(text(seed_sql())); db.commit()
    engine.dispose()
    return {"technova": technova, "zensar": JOB_ID}


DEVICES = r"""() => {
  const canvas=document.createElement('canvas');canvas.width=320;canvas.height=240;
  const ctx=canvas.getContext('2d');let frame=0;
  window.paint=setInterval(()=>{ctx.fillStyle=frame++%2?'#eee':'#555';ctx.fillRect(0,0,320,240);},65);
  window.audioContexts=[];
  navigator.mediaDevices.getUserMedia=async options=>{
    const audio=new AudioContext(),osc=audio.createOscillator(),out=audio.createMediaStreamDestination();
    osc.frequency.value=440;osc.connect(out);osc.start();await audio.resume();audioContexts.push(audio);
    const stream=options.video?canvas.captureStream(10):new MediaStream();
    stream.addTrack(out.stream.getAudioTracks()[0]);return stream;
  };
  navigator.mediaDevices.getDisplayMedia=async()=>canvas.captureStream(5);
  Object.defineProperty(window.screen,'isExtended',{value:false});
  window.SpeechSynthesisUtterance=class {constructor(text){this.text=text;}};
  window.spokenTexts=[];window.stallNarration=false;
  Object.defineProperty(window,'speechSynthesis',{value:{cancel(){},resume(){},speak(u){
    spokenTexts.push(u.text);setTimeout(()=>u.onstart?.(),1);
    if(!stallNarration)setTimeout(()=>u.onend?.(),10);
  }}});
}"""


@pytest.mark.parametrize("company", ["technova", "zensar"])
def test_complete_exam_has_same_protection_and_real_recordings(browser, exams, layout_accounts, local_server, company):
    context=browser.new_context(viewport={"width":1440,"height":1000})
    email,password=layout_accounts["student"]
    assert context.request.post(BASE_URL+"/auth/login-json",data={"email":email,"password":password}).status==200
    page=context.new_page(); errors=[]; page.on("pageerror",lambda error:errors.append(str(error)))
    script=(ROOT/"app/static/mock-interview.js").read_text(encoding="utf8")
    script=script.rsplit("})();",1)[0]+"window.examTest={state};})();"
    page.route("**/static/mock-interview.js*",lambda route:route.fulfill(body=script,content_type="application/javascript"))
    worker="self.onmessage=({data})=>self.postMessage(data.type==='load'?{type:'ready'}:{type:'result',id:data.id,predictions:[{class:'person',score:.99,bbox:[40,10,220,220]}]});"
    page.route("**/static/proctor-worker.js*",lambda route:route.fulfill(body=worker,content_type="application/javascript"))
    # Do not send test media to an external AI; capture the real final request.
    submitted=[]
    def evaluate(route):
        submitted.append(route.request.post_data_json)
        route.fulfill(status=503,json={"detail":{"code":"VIDEO_PROVIDER_CAPACITY","message":"Synthetic test analysis is deliberately offline; exam data remains saved."}})
    page.route("**/mock-interview/evaluate",evaluate)
    page.route("**/mock-interview/proctor-frame",lambda route:route.fulfill(json={"candidate_visible":True,"person_count":1,"mobile_phone_detected":False}))
    page.add_init_script("("+DEVICES+")()")
    page.goto(BASE_URL+"/mock-interview",wait_until="domcontentloaded")
    page.locator("#job-select").select_option(exams[company])
    with page.expect_response("**/mock-interview/start") as start:
        page.get_by_role("button",name="Continue to secure system check",exact=True).click()
    assert start.value.status==200,start.value.text()
    result=start.value.json(); questions=result["questions"]; assert len(questions)==50
    page.locator("#consent-check").check()
    page.locator("#run-check").click()
    expect(page.locator('[data-check="microphone"]')).to_contain_text("Connected")
    page.locator("#run-liveness").click()
    expect(page.locator("#start-assessment")).to_be_enabled(timeout=15000)
    page.locator("#start-assessment").click()
    expect(page.locator("#interview-panel")).to_be_visible()
    assert page.evaluate("examTest.state.assessmentActive")
    assert page.locator("#question-text").evaluate("el=>getComputedStyle(el).userSelect")=="none"
    # Test browser-menu events as well as keyboard variants; the code editor stays editable.
    protection=page.evaluate("""() => {
      const q=document.querySelector('#question-text');
      const result={};
      for(const type of ['copy','paste','cut','selectstart','dragstart','contextmenu']){
        result[type]=!q.dispatchEvent(new Event(type,{bubbles:true,cancelable:true}));
      }
      for(const [key,options] of [['c',{ctrlKey:true}],['v',{metaKey:true}],['Insert',{shiftKey:true}],['Insert',{ctrlKey:true}],['Delete',{shiftKey:true}]]){
        result[key+JSON.stringify(options)]=!q.dispatchEvent(new KeyboardEvent('keydown',{key,...options,bubbles:true,cancelable:true}));
      }
      return result;
    }""")
    assert all(protection.values()),protection
    recorded=[]
    for i,q in enumerate(questions):
        expect(page.locator("#question-progress")).to_have_text(f"Question {i+1} of 50")
        if q.get("response_mode"):
            if not recorded:
                # A voice engine can start but never fire onend. Starting manually must remain possible.
                expect(page.get_by_role("button",name="Start answer now",exact=True)).to_be_visible()
                page.get_by_role("button",name="Start answer now",exact=True).click()
            page.wait_for_function("qid => examTest.state.answerClip?.questionId===qid && examTest.state.answerClip.recorder.state==='recording'",arg=q["question_id"])
            assert page.locator("#spoken-mic-label").inner_text().lower()=="microphone on · listening"
            assert page.evaluate("examTest.state.answerClip.recorder.stream.getVideoTracks().length")==int(q["response_mode"]=="video")
            page.wait_for_timeout(160)
            recorded.append(q["question_id"])
            page.evaluate("stallNarration=false")
        elif q["answer_type"]=="mcq":
            page.locator(".option-button").first.click()
        else:
            page.locator("#code-editor").fill("print(0)")
            assert page.locator("#code-editor").evaluate("el=>!getComputedStyle(el).userSelect.includes('none')")
        if q.get("response_mode") and len(recorded)==1:
            page.evaluate("examTest.state.mediaStream.getAudioTracks()[0].stop()")
        if i==37:page.evaluate("stallNarration=true")
        page.locator("#next-question").click()
        if q.get("response_mode") and len(recorded)==1:
            expect(page.locator("#reconnect-answer-microphone")).to_be_visible()
            camera=page.evaluate("examTest.state.mediaStream.getVideoTracks()[0].id")
            if company=="zensar":
                page.evaluate("() => {window.restoreMicrophone=navigator.mediaDevices.getUserMedia;navigator.mediaDevices.getUserMedia=async()=>{throw new DOMException('Test microphone permission denied','NotAllowedError');};}")
                page.locator("#reconnect-answer-microphone").click()
                expect(page.locator("#spoken-answer-status")).to_contain_text("permission denied")
                expect(page.locator("#reconnect-answer-microphone")).to_be_enabled()
                assert page.evaluate("examTest.state.answerClip===null")
                assert page.evaluate("examTest.state.mediaStream.getVideoTracks()[0].id")==camera
                page.evaluate("() => {navigator.mediaDevices.getUserMedia=restoreMicrophone;}")
            page.locator("#reconnect-answer-microphone").click()
            page.wait_for_function("() => examTest.state.answerClip?.recorder.state==='recording'")
            assert page.evaluate("examTest.state.mediaStream.getVideoTracks()[0].id")==camera
    expect(page.locator("#retry-analysis")).to_be_visible(timeout=15000)
    assert len(recorded)==12 and len(submitted)==1
    assert len(submitted[0]["answers"])==50
    engine=create_engine("sqlite:///"+str(local_server))
    with Session(engine) as db:
        clips=db.query(AnswerRecording).filter_by(interview_id=result["interview_id"]).all()
        assert len(clips)==12
        assert all(row.sealed_at and row.chunk_count and row.size_bytes>0 for row in clips)
        for row in clips:
            chunks=db.query(AnswerRecordingChunk).filter_by(recording_id=row.id).order_by(AnswerRecordingChunk.sequence).all()
            with av.open(BytesIO(b"".join(chunk.data for chunk in chunks))) as media:
                assert bool(media.streams.video)==row.mime_type.startswith("video/")
                audio=list(media.decode(audio=0))
                assert audio and any(frame.to_ndarray().max()>0 for frame in audio),row.question_id
    engine.dispose()
    assert not errors,errors
    output=ROOT/"work/exam-flow-verification";output.mkdir(parents=True,exist_ok=True)
    (output/(company+".json")).write_text(json.dumps({"questions":50,"clips":12,"protected":protection,"errors":errors},indent=2),encoding="utf8")
    page.evaluate("clearInterval(paint);audioContexts.forEach(c=>c.close())")
    context.close()
