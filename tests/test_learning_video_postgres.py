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
