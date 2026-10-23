"""Shared topic-only video lessons; private enrollments and viewing/practice progress."""
from __future__ import annotations

import json
import hashlib
import unicodedata
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, Request
from pydantic import Field
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session, defer
from sqlalchemy.orm.attributes import flag_modified

from app.ai_rate_limit import student_ai_guard
from app.database import get_db
from app.dependencies import require_student
from app.learning_content import ContentModel
from app.learning_video_content import VideoRequest
from app.learning_video_media import captions
from app.models import User, VideoCourse, VideoLesson, VideoProgress, VideoEnrollment, VideoViewerProgress, utcnow
from app.routers.learning_hub import generation_available, wake_worker

router = APIRouter(prefix="/learning-hub/video", tags=["Video Learning"])
PRIVATE = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}


def owner_course(db, course_id, user):
    course = db.query(VideoCourse).filter(VideoCourse.id == course_id, or_(
        and_(VideoCourse.shared_key.is_(None), VideoCourse.user_id == user.id),
        and_(VideoCourse.shared_key.is_not(None), db.query(VideoEnrollment).filter(
            VideoEnrollment.course_id == VideoCourse.id, VideoEnrollment.user_id == user.id).exists()))).first()
    if not course:
        raise HTTPException(404, "Video course not found")
    return course


def owner_lesson(db, course_id, position, user):
    course = owner_course(db, course_id, user)
    publication = course_data(db, course, user)
    if not publication["course_ready"]:
        raise HTTPException(409, "Your full course is still being prepared and checked. Return to the course overview.")
    lesson = db.query(VideoLesson).options(defer(VideoLesson.video_data)).filter_by(
        course_id=course.id, position=position).first()
    if not lesson:
        raise HTTPException(404, "Video lesson not found")
    return lesson


def progress_data(progress):
    return {"position_seconds": progress.position_seconds if progress else 0,
            "watched_seconds": progress.watched_seconds if progress else 0,
            "video_completed": bool(progress and progress.video_completed),
            "practice_completed": bool(progress and progress.practice_completed)}


def course_data(db, course, user):
    progress_model = VideoViewerProgress if course.shared_key else VideoProgress
    rows = db.query(VideoLesson, progress_model).options(defer(VideoLesson.video_data)).outerjoin(
        progress_model, and_(progress_model.lesson_id == VideoLesson.id,
            progress_model.user_id == user.id) if course.shared_key else progress_model.lesson_id == VideoLesson.id).filter(
        VideoLesson.course_id == course.id).all()
    lessons = {row.position: (row, progress) for row, progress in rows}
    plan = json.loads(course.plan_json)
    result = {"id": course.id, "title": course.title, "status": course.state,
              "preparation_notice": "",
              "retry_available": course.state == "failed" and course.attempts < 4,
              "error_code": course.error_code, "introduction": plan.get("introduction", ""),
              "prerequisites": plan.get("prerequisites", []), "lessons": [],
              "sources": json.loads(course.sources_json), "created_at": course.created_at.isoformat(),
              "requires_full_preparation": True}
    modules, previous, in_module = [], None, 0
    for position, outline in enumerate(plan.get("lessons", [])):
        # Old flat outlines get neutral two-part sections without changing their
        # media, lesson IDs or student history. New plans have authored subtopics.
        title = outline.get("module_title", "").strip()
        key = title.casefold() if title else f"legacy-{position // 2}"
        if key != previous:
            modules.append({"title": title or f"Module {len(modules)+1}",
                            "number": len(modules)+1, "positions": []})
            in_module = 0
        previous = key
        in_module += 1
        modules[-1]["positions"].append(position)
        row, progress = lessons.get(position, (None, None))
        checks = json.loads(row.content_json) if row and row.state == "ready" else {}
        from app.learning_publication import checks_passed
        quality_checked = checks_passed(checks)
        result["lessons"].append({**outline, "position": position,
            "module_title": modules[-1]["title"], "module_number": len(modules),
            "number": f"{len(modules)}.{in_module}",
            "status": row.state if row else "not_started", "duration_seconds": row.duration_seconds if row else 0,
            "quality_checked": quality_checked,
            "retry_available": bool(row and row.state == "failed" and row.attempts < 4),
            "error_code": row.error_code if row else None,
            "available_at": row.available_at.isoformat() + "Z" if row else None,
            **progress_data(progress)})
    result["videos_completed"] = sum(item["video_completed"] for item in result["lessons"])
    result["practice_completed"] = sum(item["practice_completed"] for item in result["lessons"])
    result["modules"] = modules
    result["ready_parts"] = sum(item["status"] == "ready" for item in result["lessons"])
    result["completed_parts"] = sum(item["video_completed"] and item["practice_completed"] for item in result["lessons"])
    result["checked_parts"] = sum(item["status"] == "ready" and item["quality_checked"] for item in result["lessons"])
    result["course_ready"] = (course.state == "ready" and bool(result["lessons"])
        and result["ready_parts"] == len(result["lessons"])
        and (not result["requires_full_preparation"] or result["checked_parts"] == len(result["lessons"])))
    result["course_completed"] = bool(result["lessons"]) and result["completed_parts"] == len(result["lessons"])
    result["completion_percent"] = round(100 * result["completed_parts"] / len(result["lessons"])) if result["lessons"] else 0
    from app import learning_speech
    now = utcnow()
    pending = [row for row, _progress in rows if row.state in {"queued", "retrying"}]
    offline = learning_speech.enabled() and learning_speech.available()
    runnable = any(row.available_at <= now or offline and row.error_code == "NARRATION_CAPACITY" for row in pending)
    running = course.state == "running" or any(row.state == "running" for row, _progress in rows)
    waiting = [row for row in pending if row.available_at > now]
    result["next_retry_at"] = None
    if result["course_ready"]:
        result["preparation_status"] = "ready"
    elif course.state == "failed" or any(item["status"] == "failed" for item in result["lessons"]):
        result["preparation_status"] = "needs_attention"
        result["preparation_notice"] = "This course needs a preparation repair. Your request and saved progress are preserved. Please contact PlaceAI support."
    elif any(item["status"] == "ready" and not item["quality_checked"] for item in result["lessons"]):
        result["preparation_status"] = "review_required"
        result["preparation_notice"] = "This saved course needs its quality recheck before learning can begin. Your progress is preserved."
    elif running:
        result["preparation_status"] = "preparing"
        result["preparation_notice"] = "Your course is being prepared and checked in the background. You can leave this page."
    elif waiting and not runnable:
        result["preparation_status"] = "waiting_capacity"
        result["next_retry_at"] = min(row.available_at for row in waiting).isoformat() + "Z"
        result["preparation_notice"] = ("Lesson quality review is waiting for provider capacity. Your prepared work is saved."
            if any(row.error_code == "REVIEW_CAPACITY" for row in waiting) else
            "Preparation is waiting to retry. Your completed work is saved.")
    else:
        result["preparation_status"] = "queued"
        result["preparation_notice"] = "Your course is queued for background preparation. You can leave this page and return later."
    return result


def budget(db, user, *, lesson=False):
    """Admission is serialized on the account; global reservations prevent queue bursts."""
    since = utcnow() - timedelta(days=1)
    # A single existing runtime row serializes the global budget, including multiple workers.
    from app.models import LearningRuntime
    db.query(LearningRuntime).filter_by(id=1).with_for_update().first()
    if lesson:
        mine = db.query(VideoLesson).join(VideoCourse).filter(VideoCourse.user_id == user.id,
            VideoLesson.created_at >= since).count()
        total = db.query(VideoLesson).filter(VideoLesson.created_at >= since).count()
        from app.learning_video_worker import storage_used, STORAGE_BUDGET
        pending = db.query(VideoLesson).filter(VideoLesson.state.in_(["queued", "running", "retrying"])).count()
        from app.learning_video_media import MAX_VIDEO_BYTES
        if storage_used(db) + (pending + 1) * MAX_VIDEO_BYTES > STORAGE_BUDGET:
            raise HTTPException(503, "Video storage is at capacity. Your saved lessons remain available.")
        if mine >= 8 or total >= 40:
            raise HTTPException(429, "Video preparation allowance reached. Continue saved lessons and try tomorrow.")
    elif db.query(VideoCourse).filter(VideoCourse.user_id == user.id,
                                     VideoCourse.created_at >= since).count() >= 3:
        raise HTTPException(429, "You can create three video learning paths per day. Continue a saved course.")
    elif db.query(VideoCourse).filter(VideoCourse.created_at >= since).count() >= 30:
        raise HTTPException(429, "Video learning path preparation is busy. Please try tomorrow.")


def topic_key(topic):
    normalized = " ".join(unicodedata.normalize("NFKC", topic).split()).casefold()
    if len(normalized) < 2:
        raise HTTPException(422, "Enter a topic with at least two characters")
    return normalized, hashlib.sha256(("shared-full-course-v2:en:" + normalized).encode()).hexdigest()


@router.get("")
def library(user: User = Depends(require_student), db: Session = Depends(get_db)):
    rows = db.query(VideoCourse).filter(or_(
        and_(VideoCourse.shared_key.is_(None), VideoCourse.user_id == user.id),
        db.query(VideoEnrollment).filter(VideoEnrollment.course_id == VideoCourse.id,
            VideoEnrollment.user_id == user.id).exists())).order_by(VideoCourse.created_at.desc()).limit(100).all()
    return {"items": [course_data(db, row, user) for row in rows], "generation_available": generation_available(db)}


@router.post("", status_code=202)
def create(body: VideoRequest, request: Request, tasks: BackgroundTasks,
           user: User = Depends(require_student), db: Session = Depends(get_db)):
    normalized, key = topic_key(body.topic)
    # Rate-limit only possible cache misses, before acquiring transaction locks:
    # the durable limiter commits its own counters.
    if not db.query(VideoCourse.id).filter_by(shared_key=key).first():
        student_ai_guard(request, user, db)
    db.query(User).filter_by(id=user.id).with_for_update().one()
    from app.models import LearningRuntime
    db.query(LearningRuntime).filter_by(id=1).with_for_update().one()
    prior = db.query(VideoEnrollment).filter_by(user_id=user.id, request_id=body.request_id).first()
    if prior:
        row = db.get(VideoCourse, prior.course_id)
        if row.shared_key != key:
            raise HTTPException(409, "This request identifier belongs to another topic")
        return course_data(db, row, user)
    row = db.query(VideoCourse).filter_by(shared_key=key).first()
    if not row:
        if not generation_available(db):
            raise HTTPException(503, "Video research is temporarily unavailable. Saved lessons remain available.")
        budget(db, user)
        row = VideoCourse(user_id=user.id, shared_key=key, request_id=body.request_id,
            title=normalized, input_json=json.dumps({"topic": normalized, "curriculum_version": 2}))
        db.add(row); db.flush()
        tasks.add_task(wake_worker)
    enrollment = db.get(VideoEnrollment, (user.id, row.id))
    if not enrollment:
        db.add(VideoEnrollment(user_id=user.id, course_id=row.id, request_id=body.request_id))
    db.commit()
    return course_data(db, row, user)


@router.get("/{course_id}")
def get_course(course_id: str, user: User = Depends(require_student), db: Session = Depends(get_db)):
    return course_data(db, owner_course(db, course_id, user), user)


@router.post("/{course_id}/retry", dependencies=[Depends(student_ai_guard)])
def retry_course(course_id: str, tasks: BackgroundTasks,
                 user: User = Depends(require_student), db: Session = Depends(get_db)):
    db.query(User).filter_by(id=user.id).with_for_update().one()
    course = owner_course(db, course_id, user)
    if course.state != "failed":
        return course_data(db, course, user)
    if course.attempts >= 4:
        raise HTTPException(409, "Preparation could not finish after retries. Please try a new path later.")
    if not generation_available(db):
        raise HTTPException(503, "Video preparation is temporarily unavailable")
    budget(db, user)
    course.state, course.error_code, course.available_at = "queued", None, utcnow()
    db.commit(); tasks.add_task(wake_worker)
    return course_data(db, course, user)


@router.post("/{course_id}/lessons/{position}", status_code=202)
def prepare(course_id: str, position: int, request: Request, tasks: BackgroundTasks,
            user: User = Depends(require_student), db: Session = Depends(get_db)):
    db.query(User).filter_by(id=user.id).with_for_update().one()
    course = owner_course(db, course_id, user)
    db.query(VideoCourse).filter_by(id=course.id).with_for_update().one()
    lessons = json.loads(course.plan_json).get("lessons", [])
    if course.state != "ready" or not 0 <= position < len(lessons):
        raise HTTPException(409, "Wait for the learning path before preparing a lesson")
    existing = db.query(VideoLesson).options(defer(VideoLesson.video_data)).populate_existing().filter_by(course_id=course.id, position=position).first()
    if existing and existing.state != "failed":
        return course_data(db, course, user)
    if existing and existing.attempts >= 4:
        raise HTTPException(409, "Lesson preparation could not finish after retries. Please try again with a new course later.")
    if not generation_available(db):
        raise HTTPException(503, "Video preparation is temporarily unavailable")
    student_ai_guard(request, user, db)
    # The limiter committed; reacquire the global course lock and recheck after
    # another student's possible concurrent prepare request.
    db.query(VideoCourse).filter_by(id=course.id).with_for_update().one()
    existing = db.query(VideoLesson).options(defer(VideoLesson.video_data)).populate_existing().filter_by(course_id=course.id, position=position).first()
    if existing and existing.state != "failed":
        return course_data(db, course, user)
    if existing and existing.attempts >= 4:
        raise HTTPException(409, "Lesson preparation could not finish after retries")
    budget(db, user, lesson=True)
    if existing:
        existing.state, existing.error_code, existing.available_at = "queued", None, utcnow()
        db.commit(); tasks.add_task(wake_worker)
        return course_data(db, course, user)
    row = VideoLesson(course_id=course.id, position=position, title=lessons[position]["title"])
    db.add(row); db.flush()
    if not course.shared_key:
        db.add(VideoProgress(lesson_id=row.id))
    db.commit()
    tasks.add_task(wake_worker)
    return course_data(db, course, user)


def viewer_record(db, row, user, *, lock=False):
    course = db.get(VideoCourse, row.course_id)
    if not course.shared_key:
        query = db.query(VideoProgress).filter_by(lesson_id=row.id)
    else:
        # Account lock serializes the first progress insert across tabs.
        if lock:
            db.query(User).filter_by(id=user.id).with_for_update().one()
        query = db.query(VideoViewerProgress).filter_by(user_id=user.id, lesson_id=row.id)
    record = (query.with_for_update() if lock else query).first()
    if record is None and lock:
        record = (VideoViewerProgress(user_id=user.id, lesson_id=row.id) if course.shared_key
                  else VideoProgress(lesson_id=row.id))
        db.add(record); db.flush()
    return record


@router.get("/{course_id}/lessons/{position}")
def lesson(course_id: str, position: int, user: User = Depends(require_student), db: Session = Depends(get_db)):
    row = owner_lesson(db, course_id, position, user)
    content = json.loads(row.content_json) if row.state == "ready" else {}
    content.pop("solution", None)
    content["quiz"] = [{"question": q["question"], "options": q["options"]} for q in content.get("quiz", [])]
    return {"title": row.title, "status": row.state, "duration_seconds": row.duration_seconds,
            "content": content, **progress_data(viewer_record(db, row, user))}


@router.get("/{course_id}/lessons/{position}/media")
def media(course_id: str, position: int, user: User = Depends(require_student), db: Session = Depends(get_db)):
    row = owner_lesson(db, course_id, position, user)
    if row.state != "ready":
        raise HTTPException(409, "The lesson video is still being prepared")
    data = db.query(VideoLesson.video_data).filter_by(id=row.id).scalar()
    if not data:
        raise HTTPException(404, "Lesson video is unavailable")
    return Response(bytes(data), media_type="video/mp4", headers=PRIVATE)


@router.get("/{course_id}/lessons/{position}/captions")
def subtitles(course_id: str, position: int, user: User = Depends(require_student), db: Session = Depends(get_db)):
    row = owner_lesson(db, course_id, position, user)
    if row.state != "ready":
        raise HTTPException(409, "Lesson captions are still being prepared")
    return Response(captions(json.loads(row.content_json)), media_type="text/vtt", headers=PRIVATE)


class Playback(ContentModel):
    position_seconds: float = Field(ge=0, le=480, allow_inf_nan=False)


@router.put("/{course_id}/lessons/{position}/progress")
def progress(course_id: str, position: int, body: Playback,
             user: User = Depends(require_student), db: Session = Depends(get_db)):
    row = owner_lesson(db, course_id, position, user)
    if row.state != "ready":
        raise HTTPException(409, "Lesson is not ready")
    record = viewer_record(db, row, user, lock=True)
    now = utcnow()
    endpoint = min(body.position_seconds, row.duration_seconds)
    distance = endpoint - record.position_seconds
    intervals = json.loads(record.coverage_json)
    # A seek saves resume position but never awards watched time. Playback up to 2x is supported.
    allowance = min(30, max(0, (now - record.updated_at).total_seconds()) * 2.5 + 2)
    if 0 < distance <= allowance:
        intervals.append([record.position_seconds, endpoint])
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1] + .25:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    record.coverage_json = json.dumps(merged)
    record.watched_seconds = sum(end - start for start, end in merged)
    record.position_seconds, record.updated_at = endpoint, now
    record.video_completed = record.video_completed or record.watched_seconds >= row.duration_seconds * .9
    db.commit()
    return progress_data(record)


class Answers(ContentModel):
    answers: list[int] = Field(min_length=3, max_length=3)


@router.post("/{course_id}/lessons/{position}/practice")
def practice(course_id: str, position: int, body: Answers,
             user: User = Depends(require_student), db: Session = Depends(get_db)):
    row = owner_lesson(db, course_id, position, user)
    if row.state != "ready":
        raise HTTPException(409, "Lesson is not ready")
    content = json.loads(row.content_json)
    results = []
    for answer, question in zip(body.answers, content["quiz"]):
        if not 0 <= answer < len(question["options"]):
            raise HTTPException(422, "Select one of the available answers")
        results.append({"correct": answer == question["answer"], "answer": question["answer"],
                        "explanation": question["explanation"]})
    record = viewer_record(db, row, user, lock=True)
    record.practice_completed = record.practice_completed or all(item["correct"] for item in results)
    # This timestamp is the playback clock. A practice submission must not reset
    # it or the next legitimate timeupdate looks like a seek and loses coverage.
    flag_modified(record, "updated_at")
    db.commit()
    return {"results": results, "solution": content["solution"], **progress_data(record)}
