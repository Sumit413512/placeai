import json
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from test_learning_hub import hub  # noqa: F401
from app.assessment_status import result_status
from app.profile_completeness import profile_completion
from app.processing_recovery import recover
from app.models import AuditEvent, UserRole, VideoCourse, VideoLesson, VideoProgress, utcnow
from app.routers import platform
from app.learning_video_worker import fill_pending_parts


def test_failed_and_overdue_history_never_get_a_new_24_hour_promise():
    now = utcnow()
    attempt = SimpleNamespace(overall_score=None, created_at=now-timedelta(days=15))
    failed = SimpleNamespace(state='failed', created_at=attempt.created_at)
    assert result_status(attempt, failed, now=now)['status'] == 'failed'
    assert result_status(attempt, failed, now=now)['expected_within_hours'] is None
    assert result_status(attempt, now=now)['status'] == 'delayed'
    attempt.overall_score = 0
    assert result_status(attempt, failed, now=now)['status'] == 'complete'


def test_profile_contract_includes_phone_and_accepts_zero_cgpa():
    values = dict(full_name='Student', college='College', degree='BE', branch='CS', graduation_year=2026,
                  cgpa=0, phone=None, skills=['SQL'], resume=object())
    result = profile_completion(SimpleNamespace(**values))
    assert result['percent'] < 100 and result['missing'] == ['phone']
    values['phone'] = '9999999999'
    assert profile_completion(SimpleNamespace(**values))['percent'] == 100


def test_legacy_private_course_gets_missing_lessons_and_private_progress(hub):
    course = VideoCourse(user_id=hub.owner.id, request_id='legacy-test', title='Legacy SQL', state='ready',
        input_json='{"topic":"SQL"}', plan_json=json.dumps({'lessons':[{'title':'First'},{'title':'Second'}]}))
    hub.db.add(course); hub.db.commit()
    fill_pending_parts(hub.db)
    lessons = hub.db.query(VideoLesson).filter_by(course_id=course.id).all()
    assert len(lessons) == 2
    assert all(hub.db.get(VideoProgress, row.id) is not None for row in lessons)
    fill_pending_parts(hub.db)
    assert hub.db.query(VideoLesson).filter_by(course_id=course.id).count() == 2


def test_repair_preserves_passed_media_and_progress_and_is_rate_bounded(hub):
    hub.owner.role = UserRole.platform_admin
    course = VideoCourse(user_id=hub.other.id, request_id='repair-test', title='SQL', state='ready',
        input_json='{"topic":"SQL"}', plan_json=json.dumps({'lessons':[{'title':'Passed'},{'title':'Failed'}]}))
    hub.db.add(course); hub.db.flush()
    checked = json.dumps({key:{'passed':True} for key in ['content_review','media_review','audiovisual_review']})
    passed = VideoLesson(course_id=course.id, position=0, title='Passed', state='ready', content_json=checked, video_data=b'passed-media')
    failed = VideoLesson(course_id=course.id, position=1, title='Failed', state='failed', attempts=4, content_json='{"saved":"checkpoint"}')
    hub.db.add_all([passed, failed]); hub.db.flush()
    hub.db.add(VideoProgress(lesson_id=passed.id, video_completed=True, practice_completed=True))
    hub.db.commit()
    response = recover(hub.db, hub.owner, 'courses', course.id)
    assert response['requeued_parts'] == 1
    assert passed.video_data == b'passed-media' and passed.state == 'ready'
    assert hub.db.get(VideoProgress, passed.id).video_completed
    assert failed.state == 'queued' and failed.attempts == 0 and failed.content_json == '{"saved":"checkpoint"}'
    assert hub.db.query(AuditEvent).filter_by(action='processing.recovery').count() == 1
    with pytest.raises(HTTPException) as error:
        recover(hub.db, hub.owner, 'courses', course.id)
    assert error.value.status_code == 409


def test_student_cannot_open_admin_recovery(hub):
    app = FastAPI(); app.include_router(platform.router)
    app.dependency_overrides.update(hub.client.app.dependency_overrides)
    with TestClient(app) as client:
        assert client.get('/platform/processing-recovery').status_code == 403
        assert client.post('/platform/processing-recovery/courses/test/retry').status_code == 403


@pytest.mark.parametrize('prior_kind', ['courses', 'notes', 'assessments'])
def test_video_part_allowance_counts_only_video_recovery(hub, prior_kind):
    course = VideoCourse(user_id=hub.owner.id, request_id='budget-scope-test', title='SQL', state='ready',
                        input_json='{}', plan_json='{"lessons":[{"title":"One"}]}')
    hub.db.add(course); hub.db.flush()
    hub.db.add(VideoLesson(course_id=course.id, position=0, title='One', state='failed'))
    hub.db.add(AuditEvent(action='processing.recovery', entity_type=prior_kind, entity_id='other-recovery',
                         metadata_json='{"requeued_parts":40}'))
    hub.db.commit()
    if prior_kind == 'courses':
        with pytest.raises(HTTPException) as error: recover(hub.db, hub.owner, 'courses', course.id)
        assert error.value.status_code == 409
    else:
        assert recover(hub.db, hub.owner, 'courses', course.id)['requeued_parts'] == 1
