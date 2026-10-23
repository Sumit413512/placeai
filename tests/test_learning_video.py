import io
import json
import base64
import wave
from datetime import timedelta
from types import SimpleNamespace

import av
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from test_learning_hub import hub  # noqa: F401
from app import learning_ai, learning_video_worker as worker
from app.learning_video_content import CoursePlan, LessonScript, VideoScene
from app.learning_video_media import captions, render_video, slide
from app.models import VideoCourse, VideoLesson, VideoProgress, VideoViewerProgress, VideoNarration, utcnow
from app.routers import learning_video


def course_plan():
    return {"title": "SQL foundations", "introduction": "Learn relational queries through focused lessons and practice.",
            "prerequisites": ["Basic computer familiarity"], "lessons": [
                {"title": f"Query concept {i}", "objective": "Understand and apply one relational query concept.",
                 "module_title":"Query foundations" if i<2 else "Applied queries"}
                for i in range(4)]}


def script():
    return {"objective": "Select columns from a relation and explain the resulting projection.",
            "scenes": [{"title": f"Selecting columns {i}", "narration": "SELECT chooses the named columns from a table. The FROM clause identifies the source relation. Check the column names against your schema before running this illustrative query.",
                        "bullets": ["SELECT chooses columns", "FROM identifies the table"],
                        "code": "SELECT name FROM students;", "diagram": None, "source_ids": [1]} for i in range(4)],
            "takeaways": ["SELECT names the output columns.", "FROM names the input relation."],
            "quiz": [{"question": "Which clause identifies the source table?", "options": ["FROM", "SELECT", "ORDER BY"],
                      "answer": 0, "explanation": "FROM identifies the relation from which the query reads rows."} for _ in range(3)],
            "exercise": "Write a query selecting the name column from the students table.",
            "solution": "Use SELECT name FROM students. SELECT identifies the requested column and FROM identifies the relation. Verify these identifiers against your schema first."}


@pytest.fixture
def video(hub, monkeypatch):  # noqa: F811
    monkeypatch.setattr(learning_video, 'student_ai_guard', lambda *_args: None)
    monkeypatch.setattr(worker, 'review_video', lambda *_args: {'passed': True, 'version': 1})
    app = FastAPI(); app.include_router(learning_video.router)
    app.dependency_overrides.update(hub.client.app.dependency_overrides)
    with TestClient(app) as client:
        yield SimpleNamespace(**vars(hub), api=client)


def new_course(video):
    response = video.api.post('/learning-hub/video', json={"topic": "SQL", "request_id": "video-request-00000001"})
    assert response.status_code == 202, response.text
    return response.json()['id']


def ready_lesson(video, full_ready=True):
    identifier = new_course(video)
    course = video.db.get(VideoCourse, identifier)
    course.state, course.plan_json = 'ready', json.dumps(course_plan())
    course.input_json = json.dumps({'topic':'SQL'})  # Existing short-course compatibility.
    video.db.commit()
    assert video.api.post(f'/learning-hub/video/{identifier}/lessons/0').status_code == 202
    lesson = video.db.query(VideoLesson).filter_by(course_id=identifier).one()
    content = script(); content['sources'] = [{"title": "PostgreSQL", "url": "https://www.postgresql.org/docs/current/sql-select.html"}]
    content.update({key: {'passed': True, 'version': 1} for key in ['content_review', 'media_review', 'audiovisual_review']})
    content['timings'] = [{"start": i * 25, "end": (i+1)*25} for i in range(4)]
    lesson.state, lesson.content_json, lesson.duration_seconds = 'ready', json.dumps(content), 100
    lesson.video_data = b'private-video-test'
    if full_ready:
        for index in range(1, 4):
            video.db.add(VideoLesson(course_id=identifier, position=index, title=f'Part {index}', state='ready', content_json=json.dumps(content), video_data=b'private-video-test', duration_seconds=100))
    video.db.commit()
    return identifier, lesson.id, f'/learning-hub/video/{identifier}/lessons/0'


def test_course_idempotency_budgets_and_owner_isolation(video):
    identifier = new_course(video)
    assert new_course(video) == identifier
    assert video.api.post('/learning-hub/video', json={"topic":"Python", "request_id":"video-request-00000001"}).status_code == 409
    for i in range(2):
        assert video.api.post('/learning-hub/video', json={"topic":f"SQL {i}", "request_id":f"video-request-new-00{i}"}).status_code == 202
    assert video.api.post('/learning-hub/video', json={"topic":"New topic", "request_id":"video-request-limited"}).status_code == 429
    video.actor[0] = video.other
    assert video.api.get('/learning-hub/video').json()['items'] == []
    assert video.api.get(f'/learning-hub/video/{identifier}').status_code == 404
    assert video.api.post(f'/learning-hub/video/{identifier}/lessons/0').status_code == 404
    anonymous = TestClient(FastAPI())
    anonymous.app.include_router(learning_video.router)
    assert anonymous.get('/learning-hub/video').status_code == 401


def test_media_transcript_practice_and_progress_are_private(video):
    identifier, lesson_id, path = ready_lesson(video)
    manifest = video.api.get(path).json()
    assert 'solution' not in manifest['content']
    assert 'answer' not in manifest['content']['quiz'][0]
    media = video.api.get(path+'/media')
    assert media.content == b'private-video-test' and 'no-store' in media.headers['cache-control']
    assert media.headers['content-type'] == 'video/mp4'
    assert video.api.get(path+'/captions').text.startswith('WEBVTT')
    failed = video.api.post(path+'/practice', json={"answers":[1,1,1]}).json()
    assert not failed['practice_completed'] and 'solution' in failed
    passed = video.api.post(path+'/practice', json={"answers":[0,0,0]}).json()
    assert passed['practice_completed'] and not passed['video_completed']
    assert video.api.post(path+'/practice', json={"answers":[9,0,0]}).status_code == 422
    video.actor[0] = video.other
    for suffix in ('', '/media', '/captions'):
        assert video.api.get(path+suffix).status_code == 404
    assert video.api.put(path+'/progress', json={"position_seconds":10}).status_code == 404
    assert video.api.post(path+'/practice', json={"answers":[0,0,0]}).status_code == 404


def test_seeking_does_not_award_completion_and_coverage_survives_reload(video):
    _, lesson_id, path = ready_lesson(video)
    jumped = video.api.put(path+'/progress', json={"position_seconds":99}).json()
    assert jumped['watched_seconds'] == 0 and not jumped['video_completed']
    video.api.put(path+'/progress', json={"position_seconds":0})
    for end in (25,50,75,95):
        video.db.expire_all()
        record = video.db.get(VideoViewerProgress, (video.owner.id, lesson_id))
        record.updated_at = utcnow() - timedelta(seconds=15)
        video.db.commit()
        saved = video.api.put(path+'/progress', json={"position_seconds":end}).json()
    assert saved['video_completed'] and saved['watched_seconds'] == 95
    assert video.api.get(path).json()['position_seconds'] == 95
    # Replaying covered seconds cannot inflate progress.
    video.api.put(path+'/progress', json={"position_seconds":70})
    assert video.api.put(path+'/progress', json={"position_seconds":71}).json()['watched_seconds'] == 95
    assert video.api.put(path+'/progress', json={"position_seconds":-1}).status_code == 422


def test_worker_saves_real_playable_media_and_recovers_expired_lease(video, monkeypatch):
    identifier = new_course(video)
    row = video.db.get(VideoCourse, identifier); row.input_json = json.dumps({'topic':'SQL'}); video.db.commit()
    references = [{"title":"PostgreSQL", "url":"https://www.postgresql.org/docs/current/sql-select.html"}]
    monkeypatch.setattr(learning_ai, 'research', lambda _: ('Official query evidence', references, 'test'))
    monkeypatch.setattr(learning_ai, 'generate_json', lambda *_a, **_k: (course_plan(), 'test'))
    with video.sessions() as db: item = worker.claim(db)
    with video.sessions() as db: assert worker.claim(db) is None
    worker.process(item, video.sessions)
    assert video.api.get(f'/learning-hub/video/{identifier}').json()['status'] == 'ready'
    assert video.db.query(VideoLesson).count() == 4  # One queued set for every student.
    video.api.post(f'/learning-hub/video/{identifier}/lessons/0')
    def author(task, *_a, **_k):
        content = script()
        content['scenes'][-1].update(code='', bullets=['Trace the selected column'], diagram={
            'title':'Projection', 'nodes':[{'id':'a','label':'Students'},{'id':'b','label':'Names'}],
            'edges':[{'source':'a','target':'b','label':'Select name'}],
            'explanation':'The query reads the students table and projects the name column into the result. Each selected name comes from one source row.'})
        return ({"approved":True, "issues":[]} if task.startswith('Review') else content, 'test')
    monkeypatch.setattr(learning_ai, 'generate_json', author)
    monkeypatch.setattr(worker, 'render_video', lambda content, **_kw: render_video(content, narrate=lambda _: b'\x10\x01'*24000))
    with video.sessions() as db: first = worker.claim(db)
    with video.sessions() as db:
        row = db.get(VideoLesson, first[1]); row.lease_until = utcnow() - timedelta(seconds=1); db.commit()
    with video.sessions() as db: replacement = worker.claim(db)
    assert replacement[1] == first[1] and replacement[2] != first[2]
    worker.process(first, video.sessions)  # A stale worker must not publish.
    worker.process(replacement, video.sessions)
    assert video.api.get(f'/learning-hub/video/{identifier}/lessons/0/media').status_code == 409
    for _ in range(3):
        with video.sessions() as db:
            next_item = worker.claim(db)
        worker.process(next_item, video.sessions)
    response = video.api.get(f'/learning-hub/video/{identifier}/lessons/0/media')
    assert response.status_code == 200, response.text
    with av.open(io.BytesIO(response.content)) as container:
        assert {stream.type for stream in container.streams} == {'audio','video'}
        assert sum(1 for _ in container.decode(video=0)) == 32


def test_worker_failure_is_honest_and_no_media_is_published(video, monkeypatch):
    identifier = new_course(video)
    monkeypatch.setattr(learning_ai, 'research', lambda _: (_ for _ in ()).throw(RuntimeError('provider down')))
    for _ in range(3):
        with video.sessions() as db:
            row = db.get(VideoCourse, identifier); row.available_at = utcnow() - timedelta(seconds=1); db.commit()
            item = worker.claim(db)
        worker.process(item, video.sessions)
    assert video.api.get(f'/learning-hub/video/{identifier}').json()['status'] == 'failed'
    assert video.db.query(VideoLesson).count() == 0
    assert video.api.post(f'/learning-hub/video/{identifier}/retry').status_code == 200
    with video.sessions() as db:
        item = worker.claim(db)
    worker.process(item, video.sessions)
    assert not video.api.get(f'/learning-hub/video/{identifier}').json()['retry_available']
    assert video.api.post(f'/learning-hub/video/{identifier}/retry').status_code == 409


def test_lesson_retry_reuses_the_same_private_record_and_is_bounded(video):
    identifier, lesson_id, path = ready_lesson(video, full_ready=False)
    row = video.db.get(VideoLesson, lesson_id)
    row.state, row.attempts = 'failed', 3; video.db.commit()
    assert video.api.post(path).status_code == 202
    assert video.db.query(VideoLesson).count() == 1
    video.db.expire_all()
    row = video.db.get(VideoLesson, lesson_id)
    row.state, row.attempts = 'failed', 4; video.db.commit()
    assert video.api.post(path).status_code == 409


def test_scripts_reject_unreadable_content_and_captions_escape_markup():
    assert CoursePlan.model_validate(course_plan())
    assert LessonScript.model_validate(script())
    bad = script()['scenes'][0]; bad['code'] = 'x' * 100
    with pytest.raises(ValidationError): VideoScene.model_validate(bad)
    bad = script()['scenes'][0]; bad['bullets'] = ['x'*100]*3; bad['code'] = '\n'.join(['line']*7)
    with pytest.raises(ValueError): slide(bad, 1, 4)
    assert '&lt;script&gt;' in captions({"scenes":[{"narration":"<script>"}],"timings":[{"start":0,"end":2}]})


def test_provider_script_format_is_repaired_once_before_narration(monkeypatch):
    raw = script(); raw['scenes'][0]['code'] = None
    repairs = []
    def repair(task, *_args, **_kwargs):
        repairs.append(task)
        return script(), 'test'
    monkeypatch.setattr(learning_ai, 'generate_json', repair)
    result = worker.validate_script(raw, 'Official SELECT documentation', [{"id":1,"url":"https://www.postgresql.org/docs/current/sql-select.html"}])
    assert result.scenes[0].code == 'SELECT name FROM students;'
    assert len(repairs) == 1 and 'scenes' in repairs[0]
    monkeypatch.setattr(learning_ai, 'generate_json', lambda *_a, **_k: (raw, 'test'))
    with pytest.raises(ValidationError):
        worker.validate_script(raw, 'Query evidence', [{"id":1}])


def test_mixed_visual_scene_is_split_without_losing_teaching_or_code():
    raw = script()
    diagram = {"title":"Projecting selected columns", "nodes":[{"id":"table","label":"Students"},
               {"id":"output","label":"Names"}], "edges":[{"source":"table","target":"output","label":"Choose name column"}],
               "explanation":"The source table contains student records. Selecting the name column projects one attribute from each input row into the query result."}
    raw['scenes'][0]['diagram'] = diagram
    transformed = worker.separate_visuals(raw)
    checked = LessonScript.model_validate(transformed)
    assert len(checked.scenes) == 5
    assert checked.scenes[0].code == raw['scenes'][0]['code']
    assert checked.scenes[0].narration == raw['scenes'][0]['narration']
    assert checked.scenes[1].narration == diagram['explanation']
    assert raw['scenes'][0]['diagram'] == diagram  # Input remains untouched.
    for index, scene in enumerate(checked.scenes):
        slide(scene.model_dump(), index+1, len(checked.scenes))


def test_short_solution_is_expanded_without_regenerating_other_lesson_fields(monkeypatch):
    raw = script(); raw['solution'] = 'SELECT name FROM students;'
    replacement = script()['solution']
    monkeypatch.setattr(learning_ai, 'generate_json', lambda *_a, **_k: (
        {"repairs":[{"path":"solution","value":replacement}]},'test'))
    checked = worker.validate_script(raw, 'Official query evidence', [{"id":1}])
    assert checked.solution == replacement
    assert checked.scenes[0].narration == raw['scenes'][0]['narration']


def test_speech_quota_wait_keeps_completed_scene_work_and_has_a_bound(monkeypatch):
    from contextlib import contextmanager
    import httpx
    from app import learning_video_media as media
    wav = io.BytesIO()
    with wave.open(wav, 'wb') as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(24000)
        audio.writeframes(b'\0'*48000)
    request = httpx.Request('POST','https://generativelanguage.googleapis.com/v1beta/interactions')
    responses = [httpx.Response(429,json={'error':{'details':[{'retryDelay':'2s'}]}},request=request),
                 httpx.Response(200,json={'steps':[{'type':'model_output','content':[{'type':'audio',
                    'data':base64.b64encode(wav.getvalue()).decode()}]}]},request=request)]
    delays = []
    monkeypatch.setattr(media.ai_provider,'_gemini_key',lambda:'isolated-test-key')
    monkeypatch.setattr(media.ai_provider,'_openai_keys',lambda:[])
    @contextmanager
    def streamed(*_args, **_kwargs):
        yield responses.pop(0)
    monkeypatch.setattr(media.httpx,'stream',streamed)
    monkeypatch.setattr(media.time,'sleep',delays.append)
    assert media.speak('A short isolated teaching narration.') == b'\0'*48000
    assert delays == [3] and not responses
    daily = httpx.Response(429,json={'error':{'details':[{'violations':[{'quotaId':'RequestsPerDay','quotaValue':'0'}]}]}},request=request)
    assert media.quota_delay(daily) is None
    responses.append(httpx.Response(200,json={'steps':[{'type':'model_output','content':[{'type':'audio',
        'data':base64.b64encode(wav.getvalue()).decode()}]}]},request=request))
    failures = [True]
    @contextmanager
    def interrupted(*_args, **_kwargs):
        if failures:
            failures.pop()
            raise httpx.RemoteProtocolError('Isolated transport interruption')
        yield responses.pop(0)
    monkeypatch.setattr(media.httpx,'stream',interrupted)
    assert media.speak('Retry only the interrupted narration scene.') == b'\0'*48000
    assert delays == [3, 1]


def test_shared_course_reuses_media_but_never_another_students_progress(video, monkeypatch):
    identifier, lesson_id, path = ready_lesson(video)
    video.api.put(path+'/progress', json={'position_seconds':12})
    video.api.post(path+'/practice', json={'answers':[0,0,0]})
    video.actor[0] = video.other
    assert video.api.get(path+'/media').status_code == 404  # Must join first.
    monkeypatch.setattr(learning_video, 'generation_available', lambda _db:False)
    monkeypatch.setattr(learning_video, 'student_ai_guard', lambda *_args:pytest.fail('Cache hit used AI budget'))
    joined = video.api.post('/learning-hub/video', json={'topic':'  sQl  ', 'request_id':'another-student-0001'})
    assert joined.status_code == 202 and joined.json()['id'] == identifier
    assert video.db.query(VideoCourse).count() == 1
    assert video.api.get(path+'/media').content == b'private-video-test'
    assert video.api.post(path).status_code == 202  # Ready lesson is never regenerated.
    fresh = video.api.get(path).json()
    assert fresh['position_seconds'] == 0 and not fresh['practice_completed']
    video.api.put(path+'/progress', json={'position_seconds':3})
    video.actor[0] = video.owner
    mine = video.api.get(path).json()
    assert mine['position_seconds'] == 12 and mine['practice_completed']
    assert video.api.get(f'/learning-hub/video/{identifier}').json()['practice_completed'] == 1
    assert video.db.query(VideoViewerProgress).count() == 2


def test_audio_checkpoint_survives_retry_and_daily_quota_is_not_retried_in_a_loop(video, monkeypatch):
    _, lesson_id, _ = ready_lesson(video)
    row = video.db.get(VideoLesson, lesson_id)
    row.state, row.lease_token, row.lease_until = 'running', 'checkpoint-test', utcnow()+timedelta(minutes=5)
    video.db.commit()
    calls = []
    monkeypatch.setattr(worker, 'speak', lambda text: calls.append(text) or b'\0'*48000)
    first = worker.cached_narrator(lesson_id, 'checkpoint-test', video.sessions)
    assert first('One explanation') == b'\0'*48000
    second = worker.cached_narrator(lesson_id, 'checkpoint-test', video.sessions)
    assert second('One explanation') == b'\0'*48000
    assert calls == ['One explanation'] and video.db.query(VideoNarration).count() == 1
    from app import learning_video_media as media
    import httpx
    response = httpx.Response(429, json={'error':{'message':'Rate limit exceeded (10 requests per day). Please retry in 2h3m4s'}})
    assert media.quota_delay(response) is None
    assert response.extensions['video_retry_seconds'] == 7444


def test_board_frames_change_during_explanation():
    from PIL import ImageChops
    from app.learning_video_media import board_frame
    scene = script()['scenes'][0]
    assert ImageChops.difference(board_frame(scene,1,4,.1),board_frame(scene,1,4,.9)).getbbox()


def test_legacy_personalised_course_never_enters_shared_cache(video):
    legacy = VideoCourse(user_id=video.owner.id, request_id='legacy-private-00001', title='Personal SQL',
        input_json=json.dumps({'topic':'SQL','goal':'Private learner goal'}), state='ready', plan_json=json.dumps(course_plan()))
    video.db.add(legacy); video.db.commit()
    video.actor[0] = video.other
    joined = video.api.post('/learning-hub/video', json={'topic':'SQL','request_id':'fresh-shared-request1'}).json()
    assert joined['id'] != legacy.id
    assert video.api.get(f'/learning-hub/video/{legacy.id}').status_code == 404
    assert video.api.get('/learning-hub/video').json()['items'][0]['id'] == joined['id']


def test_daily_quota_defers_only_the_affected_lesson(video):
    identifier, lesson_id, _ = ready_lesson(video, full_ready=False)
    row = video.db.get(VideoLesson, lesson_id)
    row.state, row.error_code, row.available_at = 'retrying', 'NARRATION_CAPACITY', utcnow()+timedelta(hours=2)
    video.db.add(VideoLesson(course_id=identifier, position=1, title='Next part'))
    video.db.commit()
    with video.sessions() as db:
        item = worker.claim(db)
        assert item[0] == 'lesson' and item[1] != lesson_id
    course = video.api.get(f'/learning-hub/video/{identifier}').json()
    assert course['preparation_status'] == 'preparing'


def test_practice_during_playback_does_not_reset_the_watch_clock(video):
    _, lesson_id, path = ready_lesson(video)
    video.api.put(path+'/progress',json={'position_seconds':0})
    video.db.expire_all()
    record = video.db.get(VideoViewerProgress,(video.owner.id,lesson_id))
    clock = utcnow()-timedelta(seconds=12)
    record.updated_at = clock; video.db.commit()
    assert video.api.post(path+'/practice',json={'answers':[0,0,0]}).json()['practice_completed']
    video.db.expire_all()
    assert video.db.get(VideoViewerProgress,(video.owner.id,lesson_id)).updated_at == clock
    saved = video.api.put(path+'/progress',json={'position_seconds':20}).json()
    assert saved['watched_seconds'] == 20 and saved['practice_completed']


def test_course_numbers_readiness_and_combined_completion(video):
    identifier, lesson_id, path = ready_lesson(video, full_ready=False)
    legacy = course_plan()
    for item in legacy['lessons']:item.pop('module_title')
    row = video.db.get(VideoCourse,identifier);row.plan_json=json.dumps(legacy);video.db.commit()
    data = video.api.get(f'/learning-hub/video/{identifier}').json()
    assert [item['number'] for item in data['lessons']] == ['1.1','1.2','2.1','2.2']
    assert not data['course_ready'] and data['ready_parts'] == 1 and data['completion_percent'] == 0
    assert data['modules'][0]['title'] == 'Module 1'
    row = video.db.get(VideoCourse,identifier)
    plan = course_plan()
    for index,item in enumerate(plan['lessons']):
        item['module_title'] = 'Query foundations' if index < 2 else 'Applied queries'
    row.plan_json = json.dumps(plan)
    for index in range(1,4):
        video.db.add(VideoLesson(course_id=identifier,position=index,title=f'Part {index}',state='ready',content_json=json.dumps({key:{'passed':True} for key in ['content_review','media_review','audiovisual_review']})))
    video.db.commit()
    data = video.api.get(f'/learning-hub/video/{identifier}').json()
    assert data['course_ready'] and data['preparation_status'] == 'ready'
    assert [module['title'] for module in data['modules']] == ['Query foundations','Applied queries']
    video.api.put(path+'/progress',json={'position_seconds':0})
    video.db.expire_all(); record=video.db.get(VideoViewerProgress,(video.owner.id,lesson_id))
    record.video_completed=True; video.db.commit()
    assert video.api.get(f'/learning-hub/video/{identifier}').json()['completion_percent'] == 0
    video.api.post(path+'/practice',json={'answers':[0,0,0]})
    assert video.api.get(f'/learning-hub/video/{identifier}').json()['completion_percent'] == 25


def test_background_replenishes_all_course_parts_once(video):
    identifier = new_course(video)
    course = video.db.get(VideoCourse,identifier)
    course.state,course.plan_json='ready',json.dumps(course_plan());video.db.commit()
    with video.sessions() as db:
        worker.fill_pending_parts(db)
        worker.fill_pending_parts(db)
    assert video.db.query(VideoLesson).count() == 4
    assert {row.position for row in video.db.query(VideoLesson)} == {0,1,2,3}
    invalid = course_plan()
    for index,item in enumerate(invalid['lessons']):item['module_title']=['One','Two','One','Two'][index]
    with pytest.raises(ValidationError):CoursePlan.model_validate(invalid)


def test_full_sql_curriculum_has_depth_and_cannot_drop_an_advanced_module():
    from app.learning_video_content import SQL_MODULES, validate_full_plan
    raw=course_plan()
    raw['lessons']=[{'title':f'{name} example {part}',
        'objective':f'Understand and apply {name.lower()} through a focused worked example.',
        'module_title':name} for name in SQL_MODULES for part in (1,2)]
    assert len(validate_full_plan(raw,'Full SQL course').lessons)==28
    raw['lessons']=raw['lessons'][:-2]
    with pytest.raises(ValueError):validate_full_plan(raw,'Full SQL course')
    with pytest.raises(ValueError):validate_full_plan(course_plan(),'SQL')


def test_new_full_course_publishes_only_after_every_lesson_passes_checks(video):
    identifier,lesson_id,path=ready_lesson(video, full_ready=False)
    course=video.db.get(VideoCourse,identifier)
    course.input_json=json.dumps({'topic':'SQL','curriculum_version':2})
    for position in range(1,4):
        video.db.add(VideoLesson(course_id=identifier,position=position,title=f'Part {position}',
            state='ready',video_data=b'test-checked-media',content_json=json.dumps(script())))
    video.db.commit()
    assert video.api.get(path).status_code==409
    assert video.api.get(path+'/media').status_code==409
    assert video.api.get(f'/learning-hub/video/{identifier}').json()['checked_parts']==1
    for row in video.db.query(VideoLesson).filter_by(course_id=identifier):
        content=json.loads(row.content_json)
        content.update(content_review={'passed':True},media_review={'passed':True},audiovisual_review={'passed':True})
        row.content_json=json.dumps(content)
    video.db.commit()
    assert video.api.get(f'/learning-hub/video/{identifier}').json()['course_ready']
    assert video.api.get(path).status_code==200
    video.actor[0]=video.other
    assert video.api.get(path).status_code==404


def test_actual_media_recheck_rejects_silent_and_broken_output(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, 'numpy', None)  # Production has no optional ndarray dependency.
    from app.learning_video_media import inspect_video
    content=script()
    data,duration,timings=render_video(content,narrate=lambda _:b'\x10\x01'*24000)
    content['timings']=timings
    report=inspect_video(data,content,duration)
    assert report['passed'] and report['tracks']['video']['frames']==32
    with pytest.raises(Exception):inspect_video(data[:100],content,duration)
    with pytest.raises(ValueError):inspect_video(data,content,duration+1)
    silent,duration,timings=render_video(content,narrate=lambda _:b'\0'*48000)
    with pytest.raises(ValueError,match='Silent'):inspect_video(silent,content,duration)
