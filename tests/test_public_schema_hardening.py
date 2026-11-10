import importlib.util
from pathlib import Path


def load_migration():
    path = Path(__file__).parents[1] / "alembic/versions/20261110_0029_public_schema_hardening.py"
    spec = importlib.util.spec_from_file_location("public_schema_hardening", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_public_schema_hardening_covers_every_legacy_backend_table():
    migration = load_migration()

    assert len(migration.BACKEND_TABLES) == 33
    assert len(set(migration.BACKEND_TABLES)) == len(migration.BACKEND_TABLES)
    assert {"users", "organizations", "learning_notebooks"} - set(migration.BACKEND_TABLES) == {
        "learning_notebooks"
    }


def test_public_schema_hardening_adds_all_advisor_indexes():
    migration = load_migration()

    assert {item[1:] for item in migration.INDEXES} == {
        ("learning_notebooks", "reviewed_by_user_id"),
        ("learning_video_courses", "reviewed_by_user_id"),
        ("learning_video_lessons", "reviewed_by_user_id"),
        ("student_documents", "shared_organization_id"),
    }
