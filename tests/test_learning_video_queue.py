"""Quota isolation, offline recovery and unpublished render checkpoints."""
import json
from datetime import timedelta

import pytest

from test_learning_video import video, ready_lesson, course_plan, script  # noqa: F401
from test_learning_hub import hub  # noqa: F401
from app import learning_speech, learning_video_worker as worker, learning_video_review as review
from app.models import VideoCourse, VideoLesson, utcnow


def test_quota_wait_does_not_block_another_course(video):
    first, lesson_id, _ = ready_lesson(video)
    row = video.db.get(VideoLesson, lesson_id)
    row.state, row.error_code = 'retrying', 'REVIEW_CAPACITY'
    row.available_at = utcnow() + timedelta(hours=3)
    other = VideoCourse(user_id=video.owner.id, request_id='queue-isolation-other', title='Another course',
                        state='ready', input_json='{}', plan_json=json.dumps(course_plan()))
    video.db.add(other); video.db.flush()
    due = VideoLesson(course_id=other.id, position=0, title='Unblocked lesson')
    video.db.add(due); video.db.commit()
    with video.sessions() as db:
        item = worker.claim(db)
    assert item[0] == 'lesson' and item[1] == due.id
    own = video.api.get(f'/learning-hub/video/{first}').json()
    assert own['preparation_status'] == 'waiting_capacity' and own['next_retry_at']
    assert 'review' in own['preparation_notice']
    other_view = video.api.get(f'/learning-hub/video/{other.id}').json()
    assert other_view['preparation_status'] == 'preparing'
    assert 'waiting for provider' not in other_view['preparation_notice']


def test_offline_voice_reclaims_old_speech_cooldown_immediately(video, monkeypatch):
    _, lesson_id, _ = ready_lesson(video)
    row = video.db.get(VideoLesson, lesson_id)
    row.state, row.error_code = 'retrying', 'NARRATION_CAPACITY'
    row.available_at = utcnow() + timedelta(days=1)
    video.db.commit()
    monkeypatch.setattr(learning_speech, 'enabled', lambda: True)
    monkeypatch.setattr(learning_speech, 'available', lambda: True)
    with video.sessions() as db:
        item = worker.claim(db)
        assert item[1] == lesson_id
        assert db.get(VideoLesson, lesson_id).error_code is None


def test_review_retry_reuses_checked_media_without_publishing_it(video, monkeypatch):
    course_id, lesson_id, path = ready_lesson(video)
    row = video.db.get(VideoLesson, lesson_id)
    course = video.db.get(VideoCourse, course_id)
    course.input_json = json.dumps({'topic':'SQL','curriculum_version':2})
    row.state, row.video_data, row.attempts = 'queued', None, 0
    row.content_json = json.dumps({**script(), 'sources':[], 'content_review':{'passed':True}})
    video.db.commit()
    renders=[]
    monkeypatch.setattr(worker, 'render_video', lambda *_a, **_k: (renders.append(1) or b'checked-render', 12, []))
    monkeypatch.setattr(worker, 'inspect_video', lambda *_a: {'passed':True})
    monkeypatch.setattr(worker, 'review_video', lambda *_a: (_ for _ in ()).throw(review.ReviewCapacityError(60)))
    with video.sessions() as db: item = worker.claim(db)
    worker.process(item, video.sessions)
    video.db.expire_all(); row = video.db.get(VideoLesson, lesson_id)
    assert row.state == 'retrying' and row.video_data == b'checked-render'
    assert video.api.get(path+'/media').status_code == 409
    row.available_at = utcnow() - timedelta(seconds=1); video.db.commit()
    monkeypatch.setattr(worker, 'review_video', lambda *_a: {'passed':True,'version':1,'scenes_checked':4})
    with video.sessions() as db: item = worker.claim(db)
    worker.process(item, video.sessions)
    video.db.expire_all(); row = video.db.get(VideoLesson, lesson_id)
    assert row.state == 'ready' and renders == [1]
    assert json.loads(row.content_json)['audiovisual_review']['passed'] is True


def test_offline_speech_never_calls_remote_speech(monkeypatch):
    from app import learning_video_media as media
    monkeypatch.setattr(learning_speech, 'enabled', lambda: True)
    monkeypatch.setattr(learning_speech, 'synthesize', lambda text: b'local-speech')
    monkeypatch.setattr(media.httpx, 'stream', lambda *_a, **_kw: pytest.fail('Offline narration called a provider'))
    assert media.speak('A local lesson.') == b'local-speech'


def test_daily_review_quota_is_a_wait_not_a_type_error(monkeypatch):
    import httpx
    monkeypatch.setattr(review.ai_provider, '_gemini_key', lambda: 'test-only')
    monkeypatch.setattr(review.httpx, 'post', lambda url, **_kw: httpx.Response(429,
        request=httpx.Request('POST',url), json={'error':{'message':'Daily quota exceeded'}}))
    with pytest.raises(review.ReviewCapacityError) as error:
        review.review_video(b'teaching-media', {'objective':'SQL','scenes':[],'timings':[]})
    assert error.value.retry_seconds == 86400
