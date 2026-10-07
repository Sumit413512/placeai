from pathlib import Path


MIGRATION = Path("alembic/versions/20261007_0019_fk_covering_indexes.py")


def test_fk_index_migration_preserves_owner_aware_fail_closed_contract():
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision = "20261007_0019"' in source
    assert 'down_revision = "20261006_0018"' in source
    assert "ix_assessment_jobs_user_id" in source
    assert "ix_placement_actions_job_id" in source
    assert "ix_placement_actions_owner_user_id" in source
    assert "_can_manage_indexes" in source
    assert "_verify_indexes" in source
    assert "REQUIRED_FK_INDEXES_NOT_PROVISIONED" in source
    assert "FK_INDEX_DOWNGRADE_REQUIRES_TABLE_OWNER" in source
    assert "CREATE INDEX IF NOT EXISTS" in source
