import json

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from app import assessment_queue
from app.code_execution_checkpoint import CodeExecutionCheckpoint
from app.models import AssessmentJob, MockInterview
from app.routers import mock_interview_v2 as exams
from test_assessment_queue import queued  # noqa: F401
from test_hr_video import exam, body  # noqa: F401


def test_async_execution_resumes_one_receipt_and_never_scores_a_queued_case(monkeypatch):
    saved = {}
    class Checkpoint:
        def get(self, key): return saved.get(key, {})
        def put(self, key, value): saved[key] = value
    calls = {'post': 0, 'get': 0}; ready = [False]
    def post(url, **kwargs):
        assert 'wait=false' in url
        calls['post'] += 1
        return httpx.Response(201, request=httpx.Request('POST', url),
                              json={'token': '11111111-1111-4111-8111-111111111111'})
    def get(url, **kwargs):
        calls['get'] += 1
        return httpx.Response(200, request=httpx.Request('GET', url), json={
            'status': {'id': 3 if ready[0] else 1, 'description': 'Accepted' if ready[0] else 'In Queue'},
            'stdout': '4\n' if ready[0] else None})
    monkeypatch.setattr(exams.httpx, 'post', post); monkeypatch.setattr(exams.httpx, 'get', get)
    monkeypatch.setattr(exams.time, 'sleep', lambda _: None)
    args = dict(language='python', source_code='print(2+2)', stdin='', expected_output='4',
                time_limit_seconds=2, memory_limit_kb=128000, checkpoint=Checkpoint())
    with pytest.raises(exams.CodeExecutionPending): exams._judge0_execute_case(**args)
    ready[0] = True
    assert exams._judge0_execute_case(**args)['passed']
    prior = dict(calls)
    assert exams._judge0_execute_case(**args)['passed']
    assert calls == prior and calls['post'] == 1


@pytest.mark.parametrize('status', [0, 1, 2, 13])
def test_unfinished_or_internal_execution_is_not_a_student_failure(monkeypatch, status):
    monkeypatch.setattr(exams.httpx, 'post', lambda url, **kwargs: httpx.Response(
        201, request=httpx.Request('POST', url), json={'status': {'id': status}}))
    with pytest.raises(RuntimeError):
        exams._judge0_execute_case(language='python', source_code='print(4)', stdin='', expected_output='4',
                                  time_limit_seconds=2, memory_limit_kb=128000)


def test_execution_receipts_are_private_and_fenced_by_the_current_worker_lease(queued, monkeypatch):
    assessment_queue.enqueue(queued.db, queued.interview, queued.user, body(queued))
    item = assessment_queue.claim(queued.db, 1, 10)
    checkpoint = CodeExecutionCheckpoint(sessionmaker(bind=queued.engine, expire_on_commit=False), (item[0], item[3]))
    checkpoint.put('a' * 64, {'token': 'private-execution-receipt'})
    assert checkpoint.get('a' * 64)['token'] == 'private-execution-receipt'
    monkeypatch.setattr(exams.get_settings(), 'assessment_queue_enabled', True)
    visible = exams.saved_interview_result(queued.interview.id, queued.user, queued.db)
    assert visible['result'] is None and 'private-execution-receipt' not in json.dumps(visible)
    job = queued.db.get(AssessmentJob, item[0]); job.lease_token = 'new-worker-lease'; queued.db.commit()
    with pytest.raises(HTTPException): checkpoint.put('b' * 64, {'token': 'stale-write'})
    queued.db.expire_all()
    row = queued.db.get(MockInterview, queued.interview.id)
    assert 'b' * 64 not in row.evaluation_json and row.answers_json
