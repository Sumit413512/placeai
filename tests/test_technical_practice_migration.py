import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_technical_practice_migration_is_additive_and_repeat_safe():
    filename = Path(__file__).resolve().parents[1] / 'alembic/versions/20261024_0026_technical_practice.py'
    spec = importlib.util.spec_from_file_location('technical_migration', filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine('sqlite://')
    with engine.begin() as db:
        db.execute(text('CREATE TABLE users (id VARCHAR PRIMARY KEY)'))
        db.execute(text("INSERT INTO users VALUES ('existing-student')"))
        module.op = Operations(MigrationContext.configure(db))
        module.upgrade()
        module.upgrade()
        assert db.execute(text('SELECT id FROM users')).scalar() == 'existing-student'
        assert 'technical_practice_attempts' in inspect(db).get_table_names()
        columns = {c['name'] for c in inspect(db).get_columns('technical_practice_attempts')}
        assert {'user_id', 'request_id', 'deadline_at', 'answers_json', 'result_json'} <= columns
    engine.dispose()
