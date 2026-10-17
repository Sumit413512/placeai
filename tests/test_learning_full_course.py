import json

from test_learning_hub import hub  # noqa: F401
from test_learning_video import video, new_course, course_plan  # noqa: F401
from app import learning_ai, learning_video_worker as worker
from app.learning_video_content import SQL_MODULES
from app.models import VideoCourse, VideoLesson


def full_plan():
    raw = course_plan()
    raw['title'] = 'SQL: foundations to advanced applications'
    raw['lessons'] = [dict(title=f'{name} part {part}', module_title=name,
        objective=f'Apply {name.lower()} through a focused example and explain the result.')
        for name in SQL_MODULES for part in (1, 2)]
    return raw


def test_full_syllabus_is_reviewed_before_admitting_every_lesson(video, monkeypatch):
    identifier = new_course(video)
    calls = []
    monkeypatch.setattr(learning_ai, 'research', lambda _: ('Official evidence', [], 'test'))
    def generate(task, *_args, **_kwargs):
        calls.append(task)
        return ({'approved': True, 'issues': []} if task.startswith('Review') else full_plan(), 'test')
    monkeypatch.setattr(learning_ai, 'generate_json', generate)
    with video.sessions() as db:
        item = worker.claim(db)
    worker.process(item, video.sessions)
    result = video.api.get(f'/learning-hub/video/{identifier}').json()
    assert result['requires_full_preparation'] and not result['course_ready']
    assert len(result['modules']) == 14 and len(result['lessons']) == 28
    assert result['lessons'][-1]['number'] == '14.2'
    assert len(calls) == 2 and calls[1].startswith('Review')
    assert video.db.query(VideoLesson).count() == 28
    assert video.api.get(f'/learning-hub/video/{identifier}/lessons/0').status_code == 409


def test_failed_syllabus_review_does_not_admit_or_publish_lessons(video, monkeypatch):
    identifier = new_course(video)
    monkeypatch.setattr(learning_ai, 'research', lambda _: ('Official evidence', [], 'test'))
    monkeypatch.setattr(learning_ai, 'generate_json', lambda task, *_a, **_k: (
        {'approved': False, 'issues': ['Missing prerequisite explanation']} if task.startswith('Review') else full_plan(), 'test'))
    with video.sessions() as db:
        item = worker.claim(db)
    worker.process(item, video.sessions)
    video.db.expire_all()
    row = video.db.get(VideoCourse, identifier)
    assert row.state == 'retrying' and row.error_code == 'CONTENT_CHECK'
    assert json.loads(row.plan_json) == {}
    assert video.db.query(VideoLesson).count() == 0
