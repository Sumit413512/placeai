"""Persist covering indexes for queue and placement foreign keys.

Revision ID: 20261007_0019
Revises: 20261006_0018

The production database is provisioned through an owner-capable channel, while
Render intentionally runs Alembic with the restricted ``placeai_render_runtime``
role. Owners may create the indexes; restricted runtimes only verify that the
pre-provisioned indexes are valid and fail closed if infrastructure drift removes
them.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261007_0019"
down_revision = "20261006_0018"
branch_labels = None
depends_on = None

INDEXES = (
    ("assessment_jobs", "ix_assessment_jobs_user_id", "user_id"),
    ("placement_actions", "ix_placement_actions_job_id", "job_id"),
    ("placement_actions", "ix_placement_actions_owner_user_id", "owner_user_id"),
)


def _can_manage_indexes(bind) -> bool:
    return bool(bind.execute(sa.text("""
        SELECT COALESCE((SELECT rolsuper FROM pg_roles WHERE rolname = current_user), false)
          OR NOT EXISTS (
              SELECT 1
              FROM (VALUES ('assessment_jobs'), ('placement_actions')) AS expected(relname)
              WHERE NOT EXISTS (
                  SELECT 1
                  FROM pg_class c
                  JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = 'public'
                    AND c.relname = expected.relname
                    AND pg_get_userbyid(c.relowner) = current_user
              )
          )
    """)).scalar())


def _index_matches(bind, table: str, index: str, column: str) -> bool:
    return bool(bind.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1
            FROM pg_index i
            JOIN pg_class idx ON idx.oid = i.indexrelid
            JOIN pg_class tbl ON tbl.oid = i.indrelid
            JOIN pg_namespace n ON n.oid = tbl.relnamespace
            WHERE n.nspname = 'public'
              AND tbl.relname = :table
              AND idx.relname = :index
              AND i.indisvalid
              AND i.indisready
              AND i.indnkeyatts = 1
              AND (
                  SELECT a.attname
                  FROM pg_attribute a
                  WHERE a.attrelid = tbl.oid
                    AND a.attnum = i.indkey[0]
              ) = :column
        )
    """), {"table": table, "index": index, "column": column}).scalar())


def _verify_indexes(bind) -> None:
    missing = [
        index
        for table, index, column in INDEXES
        if not _index_matches(bind, table, index, column)
    ]
    if missing:
        raise RuntimeError("REQUIRED_FK_INDEXES_NOT_PROVISIONED:" + ",".join(missing))


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    if _can_manage_indexes(bind):
        for table, index, column in INDEXES:
            bind.execute(sa.text(
                f"CREATE INDEX IF NOT EXISTS {index} ON public.{table} ({column})"
            ))

    _verify_indexes(bind)


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if not _can_manage_indexes(bind):
        raise RuntimeError("FK_INDEX_DOWNGRADE_REQUIRES_TABLE_OWNER")

    for _table, index, _column in reversed(INDEXES):
        bind.execute(sa.text(f"DROP INDEX IF EXISTS public.{index}"))
