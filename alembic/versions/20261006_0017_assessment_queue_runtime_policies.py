"""Allow the dedicated Render worker role through private assessment queue RLS.

Revision ID: 20261006_0017
Revises: 20261005_0016
"""
from alembic import op
import sqlalchemy as sa

revision = "20261006_0017"
down_revision = "20261005_0016"
branch_labels = None
depends_on = None

ROLE = "placeai_render_runtime"
POLICIES = (
    ("assessment_jobs", "placeai_render_runtime_all_assessment_jobs"),
    ("assessment_queue_control", "placeai_render_runtime_all_assessment_queue_control"),
)


def _role_exists(bind) -> bool:
    return bool(bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :role)"),
        {"role": ROLE},
    ).scalar())


def _policy_exists(bind, table: str, policy: str) -> bool:
    return bool(bind.execute(
        sa.text(
            "SELECT EXISTS ("
            "SELECT 1 FROM pg_policies "
            "WHERE schemaname = 'public' AND tablename = :table AND policyname = :policy"
            ")"
        ),
        {"table": table, "policy": policy},
    ).scalar())


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or not _role_exists(bind):
        return

    for table, policy in POLICIES:
        if _policy_exists(bind, table, policy):
            continue
        # The queue tables remain private. This policy authorizes only the dedicated
        # server-side Render runtime role; anon/authenticated keep no queue access.
        op.execute(
            f'CREATE POLICY "{policy}" ON public."{table}" '
            f'AS PERMISSIVE FOR ALL TO "{ROLE}" USING (true) WITH CHECK (true)'
        )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table, policy in reversed(POLICIES):
        op.execute(f'DROP POLICY IF EXISTS "{policy}" ON public."{table}"')
