import json
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models import UserRole, utcnow
from app.routers import technical_practice
from app.technical_practice import BANK, TechnicalPracticeAttempt
from test_learning_hub import hub  # noqa: F401


@pytest.fixture
def practice(hub, monkeypatch):
    hub.client.app.include_router(technical_practice.router)
    monkeypatch.setattr(technical_practice, 'enforce_rate_limit', lambda *a, **kw: None)
    return hub


def start(practice, request_id=None):
    response = practice.client.post('/technical-practice/start', json={'request_id': request_id or str(uuid4())})
    assert response.status_code == 200, response.text
    return response.json()


def test_answer_keys_stay_server_side_scoring_is_exact_and_idempotent(practice):
    data = start(practice)
    assert len(data['questions']) == 16
    assert len({q['section'] for q in data['questions']}) == 4
    assert all('correct' not in q and 'explanation' not in q for q in data['questions'])
    row = practice.db.get(TechnicalPracticeAttempt, data['id'])
    issued = json.loads(row.questions_json)
    for i, q in enumerate(issued):
        option = q['correct'] if i < 8 else (q['correct'] + 1) % 4
        result = practice.client.put(f"/technical-practice/{row.id}/answer", json={'question_id': q['id'], 'option': option})
        assert result.status_code == 200
    response = practice.client.post(f'/technical-practice/{row.id}/submit')
    report = response.json()['result']
    assert report['score'] == 50 and report['correct'] == 8
    assert all(q['explanation'] for q in report['questions'])
    assert sum(s['total'] for s in report['sections']) == 16
    assert practice.client.post(f'/technical-practice/{row.id}/submit').json()['result'] == report
    assert practice.client.put(f'/technical-practice/{row.id}/answer', json={'question_id': 1, 'option': 0}).status_code == 409


def test_owner_isolation_role_checks_validation_and_saved_answers(practice):
    request_id = str(uuid4())
    data = start(practice, request_id)
    assert start(practice, request_id)['id'] == data['id']
    assert start(practice)['id'] == data['id']
    path = '/technical-practice/' + data['id']
    for body in [{'question_id': 99, 'option': 0}, {'question_id': 1, 'option': 4},
                 {'question_id': True, 'option': 0}, {'question_id': 1, 'option': 1, 'score': 100}]:
        assert practice.client.put(path + '/answer', json=body).status_code == 422
    assert practice.client.put(path + '/answer', json={'question_id': 1, 'option': 2}).status_code == 200
    assert practice.client.get(path).json()['answers'] == {'1': 2}
    practice.actor[0] = practice.other
    assert practice.client.get(path).status_code == 404
    assert practice.client.put(path + '/answer', json={'question_id': 1, 'option': 0}).status_code == 404
    assert practice.client.post(path + '/submit').status_code == 404
    assert practice.client.get('/technical-practice').json() == []
    practice.actor[0] = SimpleNamespace(role=UserRole.recruiter)
    assert practice.client.get('/technical-practice').status_code == 403


def test_server_deadline_rejects_late_answers_and_finishes_saved_work(practice):
    data = start(practice)
    row = practice.db.get(TechnicalPracticeAttempt, data['id'])
    issued = json.loads(row.questions_json)
    row.answers_json = json.dumps({'1': issued[0]['correct']})
    row.deadline_at = utcnow() - timedelta(seconds=1)
    practice.db.commit()
    path = '/technical-practice/' + row.id
    assert practice.client.put(path + '/answer', json={'question_id': 2, 'option': 0}).status_code == 409
    report = practice.client.get(path).json()['result']
    assert report['correct'] == 1 and report['total'] == 16
    assert practice.client.get(path).json()['result'] == report
    assert start(practice)['id'] != row.id


def test_question_bank_has_unique_valid_answer_keys_and_explanations():
    assert len(BANK) == 16 and len({q[1] for q in BANK}) == 16
    for section, question, options, correct, explanation in BANK:
        assert section and question and len(set(options)) == 4
        assert 0 <= correct < 4 and len(explanation) > 50
