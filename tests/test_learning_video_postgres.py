"""Real PostgreSQL worker admission and stale-lease recovery under concurrent claimers."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.learning_video_worker import claim
from app.models import VideoCourse, VideoLesson, utcnow


def test_video_workers_share_one_slot_and_stop_after_three_interrupted_attempts():
    url = os.getenv('TEST_POSTGRES_URL')
    if not url:
        pytest.skip('Dedicated PostgreSQL test service is required')
    engine = create_engine(url, pool_size=12, max_overflow=0)
    schema = 'video_test_' + uuid4().hex
    scoped = engine.execution_options(schema_translate_map={None:schema})
    try:
        with engine.begin() as db:
            db.execute(text(f'CREATE SCHEMA "{schema}"'))
            db.execute(text(f'CREATE TABLE "{schema}".users (id varchar PRIMARY KEY)'))
            db.execute(text(f'INSERT INTO "{schema}".users VALUES (\'video-user\')'))
        with scoped.begin() as db:
            VideoCourse.__table__.create(db); VideoLesson.__table__.create(db)
        with Session(scoped) as db:
            db.add_all([VideoCourse(user_id='video-user',request_id=str(i),title='SQL',input_json='{}') for i in range(10)])
            db.commit()
        def attempt(_):
            with Session(scoped) as db:
                return claim(db)
        with ThreadPoolExecutor(max_workers=12) as pool:
            items = [item for item in pool.map(attempt,range(24)) if item]
        assert len(items)==1
        with Session(scoped) as db:
            row = db.get(VideoCourse,items[0][1]); row.attempts=3
            row.lease_until=utcnow()-timedelta(seconds=1); db.commit()
        with Session(scoped) as db:
            replacement=claim(db)
            assert replacement[1] != items[0][1]
            assert db.get(VideoCourse,items[0][1]).state=='failed'
    finally:
        with engine.begin() as db:
            db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def test_matching_students_share_one_course_and_one_generation_job(monkeypatch):
    url = os.getenv('TEST_POSTGRES_URL')
    if not url:
        pytest.skip('Dedicated PostgreSQL test service is required')
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker
    from app.database import Base, get_db
    from app.dependencies import get_current_user
    from app.models import User, UserRole, LearningRuntime, VideoEnrollment
    from app.routers import learning_video
    engine = create_engine(url, pool_size=8, max_overflow=0)
    schema = 'shared_video_test_' + uuid4().hex
    scoped = engine.execution_options(schema_translate_map={None:schema})
    monkeypatch.setattr(learning_video, 'student_ai_guard', lambda *_args:None)
    monkeypatch.setattr(learning_video, 'wake_worker', lambda:None)
    sessions = sessionmaker(scoped, expire_on_commit=False)
    try:
        with engine.begin() as db:
            db.execute(text(f'CREATE SCHEMA "{schema}"'))
        Base.metadata.create_all(scoped)
        with sessions() as db:
            users = [User(username=f'learner-{i}', email=f'learner-{i}@example.invalid',
                hashed_password='test-only', role=UserRole.student, is_active=True) for i in range(2)]
            db.add_all(users); db.add(LearningRuntime(id=1, provider_configured=True)); db.commit()
        def client_for(user):
            app = FastAPI(); app.include_router(learning_video.router)
            def database():
                with sessions() as db:
                    yield db
            app.dependency_overrides[get_db] = database
            app.dependency_overrides[get_current_user] = lambda:user
            return TestClient(app)
        def join(user):
            with client_for(user) as client:
                response = client.post('/learning-hub/video', json={'topic':'PostgreSQL','request_id':'parallel-request-'+user.id})
                assert response.status_code == 202, response.text
                return response.json()['id']
        with ThreadPoolExecutor(max_workers=2) as pool:
            identifiers = list(pool.map(join, users))
        assert identifiers[0] == identifiers[1]
        with sessions() as db:
            assert db.query(VideoCourse).count() == 1
            assert db.query(VideoEnrollment).count() == 2
            import json
            from test_learning_video import course_plan
            course = db.get(VideoCourse, identifiers[0]); course.state='ready'; course.plan_json=json.dumps(course_plan()); db.commit()
        def prepare(user):
            with client_for(user) as client:
                response = client.post(f'/learning-hub/video/{identifiers[0]}/lessons/0')
                assert response.status_code == 202, response.text
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(prepare, users))
        with sessions() as db:
            assert db.query(VideoLesson).count() == 1
            from app.learning_video_worker import fill_pending_parts
            fill_pending_parts(db)
            fill_pending_parts(db)
            assert db.query(VideoLesson).count() == 4
    finally:
        with engine.begin() as db:
            db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
