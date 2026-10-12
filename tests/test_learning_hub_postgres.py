"""Actual PostgreSQL leases must serialize admission across worker processes."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.learning_worker import claim
from app.models import LearningNotebook, utcnow


def test_learning_workers_share_one_admission_slot_and_reclaim_expired_leases():
    url = os.getenv("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Dedicated PostgreSQL test service is required")
    engine = create_engine(url, pool_size=12, max_overflow=0)
    schema = "learning_test_" + uuid4().hex
    scoped = engine.execution_options(schema_translate_map={None: schema})
    try:
        with engine.begin() as db:
            db.execute(text(f'CREATE SCHEMA "{schema}"'))
            db.execute(text(f'CREATE TABLE "{schema}".users (id varchar PRIMARY KEY)'))
            db.execute(text(f'INSERT INTO "{schema}".users VALUES (\'learning-user\')'))
        with scoped.begin() as db:
            LearningNotebook.__table__.create(db)
        with Session(scoped) as db:
            db.add_all([LearningNotebook(user_id="learning-user", request_id=str(i),
                                         title="SQL", input_json="{}") for i in range(10)])
            db.commit()
        def try_claim(_):
            with Session(scoped) as db:
                return claim(db)
        with ThreadPoolExecutor(max_workers=12) as pool:
            leases = [item for item in pool.map(try_claim, range(24)) if item]
        assert len(leases) == 1
        with Session(scoped) as db:
            row = db.get(LearningNotebook, leases[0][0])
            row.lease_until = utcnow() - timedelta(seconds=1)
            db.commit()
        with ThreadPoolExecutor(max_workers=12) as pool:
            replacement = [item for item in pool.map(try_claim, range(24)) if item]
        assert len(replacement) == 1
        assert replacement[0][0] == leases[0][0]
        assert replacement[0][1] != leases[0][1]
    finally:
        with engine.begin() as db:
            db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
