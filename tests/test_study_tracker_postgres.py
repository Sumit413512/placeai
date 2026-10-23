"""Migration preservation and actual PostgreSQL multi-tab progress serialization."""
import importlib.util
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine,text
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import User,UserRole,LearningNotebook
from app.study_models import StudyDaily
from app.routers import study_tracker,learning_hub
from app.learning_worker import write_checkpoint
from test_learning_hub import plan_data,chapter_data


def test_additive_study_migration_preserves_notebook_content_and_repeats_safely():
    path=Path(__file__).parents[1]/'alembic/versions/43e6ac3c4be8_private_study_tracker_and_recoverable_.py'
    spec=importlib.util.spec_from_file_location('isolated_study_migration',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    engine=create_engine('sqlite://')
    with engine.begin() as db:
        db.execute(text('CREATE TABLE users(id VARCHAR PRIMARY KEY)'))
        db.execute(text('CREATE TABLE learning_notebooks(id VARCHAR PRIMARY KEY, title VARCHAR, chapters_json TEXT)'))
        db.execute(text("INSERT INTO learning_notebooks VALUES ('kept','Original title','[{\"teaching\":\"preserve me\"}]')"))
        module.op=Operations(MigrationContext.configure(db));module.upgrade();module.upgrade()
        saved=db.execute(text('SELECT title,chapters_json,deleted_at,last_read_section FROM learning_notebooks')).one()
        assert saved==('Original title','[{"teaching":"preserve me"}]',None,None)
        assert db.execute(text("SELECT count(*) FROM sqlite_master WHERE type='table' AND name IN ('study_plans','study_goals','study_daily_activity','learning_notebook_progress')")).scalar()==4
    engine.dispose()


def test_postgres_concurrent_pdf_checkins_count_once_and_deletion_fences_worker():
    url=os.getenv('TEST_POSTGRES_URL')
    if not url:pytest.skip('Dedicated PostgreSQL test service required')
    engine=create_engine(url,pool_size=8,max_overflow=0);schema='study_test_'+uuid4().hex
    scoped=engine.execution_options(schema_translate_map={None:schema});sessions=sessionmaker(bind=scoped,expire_on_commit=False)
    try:
        with engine.begin() as db:db.execute(text(f'CREATE SCHEMA "{schema}"'))
        Base.metadata.create_all(scoped)
        with sessions() as db:
            user=User(username='isolated-study',email='isolated-study@example.com',hashed_password='isolated',role=UserRole.student,is_active=True);db.add(user);db.flush()
            plan=plan_data();plan['chapters']=plan['chapters'][:1]
            book=LearningNotebook(user_id=user.id,request_id=str(uuid4()),title='SQL',state='ready',input_json=json.dumps({'topic':'SQL','chapters':8}),plan_json=json.dumps(plan),chapters_json=json.dumps([chapter_data()]));db.add(book);db.commit();identifier=book.id;actor=SimpleNamespace(id=user.id,role=UserRole.student)
        def check_in(_):
            with sessions() as db:
                return study_tracker.save_reading(identifier,study_tracker.ReadingInput(section_key='1.2',through=True,completed=True,source='offline',event_id=uuid4()),actor,db)['completed']
        with ThreadPoolExecutor(max_workers=8) as pool:assert set(pool.map(check_in,range(12)))=={2}
        with sessions() as db:
            assert db.query(StudyDaily).one().sections_completed==2
            book=db.get(LearningNotebook,identifier);book.lease_token='old-lease';db.commit()
            learning_hub.delete_notebook(identifier,actor,db)
        with pytest.raises(RuntimeError,match='LEASE_LOST'):write_checkpoint(sessions,identifier,'old-lease',plan,[])
        with sessions() as db:assert db.get(LearningNotebook,identifier).state=='deleted'
    finally:
        with engine.begin() as db:db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
