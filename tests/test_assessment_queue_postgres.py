"""Exercise actual PostgreSQL row locks, not SQLite's no-op FOR UPDATE."""
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app import assessment_queue as queue
from app.models import AssessmentJob, AssessmentQueueControl, utcnow


def test_multiple_workers_obey_one_global_admission_limit():
    url = os.environ.get("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Dedicated PostgreSQL test service is required")
    engine = create_engine(url, pool_size=16, max_overflow=0)
    schema = "queue_test_" + uuid4().hex
    scoped = engine.execution_options(schema_translate_map={None: schema})
    try:
        with engine.begin() as db:
            db.execute(text(f'CREATE SCHEMA "{schema}"'))
            db.execute(text(f'CREATE TABLE "{schema}".users (id varchar PRIMARY KEY)'))
            db.execute(text(f'CREATE TABLE "{schema}".mock_interviews (id varchar PRIMARY KEY)'))
            db.execute(text(f'INSERT INTO "{schema}".users VALUES (\'test-user\')'))
            for number in range(100):
                db.execute(text(f'INSERT INTO "{schema}".mock_interviews VALUES (:id)'), {"id": str(number)})
        with scoped.begin() as db:
            AssessmentJob.__table__.create(db)
            AssessmentQueueControl.__table__.create(db)
        with Session(scoped) as db:
            db.add(AssessmentQueueControl(id=1, window_started_at=utcnow(), starts_in_window=0))
            db.add_all([AssessmentJob(interview_id=str(n), user_id="test-user", payload_json="{}") for n in range(100)])
            db.commit()

        def claim(_):
            with Session(scoped) as db:
                return queue.claim(db, concurrency=4, starts_per_minute=6)

        with ThreadPoolExecutor(max_workers=16) as pool:
            claimed = [item for item in pool.map(claim, range(32)) if item]
        assert len(claimed) == 4
        assert len({item[0] for item in claimed}) == 4
        with Session(scoped) as db:
            for item in claimed:
                queue.finish(db, item[0], item[3], True)
        with ThreadPoolExecutor(max_workers=16) as pool:
            second = [item for item in pool.map(claim, range(32)) if item]
        assert len(second) == 2  # Per-minute budget remains global after completion.
    finally:
        with engine.begin() as db:
            db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
