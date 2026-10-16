"""Private video learning, admission budgets and server-graded knowledge checks."""
from __future__ import annotations

import json
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from pydantic import Field
from sqlalchemy.orm import Session, defer

from app.ai_rate_limit import student_ai_guard
from app.database import get_db
from app.dependencies import require_student
from app.learning_content import ContentModel
from app.learning_video_content import VideoRequest
from app.learning_video_media import captions
from app.models import User, VideoCourse, VideoLesson, VideoProgress, utcnow
from app.routers.learning_hub import generation_available, wake_worker

router = APIRouter(prefix="/learning-hub/video", tags=["Video Learning"])
PRIVATE = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}


def owner_course(db, course_id, user):
    course = db.query(VideoCourse).filter_by(id=course_id, user_id=user.id).first()
    if not course:
        raise HTTPException(404, "Video course not found")
    return course


def owner_lesson(db, course_id, position, user):
    course = owner_course(db, course_id, user)
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


def course_data(db, course):
    rows = db.query(VideoLesson, VideoProgress).options(defer(VideoLesson.video_data)).outerjoin(
        VideoProgress, VideoProgress.lesson_id == VideoLesson.id).filter(
        VideoLesson.course_id == course.id).all()
    lessons = {row.position: (row, progress) for row, progress in rows}
    plan = json.loads(course.plan_json)
    result = {"id": course.id, "title": course.title, "status": course.state,
              "retry_available": course.state == "failed" and course.attempts < 4,
              "error_code": course.error_code, "introduction": plan.get("introduction", ""),
              "prerequisites": plan.get("prerequisites", []), "lessons": [],
              "sources": json.loads(course.sources_json), "created_at": course.created_at.isoformat()}
    for position, outline in enumerate(plan.get("lessons", [])):
        row, progress = lessons.get(position, (None, None))
        result["lessons"].append({**outline, "position": position,
            "status": row.state if row else "not_started", "duration_seconds": row.duration_seconds if row else 0,
            "retry_available": bool(row and row.state == "failed" and row.attempts < 4),
            **progress_data(progress)})
    result["videos_completed"] = sum(item["video_completed"] for item in result["lessons"])
    result["practice_completed"] = sum(item["practice_completed"] for item in result["lessons"])
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


@router.get("")
def library(user: User = Depends(require_student), db: Session = Depends(get_db)):
    rows = db.query(VideoCourse).filter_by(user_id=user.id).order_by(VideoCourse.created_at.desc()).limit(30).all()
    return {"items": [course_data(db, row) for row in rows], "generation_available": generation_available(db)}


@router.post("", status_code=202, dependencies=[Depends(student_ai_guard)])
def create(body: VideoRequest, tasks: BackgroundTasks,
           user: User = Depends(require_student), db: Session = Depends(get_db)):
    db.query(User).filter_by(id=user.id).with_for_update().one()
    existing = db.query(VideoCourse).filter_by(user_id=user.id, request_id=body.request_id).first()
    if existing:
        if json.loads(existing.input_json) != body.model_dump():
            raise HTTPException(409, "This request identifier belongs to another topic")
        return course_data(db, existing)
    if not generation_available(db):
        raise HTTPException(503, "Video research is temporarily unavailable. Try again later.")
    budget(db, user)
    row = VideoCourse(user_id=user.id, request_id=body.request_id, title=body.topic, input_json=body.model_dump_json())
    db.add(row); db.commit(); db.refresh(row)
    tasks.add_task(wake_worker)
    return course_data(db, row)


@router.get("/{course_id}")
def get_course(course_id: str, user: User = Depends(require_student), db: Session = Depends(get_db)):
    return course_data(db, owner_course(db, course_id, user))


@router.post("/{course_id}/retry", dependencies=[Depends(student_ai_guard)])
def retry_course(course_id: str, tasks: BackgroundTasks,
                 user: User = Depends(require_student), db: Session = Depends(get_db)):
    db.query(User).filter_by(id=user.id).with_for_update().one()
    course = owner_course(db, course_id, user)
    if course.state != "failed":
        return course_data(db, course)
    if course.attempts >= 4:
        raise HTTPException(409, "Preparation could not finish after retries. Please try a new path later.")
    if not generation_available(db):
        raise HTTPException(503, "Video preparation is temporarily unavailable")
    budget(db, user)
    course.state, course.error_code, course.available_at = "queued", None, utcnow()
    db.commit(); tasks.add_task(wake_worker)
    return course_data(db, course)


@router.post("/{course_id}/lessons/{position}", status_code=202, dependencies=[Depends(student_ai_guard)])
def prepare(course_id: str, position: int, tasks: BackgroundTasks,
            user: User = Depends(require_student), db: Session = Depends(get_db)):
    db.query(User).filter_by(id=user.id).with_for_update().one()
    course = owner_course(db, course_id, user)
    lessons = json.loads(course.plan_json).get("lessons", [])
    if course.state != "ready" or not 0 <= position < len(lessons):
        raise HTTPException(409, "Wait for the learning path before preparing a lesson")
    existing = db.query(VideoLesson).options(defer(VideoLesson.video_data)).filter_by(course_id=course.id, position=position).first()
    if existing and existing.state != "failed":
        return course_data(db, course)
    if existing and existing.attempts >= 4:
        raise HTTPException(409, "Lesson preparation could not finish after retries. Please try again with a new course later.")
    if not generation_available(db):
        raise HTTPException(503, "Video preparation is temporarily unavailable")
    budget(db, user, lesson=True)
    if existing:
        existing.state, existing.error_code, existing.available_at = "queued", None, utcnow()
        db.commit(); tasks.add_task(wake_worker)
        return course_data(db, course)
    row = VideoLesson(course_id=course.id, position=position, title=lessons[position]["title"])
    db.add(row); db.flush()
    db.add(VideoProgress(lesson_id=row.id))
    db.commit()
    tasks.add_task(wake_worker)
    return course_data(db, course)


@router.get("/{course_id}/lessons/{position}")
def lesson(course_id: str, position: int, user: User = Depends(require_student), db: Session = Depends(get_db)):
    row = owner_lesson(db, course_id, position, user)
    content = json.loads(row.content_json) if row.state == "ready" else {}
    content.pop("solution", None)
    content["quiz"] = [{"question": q["question"], "options": q["options"]} for q in content.get("quiz", [])]
    return {"title": row.title, "status": row.state, "duration_seconds": row.duration_seconds,
            "content": content, **progress_data(db.get(VideoProgress, row.id))}


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
    record = db.query(VideoProgress).filter_by(lesson_id=row.id).with_for_update().one()
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
    record = db.query(VideoProgress).filter_by(lesson_id=row.id).with_for_update().one()
    record.practice_completed = record.practice_completed or all(item["correct"] for item in results)
    db.commit()
    return {"results": results, "solution": content["solution"], **progress_data(record)}
