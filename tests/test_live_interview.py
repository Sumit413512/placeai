"""Real video interview practice is secure, optional, and separate from scoring."""
from pathlib import Path
import time
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.app import app
from app.routers import live_interview as live

ROOT=Path(__file__).resolve().parents[1]


def test_live_interview_is_real_provider_backed_not_static_pretend():
    html=(ROOT/"app/templates/mock-interview.html").read_text()
    assert html==(ROOT/"public/mock-interview.html").read_text()
    assert 'id="live-coach-frame"' in html
    assert 'id="live-coach-consent"' in html
    assert 'id="live-coach-end"' in html
    assert 'id="live-coach-preview"' in html
    assert 'id="live-coach-timer"' in html
    assert "separate from the scored" in html
    for name in ("mock-interview.js","mock-interview.css","live-interview.js"):
        assert (ROOT/"app/static"/name).read_text()==(ROOT/"public/static"/name).read_text()
    js=(ROOT/"app/static/live-interview.js").read_text()
    assert "tavus.daily.co" in js
    assert "frame.src=data.conversation_url" in js
    assert "navigator.mediaDevices.getUserMedia" in js
    assert "localStream.getTracks().forEach(track=>track.stop())" in js
    assert "void closeSession()" in js
    assert "/mock-interview/live/end" in js
    assert "window.PlaceAILiveInterview" in js
    assert "window.PlaceAILiveInterview?.init(state.token)" in (ROOT/"app/static/mock-interview.js").read_text()


def test_live_routes_are_authenticated():
    client=TestClient(app)
    for method,path in (("GET","/mock-interview/live/status"),("POST","/mock-interview/live/start"),("POST","/mock-interview/live/end")):
        response=client.request(method,path)
        assert response.status_code in (401,403,422)
    paths=client.get("/openapi.json").json()["paths"]
    assert "/mock-interview/live/status" in paths
    assert "/mock-interview/live/start" in paths
    assert "/mock-interview/live/end" in paths


def test_provider_url_must_be_tavus_daily_only():
    assert live._room_url("https://tavus.daily.co/c12345")=="https://tavus.daily.co/c12345"
    for url in ("https://evil.example/c12345","http://tavus.daily.co/c12345",
                "https://tavus.daily.co.evil.example/c12345",
                "https://tavus.daily.co@evil.example/c12345",
                "https://tavus.daily.co/c12345#frag"):
        with pytest.raises(HTTPException):
            live._room_url(url)


def test_end_proof_binds_user_and_conversation():
    proof=live._proof("c12345","user-1",int(time.time())+600)
    live._verify_proof(proof,"c12345","user-1")
    for cid,uid in (("c12345","user-2"),("c99999","user-1")):
        with pytest.raises(HTTPException):
            live._verify_proof(proof,cid,uid)
    with pytest.raises(HTTPException):
        live._verify_proof(proof[:-3]+"xxx","c12345","user-1")


def test_live_session_requires_explicit_consent():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        live.LiveStart(role="<script>",consent=True)
    with pytest.raises(ValidationError):
        live.LiveStart(role="Software Engineer",language="unknown",consent=True)

def test_session_creation_fails_closed_without_provider_credentials(monkeypatch):
    import asyncio
    from fastapi import Response
    monkeypatch.delenv("TAVUS_API_KEY",raising=False)
    monkeypatch.delenv("TAVUS_PAL_ID",raising=False)
    monkeypatch.delenv("TAVUS_FACE_ID",raising=False)
    async def call():
        return await live.live_start(
            live.LiveStart(role="Software Engineer",consent=True),
            Response(),None,SimpleNamespace(id="user-1"),None,
        )
    with pytest.raises(HTTPException) as error:
        asyncio.run(call())
    assert error.value.status_code==503


def test_provider_is_never_called_without_consent(monkeypatch):
    import asyncio
    from fastapi import Response
    monkeypatch.setenv("TAVUS_API_KEY","test-only")
    monkeypatch.setenv("TAVUS_PAL_ID","pal-test")
    monkeypatch.setenv("TAVUS_FACE_ID","face-test")
    async def call():
        return await live.live_start(
            live.LiveStart(role="Software Engineer",consent=False),
            Response(),None,SimpleNamespace(id="user-1"),None,
        )
    with pytest.raises(HTTPException) as error:
        asyncio.run(call())
    assert error.value.status_code==422

def test_live_provider_is_disclosed_in_privacy_policy():
    html=(ROOT/"app/templates/privacy.html").read_text()
    assert "Optional live video interview practice" in html
    assert "Tavus" in html
    assert "explicitly opts in" in html
    assert html==(ROOT/"public/privacy.html").read_text()

def test_live_start_and_end_provider_contract_without_real_credentials(monkeypatch):
    import asyncio
    from fastapi import Response
    monkeypatch.setenv("TAVUS_API_KEY","test-only-key")
    monkeypatch.setenv("TAVUS_PAL_ID","pcb-test")
    monkeypatch.setenv("TAVUS_FACE_ID","r-test")
    calls=[]
    limits=[]
    async def provider(method,url,key,*,payload=None):
        calls.append((method,url,key,payload))
        if url.endswith("/end"):
            return {"ended":True}
        return {"conversation_id":"c12345","conversation_url":"https://tavus.daily.co/c12345",
                "meeting_token":"test-meeting-token"}
    monkeypatch.setattr(live,"_provider",provider)
    monkeypatch.setattr(live,"enforce_rate_limit",lambda *a,**kw:limits.append(kw))
    student=SimpleNamespace(id="student-test")
    result=asyncio.run(live.live_start(
        live.LiveStart(role="Data Analyst",focus="technical",language="english",consent=True),
        Response(),None,student,None,
    ))
    assert result["conversation_url"]=="https://tavus.daily.co/c12345?t=test-meeting-token"
    assert result["max_minutes"]==10
    assert calls[0][0]=="POST" and calls[0][1]==live.PROVIDER_URL
    assert calls[0][3]["pal_id"]=="pcb-test"
    assert calls[0][3]["face_id"]=="r-test"
    assert calls[0][3]["require_auth"] is True
    assert calls[0][3]["max_participants"]==2
    assert calls[0][3]["properties"]["max_call_duration"]==600
    assert calls[0][3]["properties"]["enable_recording"] is False
    assert calls[0][3]["properties"]["enable_closed_captions"] is True
    assert limits[0]["limit"]==2 and limits[0]["window_seconds"]==3600
    end=asyncio.run(live.live_end(live.LiveEnd(
        conversation_id=result["conversation_id"],session_proof=result["session_proof"]),student))
    assert end=={"ended":True}
    assert calls[1][1]=="https://tavusapi.com/v2/conversations/c12345/end"
