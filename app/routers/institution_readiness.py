"""Assign and report on published video lessons using institution-scoped evidence."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session, defer

from app import lesson_readiness
from app.array_readiness_models import InstitutionLessonReadiness as Assignment
from app.database import get_db
from app.dependencies import require_institution_admin, require_student
from app.models import StudentProfile, User, VideoCourse, VideoEnrollment, VideoLesson
from app.routers.learning_video import course_data, demo_course_filter

router = APIRouter(prefix="/lesson-readiness", tags=["Lesson readiness"])
PAGE_SIZE = 50


def active_institution(db, user):
    org = lesson_readiness.institution(db, user)
    if org is None:
        raise HTTPException(403, "Your account is not linked to an active institution.")
    return org


def institution_courses(db, org_id):
    member_ids = lesson_readiness.roster(db, org_id).with_entities(User.id)
    enrolled = db.query(VideoEnrollment).filter(
        VideoEnrollment.course_id == VideoCourse.id, VideoEnrollment.user_id.in_(member_ids),
    ).exists()
    return db.query(VideoCourse).filter(
        VideoCourse.shared_key.is_not(None), VideoCourse.state == "ready",
        VideoCourse.editorial_status == "approved", or_(demo_course_filter(), enrolled),
    )


def course_lessons(db, course, user):
    publication = course_data(db, course, user)
    if not publication["course_ready"]:
        return {}
    positions = [lesson["position"] for lesson in publication["lessons"]]
    rows = db.query(VideoLesson).options(defer(VideoLesson.video_data)).filter(
        VideoLesson.course_id == course.id, VideoLesson.position.in_(positions),
    ).order_by(VideoLesson.position)
    lessons = {}
    for row in rows:
        quiz = lesson_readiness.questions(json.loads(row.content_json))
        if quiz:
            lessons[row.position] = (row, quiz, lesson_readiness.version(quiz))
    return lessons


@router.get("/institution/courses")
def courses(user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    org = active_institution(db, user)
    result = []
    for course in institution_courses(db, org.id).order_by(VideoCourse.title, VideoCourse.id):
        lessons = course_lessons(db, course, user)
        if lessons:
            result.append({"id": course.id, "title": course.title, "lessons": [
                {"position": row.position, "title": row.title} for row, _, _ in lessons.values()
            ]})
    return result


def course_and_students(db, user, course_id):
    org = active_institution(db, user)
    course = institution_courses(db, org.id).filter(VideoCourse.id == course_id).first()
    if not course:
        raise HTTPException(404, "Course not available to this institution.")
    students = lesson_readiness.roster(db, org.id)
    if not db.query(VideoCourse.id).filter(VideoCourse.id == course.id, demo_course_filter()).first():
        students = students.filter(db.query(VideoEnrollment).filter(
            VideoEnrollment.course_id == course.id, VideoEnrollment.user_id == User.id,
        ).exists())
    return org, course, students


@router.get("/institution/courses/{course_id}/lessons/{position}")
def report(course_id: str, position: int, search: str = Query(default="", max_length=80),
           offset: int = Query(default=0, ge=0), user: User = Depends(require_institution_admin),
           db: Session = Depends(get_db)):
    org, course, students = course_and_students(db, user, course_id)
    lesson = course_lessons(db, course, user).get(position)
    if lesson is None:
        raise HTTPException(404, "Readiness is unavailable for this lesson.")
    row, quiz, revision = lesson
    baseline, followup = quiz["diagnostic"]["answer"], quiz["followup"]["answer"]
    students = students.outerjoin(Assignment, and_(
        Assignment.student_id == User.id, Assignment.organization_id == org.id,
        Assignment.lesson_id == row.id, Assignment.question_version == revision,
    ))
    needs_help = and_(Assignment.followup_answer.is_not(None), Assignment.followup_answer != followup)
    summary = students.with_entities(
        func.count(Assignment.student_id), func.count(Assignment.diagnostic_answer),
        func.count(Assignment.followup_answer),
        func.count(case((and_(Assignment.diagnostic_answer != baseline, Assignment.followup_answer == followup), 1))),
        func.count(case((needs_help, 1))),
    ).one()
    if search.strip():
        term = search.strip().lower()
        students = students.filter(or_(func.lower(User.username).contains(term, autoescape=True),
                                       func.lower(StudentProfile.full_name).contains(term, autoescape=True)))
    rows = students.add_entity(Assignment).order_by(
        case((needs_help, 0), (and_(Assignment.student_id.is_not(None), Assignment.followup_answer.is_(None)), 1),
             else_=2), User.username, User.id,
    ).offset(offset).limit(PAGE_SIZE + 1).all()
    return {
        "assigned": summary[0], "started": summary[1], "reassessed": summary[2],
        "improved": summary[3], "needs_help": summary[4], "has_more": len(rows) > PAGE_SIZE,
        "students": [{
            "id": student.id, "name": profile.full_name or student.username, "assigned": attempt is not None,
            "diagnostic_correct": attempt.diagnostic_answer == baseline
            if attempt and attempt.diagnostic_answer is not None else None,
            "followup_correct": attempt.followup_answer == followup
            if attempt and attempt.followup_answer is not None else None,
        } for student, profile, attempt in rows[:PAGE_SIZE]],
    }


@router.put("/institution/courses/{course_id}/assignments/{student_id}", status_code=204)
def assign(course_id: str, student_id: str, position: int | None = Query(default=None, ge=0),
           user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    org, course, students = course_and_students(db, user, course_id)
    if not students.filter(User.id == student_id).with_for_update(of=User).first():
        raise HTTPException(404, "Student does not have access to this course in your institution.")
    lessons = course_lessons(db, course, user)
    if position is not None:
        lessons = {position: lessons[position]} if position in lessons else {}
    if not lessons:
        raise HTTPException(404, "No published readiness lessons were found.")
    previous = {(row.lesson_id, row.question_version) for row in db.query(
        Assignment.lesson_id, Assignment.question_version,
    ).filter_by(organization_id=org.id, student_id=student_id).filter(
        Assignment.lesson_id.in_([row.id for row, _, _ in lessons.values()]),
    )}
    for row, _, revision in lessons.values():
        if (row.id, revision) not in previous:
            db.add(Assignment(organization_id=org.id, student_id=student_id,
                              lesson_id=row.id, question_version=revision))
    db.commit()


@router.get("/me")
def my_assignments(user: User = Depends(require_student), db: Session = Depends(get_db)):
    org = lesson_readiness.institution(db, user)
    if not org or not lesson_readiness.roster(db, org.id).filter(User.id == user.id).first():
        return []
    enrolled = db.query(VideoEnrollment).filter(
        VideoEnrollment.course_id == VideoCourse.id, VideoEnrollment.user_id == user.id,
    ).exists()
    available = db.query(VideoCourse).filter(
        VideoCourse.shared_key.is_not(None), VideoCourse.state == "ready",
        VideoCourse.editorial_status == "approved", or_(demo_course_filter(), enrolled),
        db.query(Assignment).join(VideoLesson, VideoLesson.id == Assignment.lesson_id).filter(
            VideoLesson.course_id == VideoCourse.id, Assignment.student_id == user.id,
            Assignment.organization_id == org.id,
        ).exists(),
    ).order_by(VideoCourse.title, VideoCourse.id)
    attempts = {(item.lesson_id, item.question_version): item for item in db.query(Assignment).filter_by(
        student_id=user.id, organization_id=org.id,
    )}
    result = []
    for course in available:
        for row, _, revision in course_lessons(db, course, user).values():
            item = attempts.get((row.id, revision))
            if item:
                result.append({"course_id": course.id, "course": course.title, "position": row.position,
                               "lesson": row.title, "complete": item.followup_answer is not None})
    return result
