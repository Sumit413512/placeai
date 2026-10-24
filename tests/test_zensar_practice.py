import importlib.util
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import Depends
from sqlalchemy import text

from app.dependencies import require_student
from app.models import HRRecording, Job, MockInterview, RecruiterProfile, StudentProfile, User, UserRole
from app.placement_access import job_is_visible_to_student
from app.routers import mock_interview, mock_interview_v2
from app.student_entitlements import require_student_premium_access
from app.trial_demo_access import is_trial_demo_job, trial_demo_access_state
from app.zensar_practice import JOB_ID, TITLE, COMPANY, VERSION, OBJECTIVE, SPOKEN, is_zensar_practice
from test_learning_hub import hub  # noqa: F401


def seed_sql():
    filename=Path(__file__).resolve().parents[1]/'alembic/versions/20261024_0027_zensar_practice.py'
    spec=importlib.util.spec_from_file_location('zensar_migration',filename)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.SEED_SQL


@pytest.fixture
def exam(hub, monkeypatch):
    user=User(email='zensar-owner@example.invalid',username='zensar-fixture-owner',hashed_password='unused',role=UserRole.recruiter,is_active=True)
    hub.db.add(user);hub.db.flush()
    recruiter=RecruiterProfile(user_id=user.id,company_name='TechNova Solutions — Demo')
    profile=StudentProfile(user_id=hub.owner.id,full_name='Practice student')
    hub.db.add_all([recruiter,profile]);hub.db.flush()
    base=Job(recruiter_id=recruiter.id,title='PlaceAI TechNova Demo Assessment',description='Fictional demo',visibility='public')
    hub.db.add(base);hub.db.commit()
    hub.db.execute(text(seed_sql()));hub.db.execute(text(seed_sql()));hub.db.commit()
    hub.client.app.include_router(mock_interview_v2.router)
    hub.client.app.include_router(mock_interview.router)
    def premium(user=Depends(require_student)):
        return user
    hub.client.app.dependency_overrides[require_student_premium_access]=premium
    monkeypatch.setattr('app.trial_demo_access.student_access_status',lambda *args:{'premium_access':True,'access_mode':'student_workspace'})
    monkeypatch.setattr(mock_interview_v2,'_call_interview_ai',lambda *a,**kw:pytest.fail('Curated Zensar generation must not require AI capacity'))
    hub.profile=profile;hub.base=base
    return hub


def test_zensar_is_in_mock_catalog_but_not_a_recruitment_opportunity(exam):
    rows=exam.client.get('/mock-interview/jobs').json()
    row=next(x for x in rows if x['id']==JOB_ID)
    assert row['title']==TITLE and row['company_name']==COMPANY
    assert row['is_trial_demo'] and row['can_start']
    assert 'Not an official Zensar' in row['practice_notice']
    job=exam.db.get(Job,JOB_ID)
    assert is_zensar_practice(job) and is_trial_demo_job(job)
    assert not job_is_visible_to_student(exam.profile,job,exam.db)
    assert exam.db.query(Job).filter_by(id=JOB_ID).count()==1
    job.id='untrusted-copy'
    assert not is_zensar_practice(job)
    exam.db.rollback()


def test_zensar_uses_complete_existing_proctored_contract_and_private_keys(exam):
    response=exam.client.post('/mock-interview/start',json={'job_id':JOB_ID,'mode':'assessment','question_count':50,'focus':'balanced','difficulty':'mixed'})
    assert response.status_code==200,response.text
    data=response.json();questions=data['questions']
    assert data['job_title']==TITLE and data['company_name']==COMPANY
    assert data['generation_mode']=='curated_practice' and data['model']==VERSION
    assert len(questions)==50
    assert Counter(q['section'] for q in questions)=={key:count for key,_,count in mock_interview_v2.ASSESSMENT_BLUEPRINT}
    assert sum(q.get('response_mode')=='audio' for q in questions)==8
    assert sum(q['answer_type']=='video' for q in questions)==4
    assert sum(q['answer_type']=='code' for q in questions)==2
    assert all('correct_answer' not in q for q in questions)
    assert all('hidden_tests' not in q.get('coding_spec',{}) for q in questions)
    assert all(q['practice_exam']==VERSION for q in questions)
    saved=exam.db.get(MockInterview,data['interview_id'])
    assert saved.job_id==JOB_ID and saved.overall_score is None
    assert exam.db.query(HRRecording).filter_by(interview_id=saved.id).one().exam_started_at is None
    issued=json.loads(saved.questions_json)
    for q in issued:
        if q['answer_type']=='mcq':
            assert len(set(q['options']))==4 and q['correct_answer'] in q['options']
    # Separate job identity also keeps TechNova's attempt allowance separate.
    from app import trial_demo_access
    original=trial_demo_access.student_access_status
    trial_demo_access.student_access_status=lambda *args:{'premium_access':True,'access_mode':'trial'}
    try:
        assert trial_demo_access_state(exam.owner,exam.profile,exam.db.get(Job,JOB_ID),exam.db)['attempts_used']==1
        assert trial_demo_access_state(exam.owner,exam.profile,exam.base,exam.db)['attempts_used']==0
    finally:
        trial_demo_access.student_access_status=original


def test_zensar_cannot_be_downgraded_or_opened_when_inactive(exam):
    assert exam.client.post('/mock-interview/start',json={'job_id':JOB_ID,'mode':'practice','question_count':8}).status_code==422
    assert exam.client.post('/mock-interview/start',json={'job_id':JOB_ID,'mode':'assessment','question_count':16}).status_code==422
    job=exam.db.get(Job,JOB_ID);job.is_active=False;exam.db.commit()
    assert all(x['id']!=JOB_ID for x in exam.client.get('/mock-interview/jobs').json())
    assert exam.client.post('/mock-interview/start',json={'job_id':JOB_ID,'mode':'assessment','question_count':50}).status_code==404
    exam.actor[0]=SimpleNamespace(role=UserRole.recruiter)
    assert exam.client.get('/mock-interview/jobs').status_code==403


def test_curated_bank_matches_all_sections_and_has_one_answer_per_item():
    assert {key:len(items) for key,items in OBJECTIVE.items()}=={'quantitative':8,'logical':8,'communication':6,'technical':8,'programming':6}
    assert sum(map(len,SPOKEN.values()))==12
    for items in OBJECTIVE.values():
        for prompt,options,answer in items:
            assert prompt and len(set(options))==4 and options.count(answer)==1
