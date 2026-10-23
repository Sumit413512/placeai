"""Audited, bounded recovery; existing answers, media and progress are retained."""
import json
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.orm import defer

from app.learning_publication import checks_passed
from app.models import (AssessmentJob, AuditEvent, LearningNotebook, LearningRuntime,
                        User, UserRole, VideoCourse, VideoLesson, utcnow)
from app.services import record_audit

# Staff-only repair admission; ordinary new-lesson limits remain unchanged.
MAINTENANCE_PARTS_PER_DAY = 48


def overview(db):
    courses = []
    for course in db.query(VideoCourse).order_by(VideoCourse.created_at).limit(100).all():
        lessons = db.query(VideoLesson).options(defer(VideoLesson.video_data)).filter_by(course_id=course.id).all()
        total = len(json.loads(course.plan_json).get('lessons', []))
        failed = sum(row.state == 'failed' for row in lessons)
        unreviewed = sum(row.state == 'ready' and not checks_passed(json.loads(row.content_json)) for row in lessons)
        missing = max(0, total-len(lessons))
        if course.state == 'failed' or failed or unreviewed or missing:
            courses.append({'id': course.id, 'title': course.title, 'status': course.state,
                            'failed': failed, 'unreviewed': unreviewed, 'missing': missing})
    return {'courses': courses,
            'assessments': [{'id': row.interview_id, 'error_code': row.error_code, 'attempts': row.attempts}
                for row in db.query(AssessmentJob).filter_by(state='failed').order_by(AssessmentJob.created_at).limit(100).all()],
            'notes': [{'id': row.id, 'title': row.title, 'error_code': row.error_code}
                for row in db.query(LearningNotebook).filter_by(state='failed').order_by(LearningNotebook.created_at).limit(100).all()]}


def recover(db, actor, kind, identifier):
    now = utcnow()
    # Serialize admission with the same row used by the generation budget.
    db.query(LearningRuntime).filter_by(id=1).with_for_update().one()
    prior = db.query(AuditEvent.id).filter(AuditEvent.action == 'processing.recovery',
        AuditEvent.entity_id == identifier, AuditEvent.created_at > now-timedelta(minutes=30)).first()
    if prior:
        raise HTTPException(409, 'Recovery was already requested recently. Allow processing to finish before retrying.')
    changed = 0
    if kind == 'courses':
        course = db.query(VideoCourse).filter_by(id=identifier).with_for_update().first()
        if not course:
            raise HTTPException(404, 'Course not found')
        if course.state == 'running':
            raise HTTPException(409, 'This course is already being prepared')
        if course.state == 'failed':
            course.state, course.attempts, course.error_code = 'queued', 0, None
            course.available_at, course.lease_until, course.lease_token = now, None, None
            changed += 1
        from app.learning_video_worker import STORAGE_BUDGET, storage_used
        from app.learning_video_media import MAX_VIDEO_BYTES
        pending = db.query(VideoLesson).filter(VideoLesson.state.in_(['queued','running','retrying'])).count()
        recent = db.query(AuditEvent).filter(AuditEvent.action == 'processing.recovery', AuditEvent.entity_type == 'courses',
            AuditEvent.created_at > now-timedelta(days=1)).limit(1000).all()
        used = sum(json.loads(event.metadata_json or '{}').get('requeued_parts', 0) for event in recent)
        capacity = min(max(0, MAINTENANCE_PARTS_PER_DAY-used), max(0, (STORAGE_BUDGET-storage_used(db))//MAX_VIDEO_BYTES-pending))
        for row in db.query(VideoLesson).options(defer(VideoLesson.video_data)).filter_by(course_id=identifier).order_by(VideoLesson.position).with_for_update().all():
            if row.state != 'failed' and not (row.state == 'ready' and not checks_passed(json.loads(row.content_json))):
                continue
            if changed >= min(40, capacity):
                break
            row.state, row.attempts, row.error_code = 'queued', 0, None
            row.available_at, row.lease_until, row.lease_token = now, None, None
            changed += 1
        missing = len(json.loads(course.plan_json).get('lessons', [])) - db.query(VideoLesson.id).filter_by(course_id=identifier).count()
        if not changed and missing <= 0:
            raise HTTPException(409, 'No recoverable parts or storage capacity available')
    elif kind == 'notes':
        row = db.query(LearningNotebook).filter_by(id=identifier, state='failed').with_for_update().first()
        if not row:
            raise HTTPException(409, 'Only a failed notebook can be recovered')
        preferences = json.loads(row.input_json)
        preferences['authoring_version'] = 2
        row.input_json = json.dumps(preferences)
        row.state, row.attempts, row.error_code = 'queued', 0, None
        row.available_at, row.lease_until, row.lease_token = now, None, None
        changed = 1
    else:
        row = db.query(AssessmentJob).filter_by(interview_id=identifier, state='failed').with_for_update().first()
        if not row:
            raise HTTPException(409, 'Only a failed submitted assessment can be recovered')
        owner = db.get(User, row.user_id)
        if not owner or not owner.is_active or owner.role != UserRole.student:
            raise HTTPException(409, 'The assessment owner needs an active student account')
        if row.created_at < now-timedelta(days=30):
            raise HTTPException(409, 'The recording retention window has expired. Review with the institution.')
        row.state, row.attempts, row.error_code = 'queued', 0, None
        row.available_at, row.lease_until, row.lease_token = now, None, None
        changed = 1
    record_audit(db, actor, 'processing.recovery', entity_type=kind, entity_id=identifier,
                 metadata={'requeued_parts': changed, 'preserved_existing_records': True})
    db.commit()
    return {'status': 'queued', 'requeued_parts': changed,
            'message': 'Recovery requested. Existing answers, passed lessons and progress are preserved.'}
