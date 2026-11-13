"""Regressions for the DSA1 authoring-429 bottleneck.

No paid model, live credentials, media upload or learner records are used.
"""
import json
from datetime import timedelta

from app import learning_ai
from app import learning_video_worker as worker
from app.models import VideoCourse, VideoLesson, utcnow
from test_learning_video import ready_lesson, script


def _requeue_lesson(video):
    course_id, lesson_id, path = ready_lesson(video, full_ready=False)
    lesson = video.db.get(VideoLesson, lesson_id)
    lesson.state, lesson.video_data, lesson.content_json = "queued", None, "{}"
    lesson.attempts, lesson.error_code = 0, None
    lesson.editorial_status = "generating"
    video.db.commit()
    return course_id, lesson_id, path


def test_author_429_pauses_all_unwritten_lessons_without_consuming_retries(video, monkeypatch):
    course_id, lesson_id, _ = _requeue_lesson(video)
    course = video.db.get(VideoCourse, course_id)
    second = VideoLesson(course_id=course_id, position=1, title="Additional DSA concept",
                         state="queued", available_at=utcnow())
    video.db.add(second)
    video.db.commit()
    monkeypatch.setattr(learning_ai, "research", lambda *_args: (
        "A" * 120, [{"url":"https://example.org/docs", "title":"Public reference"}], "test"))
    monkeypatch.setattr(learning_ai, "generate_json", lambda *_args, **_kw: (
        (_ for _ in ()).throw(learning_ai.LearningCapacityError(93))))
    with video.sessions() as db:
        item = worker.claim(db)
    assert item[1] == lesson_id
    worker.process(item, video.sessions)
    video.db.expire_all()

    first = video.db.get(VideoLesson, lesson_id)
    other = video.db.get(VideoLesson, second.id)
    for row in (first, other):
        assert row.state == "retrying" and row.error_code == "AUTHOR_CAPACITY"
        assert row.available_at >= utcnow() + timedelta(seconds=75)
        assert row.attempts == 0
        assert not row.video_data
    assert "_research_checkpoint" in json.loads(first.content_json)
    assert video.db.get(VideoCourse, course_id).state == "ready"
    # Do not make another paid provider request when the quota is still paused.
    with video.sessions() as db:
        assert worker.claim(db) is None


def test_author_retry_reuses_researched_sources_and_does_not_repeat_search(video, monkeypatch):
    course_id, lesson_id, _ = _requeue_lesson(video)
    # Exercise the legacy compatible teaching script to focus this test on
    # research checkpoint/retry behavior, not the independent animation tests.
    video.db.get(VideoCourse, course_id).shared_key = None
    video.db.commit()
    research_calls = []
    author_calls = []
    citations = [{"url": "https://example.org/official", "title": "Official reference"}]

    def research(_subject):
        research_calls.append(1)
        return "Evidence about the SQL SELECT clause, tables and row projections. " * 3, citations, "test"

    def author(task, *_a, **_k):
        author_calls.append(1)
        if len(author_calls) == 1:
            raise learning_ai.LearningCapacityError(35)
        return ({"approved": True, "issues": []} if task.startswith("Review")
                else script(), "test")

    monkeypatch.setattr(learning_ai, "research", research)
    monkeypatch.setattr(learning_ai, "generate_json", author)
    monkeypatch.setattr(worker, "render_video", lambda *_a, **_kw: (
        b"isolated-private-mp4", 1, [{"start":0, "end":1}] * 4))
    monkeypatch.setattr(worker, "inspect_video", lambda *_a, **_kw: {"passed": True})
    monkeypatch.setattr(worker, "review_video", lambda *_a, **_kw: {"passed": True})

    with video.sessions() as db:
        item = worker.claim(db)
    worker.process(item, video.sessions)
    assert len(research_calls) == len(author_calls) == 1
    video.db.expire_all()
    row = video.db.get(VideoLesson, lesson_id)
    assert row.state == "retrying"
    assert json.loads(row.content_json)["_research_checkpoint"]["sources"] == citations
    row.available_at = utcnow() - timedelta(seconds=2)
    video.db.commit()
    with video.sessions() as db:
        next_item = worker.claim(db)
    assert next_item and next_item[1] == lesson_id
    worker.process(next_item, video.sessions)
    video.db.expire_all()
    row = video.db.get(VideoLesson, lesson_id)
    assert row.state == "ready"
    assert row.video_data == b"isolated-private-mp4"
    assert len(research_calls) == 1
    assert len(author_calls) == 3  # once quota-limited, then authored + reviewed
    assert "research_checkpoint" not in json.loads(row.content_json)
