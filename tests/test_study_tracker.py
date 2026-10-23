import json
from datetime import timedelta
from uuid import uuid4
import pytest
from app.models import LearningNotebook,StudentProfile,MockInterview,Job,VideoViewerProgress,VideoCourse,utcnow
from app.routers import study_tracker
from app.study_models import StudyDaily,NotebookProgress,StudyPlan
from test_learning_hub import hub,plan_data,chapter_data  # noqa: F401
from test_learning_video import video,ready_lesson  # noqa: F401

@pytest.fixture
def tracker(hub):
    hub.client.app.include_router(study_tracker.router)
    return hub

def book(tracker):
    row=LearningNotebook(user_id=tracker.owner.id,request_id=str(uuid4()),title='SQL notes',state='ready',
        input_json=json.dumps({'topic':'SQL','chapters':8}),plan_json=json.dumps({**plan_data(),'chapters':plan_data()['chapters'][:1]}),chapters_json=json.dumps([chapter_data()]),sources_json=json.dumps([{'title':'PostgreSQL','url':'https://www.postgresql.org/docs/current/'}]))
    tracker.db.add(row);tracker.db.commit();return row

def plan(tracker,**changes):
    r=tracker.client.post('/study-tracker/plans',json={'title':'Data engineering path',**changes});assert r.status_code==201,r.text;return r.json()

def test_notebook_deletion_is_recoverable_private_and_stops_a_live_lease(tracker):
    row=book(tracker);identifier=row.id
    row.lease_token='private-worker-lease';row.lease_until=utcnow()+timedelta(minutes=8);tracker.db.commit()
    assert tracker.client.delete('/learning-hub/'+identifier).status_code==200
    tracker.db.refresh(row);assert row.state=='deleted' and row.lease_token is None
    assert tracker.client.get('/learning-hub').json()['items']==[]
    for tail in ['', '/pdf']:
        assert tracker.client.get('/learning-hub/'+identifier+tail).status_code==404
    assert len(tracker.client.get('/learning-hub?trash=true').json()['items'])==1
    tracker.actor[0]=tracker.other
    assert tracker.client.post('/learning-hub/'+identifier+'/restore').status_code==404
    assert tracker.client.get('/learning-hub?trash=true').json()['items']==[]
    tracker.actor[0]=tracker.owner
    assert tracker.client.post('/learning-hub/'+identifier+'/restore').json()['ready_to_begin']
    assert tracker.client.get('/learning-hub/'+identifier+'/pdf').status_code==200

def test_notes_visit_does_not_award_completion_pdf_marks_are_idempotent_and_undoable(tracker):
    row=book(tracker);p=plan(tracker)
    r=tracker.client.post(f"/study-tracker/plans/{p['id']}/goals",json={'kind':'notes','resource_id':row.id,'target':999});assert r.status_code==201,r.text
    assert r.json()['target']==3
    path='/study-tracker/notes/'+row.id
    assert tracker.client.put(path,json={'section_key':'1.2','event_id':str(uuid4()),'active_seconds':60}).json()['completed']==0
    mark={'section_key':'1.2','event_id':str(uuid4()),'source':'offline','through':True,'completed':True}
    assert tracker.client.put(path,json=mark).json()['percent']==66
    assert tracker.client.put(path,json=mark).json()['completed']==2
    daily=tracker.db.query(StudyDaily).one();tracker.db.refresh(daily);assert daily.sections_completed==2 and daily.notes_seconds==0
    summary=tracker.client.get('/study-tracker').json()
    assert summary['plans'][0]['goals'][0]['completed']==2 and summary['plans'][0]['percent']==66
    assert tracker.client.put(path,json={'section_key':'1.2','event_id':str(uuid4()),'completed':False}).json()['completed']==1
    assert tracker.client.put(path,json={'section_key':'9.9','event_id':str(uuid4()),'completed':True}).status_code==422
    tracker.actor[0]=tracker.other
    for endpoint in [path]:
        assert tracker.client.get(endpoint).status_code==404
        assert tracker.client.put(endpoint,json=mark).status_code==404
    assert tracker.client.get('/study-tracker').json()['plans']==[]
    assert tracker.client.patch('/study-tracker/plans/'+p['id'],json={'daily_minutes':30}).status_code==404

def test_web_time_is_wall_clock_bounded_and_study_progress_cannot_change_grades(tracker,monkeypatch):
    row=book(tracker);plan(tracker)
    now=utcnow();monkeypatch.setattr(study_tracker,'utcnow',lambda:now)
    payload={'section_key':'1.1','event_id':str(uuid4()),'active_seconds':60}
    path='/study-tracker/notes/'+row.id
    tracker.client.put(path,json=payload)
    now+=timedelta(seconds=20);payload['event_id']=str(uuid4());tracker.client.put(path,json=payload)
    now+=timedelta(seconds=1);payload['event_id']=str(uuid4());tracker.client.put(path,json=payload)
    daily=tracker.db.query(StudyDaily).one();tracker.db.refresh(daily);assert daily.notes_seconds==21
    assert tracker.client.put(path,json={**payload,'percent':100}).status_code==422
    assert tracker.client.get(path).json()['completed']==0

def test_mock_goals_count_actual_complete_assessments_not_client_counts(tracker):
    profile=StudentProfile(user_id=tracker.owner.id);tracker.db.add(profile);tracker.db.flush()
    job=Job(recruiter_id='isolated-fixture',title='SQL engineer',description='Isolated test role');tracker.db.add(job);tracker.db.flush()
    for score,status in [(80,'complete'),(20,'incomplete'),(None,'pending')]:
        tracker.db.add(MockInterview(student_id=profile.id,job_id=job.id,questions_json='[]',answers_json='[]',overall_score=score,evaluation_json=json.dumps({'analysis_status':status})))
    tracker.db.commit();p=plan(tracker)
    goal=tracker.client.post(f"/study-tracker/plans/{p['id']}/goals",json={'kind':'mock','target':20}).json()
    assert goal['completed']==1 and goal['percent']==5
    assert tracker.client.patch('/study-tracker/goals/'+goal['id'],json={'completed':20}).status_code==409
    assert tracker.client.post('/study-tracker/plans',json={'title':'Bad zone','timezone':'invalid/zone'}).status_code==422

def test_video_goals_follow_the_viewers_private_completion_and_quiz(video):
    video.api.app.include_router(study_tracker.router)
    identifier,lesson_id,_=ready_lesson(video)
    p=video.api.post('/study-tracker/plans',json={'title':'Video learning plan'}).json()
    endpoint=f"/study-tracker/plans/{p['id']}/goals"
    goal=video.api.post(endpoint,json={'kind':'video','resource_id':identifier});assert goal.status_code==201,goal.text
    assert goal.json()['completed']==0 and goal.json()['target']==4
    from app.models import VideoProgress
    row=VideoViewerProgress(user_id=video.owner.id,lesson_id=lesson_id,video_completed=True,practice_completed=False);video.db.add(row);video.db.commit()
    assert video.api.get('/study-tracker').json()['plans'][0]['goals'][0]['completed']==0
    row.practice_completed=True;video.db.commit()
    assert video.api.get('/study-tracker').json()['plans'][0]['goals'][0]['completed']==1
    video.actor[0]=video.other
    assert video.api.post(endpoint,json={'kind':'video','resource_id':identifier}).status_code==404
