import io
import json
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
from app.models import VideoCourse, VideoLesson, VideoProgress, utcnow
from app.routers import learning_video


def course_plan():
    return {"title": "SQL foundations", "introduction": "Learn relational queries through focused lessons and practice.",
            "prerequisites": ["Basic computer familiarity"], "lessons": [
                {"title": f"Query concept {i}", "objective": "Understand and apply one relational query concept."}
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
def video(hub):  # noqa: F811
    app = FastAPI(); app.include_router(learning_video.router)
    app.dependency_overrides.update(hub.client.app.dependency_overrides)
    with TestClient(app) as client:
        yield SimpleNamespace(**vars(hub), api=client)


def new_course(video):
    response = video.api.post('/learning-hub/video', json={"topic": "SQL", "request_id": "video-request-00000001"})
    assert response.status_code == 202, response.text
    return response.json()['id']


def ready_lesson(video):
    identifier = new_course(video)
    course = video.db.get(VideoCourse, identifier)
    course.state, course.plan_json = 'ready', json.dumps(course_plan())
    video.db.commit()
    assert video.api.post(f'/learning-hub/video/{identifier}/lessons/0').status_code == 202
    lesson = video.db.query(VideoLesson).filter_by(course_id=identifier).one()
    content = script(); content['sources'] = [{"title": "PostgreSQL", "url": "https://www.postgresql.org/docs/current/sql-select.html"}]
    content['timings'] = [{"start": i * 25, "end": (i+1)*25} for i in range(4)]
    lesson.state, lesson.content_json, lesson.duration_seconds = 'ready', json.dumps(content), 100
    lesson.video_data = b'private-video-test'
    video.db.commit()
    return identifier, lesson.id, f'/learning-hub/video/{identifier}/lessons/0'


def test_course_idempotency_budgets_and_owner_isolation(video):
    identifier = new_course(video)
    assert new_course(video) == identifier
    assert video.api.post('/learning-hub/video', json={"topic":"Python", "request_id":"video-request-00000001"}).status_code == 409
    for i in range(2):
        assert video.api.post('/learning-hub/video', json={"topic":"SQL", "request_id":f"video-request-new-00{i}"}).status_code == 202
    assert video.api.post('/learning-hub/video', json={"topic":"SQL", "request_id":"video-request-limited"}).status_code == 429
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
        record = video.db.get(VideoProgress, lesson_id)
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
    references = [{"title":"PostgreSQL", "url":"https://www.postgresql.org/docs/current/sql-select.html"}]
    monkeypatch.setattr(learning_ai, 'research', lambda _: ('Official query evidence', references, 'test'))
    monkeypatch.setattr(learning_ai, 'generate_json', lambda *_a, **_k: (course_plan(), 'test'))
    with video.sessions() as db: item = worker.claim(db)
    with video.sessions() as db: assert worker.claim(db) is None
    worker.process(item, video.sessions)
    assert video.api.get(f'/learning-hub/video/{identifier}').json()['status'] == 'ready'
    video.api.post(f'/learning-hub/video/{identifier}/lessons/0')
    def author(task, *_a, **_k):
        return ({"approved":True, "issues":[]} if task.startswith('Review') else script(), 'test')
    monkeypatch.setattr(learning_ai, 'generate_json', author)
    monkeypatch.setattr(worker, 'render_video', lambda content: render_video(content, narrate=lambda _: b'\0'*48000))
    with video.sessions() as db: first = worker.claim(db)
    with video.sessions() as db:
        row = db.get(VideoLesson, first[1]); row.lease_until = utcnow() - timedelta(seconds=1); db.commit()
    with video.sessions() as db: replacement = worker.claim(db)
    assert replacement[1] == first[1] and replacement[2] != first[2]
    worker.process(first, video.sessions)  # A stale worker must not publish.
    worker.process(replacement, video.sessions)
    response = video.api.get(f'/learning-hub/video/{identifier}/lessons/0/media')
    with av.open(io.BytesIO(response.content)) as container:
        assert {stream.type for stream in container.streams} == {'audio','video'}
        assert sum(1 for _ in container.decode(video=0)) == 4


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
    identifier, lesson_id, path = ready_lesson(video)
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
