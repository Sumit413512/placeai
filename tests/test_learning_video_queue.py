"""Quota isolation, offline recovery and unpublished render checkpoints."""
import json
import sys
import subprocess
from datetime import timedelta

import pytest

from test_learning_video import video, ready_lesson, course_plan, script  # noqa: F401
from test_learning_hub import hub  # noqa: F401
from app import learning_speech, learning_video_worker as worker, learning_video_review as review
from app.models import VideoCourse, VideoLesson, VideoNarration, utcnow


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


def test_crashed_admitted_lease_ignores_pre_admission_cooldown(video):
    _, lesson_id, _ = ready_lesson(video)
    row = video.db.get(VideoLesson, lesson_id)
    row.state, row.error_code, row.attempts = 'running', None, 1
    row.lease_until = utcnow() - timedelta(seconds=1)
    row.available_at = utcnow() + timedelta(days=1)
    video.db.commit()
    with video.sessions() as db:
        assert worker.claim(db)[1] == lesson_id


def test_narration_rejects_embedded_null_without_running_native_code():
    with pytest.raises(ValueError, match='Invalid lesson narration'):
        learning_speech.synthesize('SQL\0 hidden text')


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux runtime memory accounting')
def test_voice_memory_measurement_excludes_the_build_launcher():
    parent = """
import subprocess, sys
allocated = bytearray(128 * 1024 * 1024)
print(subprocess.check_output([sys.executable, '-c',
    'from app.learning_speech import linux_peak_mib; print(linux_peak_mib())'], text=True))
"""
    measured = float(subprocess.check_output([sys.executable, '-c', parent], text=True).strip())
    assert 0 < measured < 80


def test_all_narration_finishes_before_encoder_starts(monkeypatch):
    from app import learning_video_media as media
    events = []
    def narrate(text):
        events.append(text)
        return b'\1\0' * media.RATE
    def encode(content, read):
        assert events == ['first scene', 'second scene']
        assert read('first scene') == b'\1\0' * media.RATE
        assert read('second scene') == b'\1\0' * media.RATE
        return b'mp4', 2, []
    monkeypatch.setattr(media, '_encode_video', encode)
    assert media.render_video({'scenes':[{'narration':'first scene'},
        {'narration':'second scene'}]}, narrate=narrate)[0] == b'mp4'


@pytest.mark.parametrize('review_error', [review.ReviewCapacityError(60), RuntimeError('VIDEO_REVIEW_INCOMPLETE')])
def test_review_retry_reuses_checked_media_without_publishing_it(video, monkeypatch, review_error):
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
    monkeypatch.setattr(worker, 'review_video', lambda *_a: (_ for _ in ()).throw(review_error))
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
    assert 60 <= error.value.retry_seconds <= 86400
    from app.learning_ai import next_daily_quota_reset_seconds
    assert abs(error.value.retry_seconds - next_daily_quota_reset_seconds()) <= 5


def test_rejected_lesson_keeps_correction_feedback_and_removes_only_its_generated_checkpoints(video, monkeypatch):
    _, lesson_id, _ = ready_lesson(video)
    row = video.db.get(VideoLesson, lesson_id)
    row.state = 'queued'
    video.db.add(VideoNarration(lesson_id=lesson_id, scene_key='obsolete-audio', audio_data=b'rejected-generated-audio'))
    video.db.commit()
    monkeypatch.setattr(worker, 'review_video', lambda *_: (_ for _ in ()).throw(
        review.LessonReviewRejected(['Scene 2 diagram direction contradicts the explanation'])))
    with video.sessions() as db: item = worker.claim(db)
    worker.process(item, video.sessions)
    video.db.expire_all(); row = video.db.get(VideoLesson, lesson_id)
    assert row.state == 'retrying' and row.video_data is None
    assert 'Scene 2' in json.loads(row.content_json)['revision_feedback'][0]
    assert video.db.query(VideoNarration).filter_by(lesson_id=lesson_id).count() == 0
    assert video.db.query(VideoLesson).filter_by(state='ready').count() == 3


def test_checked_mp4_review_preempts_new_authoring_and_keeps_media_private(video):
    course_id, lesson_id, path = ready_lesson(video)
    checked = video.db.get(VideoLesson, lesson_id)
    checked.state = "queued"
    checked.available_at = utcnow() - timedelta(minutes=2)
    checked.content_json = json.dumps({**script(),
        "content_review":{"passed": True}, "media_review":{"passed": True}})
    checked.video_data = b"durably-checked-private-mp4"
    newer = VideoCourse(user_id=video.owner.id, request_id='review-priority-new-course',
                        title='Waiting authoring course', state='ready',
                        input_json='{}', plan_json=json.dumps(course_plan()))
    video.db.add(newer); video.db.flush()
    to_author = VideoLesson(course_id=newer.id, position=0,
                            title='New authoring task', state='queued')
    to_author.available_at = utcnow() - timedelta(hours=4)
    video.db.add(to_author); video.db.commit()
    with video.sessions() as db:
        item = worker.claim(db)
    assert item[0] == 'lesson' and item[1] == lesson_id
    assert video.api.get(path+'/media').status_code == 409


def test_shared_author_429_cooldown_stops_new_requests_but_not_review(video):
    _, lesson_id, _ = ready_lesson(video, full_ready=False)
    author = video.db.get(VideoLesson, lesson_id)
    author.state, author.error_code, author.video_data = "retrying", "AUTHOR_CAPACITY", None
    author.content_json = "{}"
    author.available_at = utcnow() + timedelta(minutes=20)
    video.db.commit()
    other = VideoCourse(user_id=video.owner.id, request_id='review-priority-other-course',
                        title='Other authoring', state='ready',
                        input_json='{}', plan_json=json.dumps(course_plan()))
    video.db.add(other); video.db.flush()
    queued = VideoLesson(course_id=other.id, position=0, title='Not while 429')
    video.db.add(queued); video.db.commit()
    with video.sessions() as db:
        assert worker.claim(db) is None  # Do not hammer one shared provider.

    # A saved, locally checked video uses a distinct review stage and should
    # continue to completion even while the authoring model is rate-limited.
    review_task = VideoLesson(course_id=other.id, position=1, title='Needs audio-visual audit',
                              state="queued", video_data=b"checked-original")
    review_task.content_json = json.dumps({**script(),
       "content_review":{"passed":True}, "media_review":{"passed":True}})
    video.db.add(review_task); video.db.commit()
    with video.sessions() as db:
        item = worker.claim(db)
    assert item[1] == review_task.id


def test_author_quota_earliest_due_job_probes_even_with_other_long_waits(video):
    _, first_id, _ = ready_lesson(video, full_ready=False)
    course = video.db.get(VideoLesson, first_id).course_id
    first = video.db.get(VideoLesson, first_id)
    first.state, first.error_code, first.attempts = 'retrying','AUTHOR_CAPACITY',1
    first.available_at = utcnow() - timedelta(minutes=2)
    first.video_data, first.content_json = None, '{}'
    later = VideoLesson(course_id=course, position=1, title='Another held author')
    later.state, later.error_code = 'retrying','AUTHOR_CAPACITY'
    later.available_at = utcnow() + timedelta(hours=4)
    video.db.add(later); video.db.commit()
    with video.sessions() as db:
        item = worker.claim(db)
    assert item[1] == first_id
    assert video.db.get(VideoLesson, later.id).state == "retrying"


def test_llm_429_uses_provider_retry_hint_without_forcing_one_hour():
    from types import SimpleNamespace
    from app.learning_ai import (LearningCapacityError, provider_retry_seconds,
                                 next_daily_quota_reset_seconds)
    assert provider_retry_seconds(SimpleNamespace(
        details=[{'retryDelay':'27s'}], message='RESOURCE_EXHAUSTED')) == 30
    assert provider_retry_seconds(SimpleNamespace(
        response=SimpleNamespace(headers={'retry-after':'45'}), message='rate limited')) == 48
    assert 60 <= provider_retry_seconds(SimpleNamespace(
        message='Requests per day quota exhausted')) <= 86400
    from datetime import datetime, timezone
    # Nov 12 in Los Angeles reaches midnight at Nov 13, 08:00 UTC.
    assert next_daily_quota_reset_seconds(
        datetime(2026,11,13,7,59,0,tzinfo=timezone.utc)) == 150
    assert provider_retry_seconds(SimpleNamespace(message='Resource exhausted')) == 3600
    assert LearningCapacityError(29).retry_seconds == 29
    assert LearningCapacityError(999999).retry_seconds == 86400
