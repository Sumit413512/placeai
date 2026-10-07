"""Persist and verify private Render worker access for HR media and queue tables.

Revision ID: 20261006_0018
Revises: 20261005_0017

Production uses a dedicated ``placeai_render_runtime`` PostgreSQL role. These
private tables keep RLS enabled and remain unavailable to browser client roles.

Alembic can run in two legitimate contexts:
1. an owner/superuser migration connection, which may create grants/policies;
2. the restricted Render runtime role, which must never be promoted to table
   owner just so application startup can run migrations.

When running as the restricted role this migration therefore verifies the exact
pre-provisioned least-privilege access and fails closed if anything is missing.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261006_0018"
down_revision = "20261005_0017"
branch_labels = None
depends_on = None

RUNTIME_ROLE = "placeai_render_runtime"
ACCESS = (
    ("hr_recordings", "placeai_render_recording_access"),
    ("hr_video_chunks", "placeai_render_chunk_access"),
    ("assessment_jobs", "placeai_render_runtime_all_assessment_jobs"),
    ("assessment_queue_control", "placeai_render_runtime_all_assessment_queue_control"),
)


def _role_exists(bind) -> bool:
    return bool(bind.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :role)"
    ), {"role": RUNTIME_ROLE}).scalar())


def _can_manage_policies(bind) -> bool:
    """Return true only when the migration connection can own policy DDL safely."""
    return bool(bind.execute(sa.text("""
        SELECT COALESCE((SELECT rolsuper FROM pg_roles WHERE rolname = current_user), false)
          OR NOT EXISTS (
              SELECT 1
              FROM (VALUES
                    ('hr_recordings'),
                    ('hr_video_chunks'),
                    ('assessment_jobs'),
                    ('assessment_queue_control')) AS expected(relname)
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


def _verify_runtime_access(bind) -> None:
    missing: list[str] = []
    for table, policy in ACCESS:
        rls_enabled = bool(bind.execute(sa.text("""
            SELECT COALESCE((
                SELECT c.relrowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relname = :table
            ), false)
        """), {"table": table}).scalar())

        privileges_ok = bool(bind.execute(sa.text("""
            SELECT has_table_privilege(:role, :qualified, 'SELECT')
               AND has_table_privilege(:role, :qualified, 'INSERT')
               AND has_table_privilege(:role, :qualified, 'UPDATE')
               AND has_table_privilege(:role, :qualified, 'DELETE')
        """), {"role": RUNTIME_ROLE, "qualified": f"public.{table}"}).scalar())

        policy_ok = bool(bind.execute(sa.text("""
            SELECT EXISTS (
                SELECT 1
                FROM pg_policies
                WHERE schemaname = 'public'
                  AND tablename = :table
                  AND policyname = :policy
                  AND cmd = 'ALL'
                  AND CAST(:role AS name) = ANY(roles)
                  AND qual = 'true'
                  AND with_check = 'true'
            )
        """), {"table": table, "policy": policy, "role": RUNTIME_ROLE}).scalar())

        if not rls_enabled:
            missing.append(f"{table}:rls")
        if not privileges_ok:
            missing.append(f"{table}:grants")
        if not policy_ok:
            missing.append(f"{table}:policy")

    if missing:
        raise RuntimeError(
            "RENDER_PRIVATE_RUNTIME_ACCESS_NOT_PROVISIONED:" + ",".join(missing)
        )


def _apply_owner_configuration(bind) -> None:
    # Static identifiers only; never interpolate request/user-controlled values here.
    for table, policy in ACCESS:
        bind.execute(sa.text(
            f"REVOKE ALL ON public.{table} FROM {RUNTIME_ROLE}"
        ))
        bind.execute(sa.text(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON public.{table} TO {RUNTIME_ROLE}"
        ))
        bind.execute(sa.text(
            f"DROP POLICY IF EXISTS {policy} ON public.{table}"
        ))
        bind.execute(sa.text(
            f"CREATE POLICY {policy} ON public.{table} "
            f"FOR ALL TO {RUNTIME_ROLE} USING (true) WITH CHECK (true)"
        ))


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or not _role_exists(bind):
        return

    if _can_manage_policies(bind):
        _apply_owner_configuration(bind)

    # Whether configuration was just applied by an owner or was pre-provisioned
    # by infrastructure, never advance the revision unless the exact private
    # worker access is present and RLS remains enabled.
    _verify_runtime_access(bind)


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or not _role_exists(bind):
        return
    if not _can_manage_policies(bind):
        raise RuntimeError("RENDER_PRIVATE_RUNTIME_DOWNGRADE_REQUIRES_TABLE_OWNER")

    for table, policy in reversed(ACCESS):
        bind.execute(sa.text(f"DROP POLICY IF EXISTS {policy} ON public.{table}"))
        bind.execute(sa.text(f"REVOKE ALL ON public.{table} FROM {RUNTIME_ROLE}"))
