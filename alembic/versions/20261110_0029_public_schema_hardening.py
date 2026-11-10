"""Harden remaining public tables and index editorial reviewer lookups."""

from alembic import op
import sqlalchemy as sa


revision = "20261110_0029"
down_revision = "20261110_0028"
branch_labels = None
depends_on = None


BACKEND_TABLES = (
    "access_requests",
    "alembic_version",
    "announcements",
    "applications",
    "attendance_records",
    "attendance_sessions",
    "audit_events",
    "communication_messages",
    "communication_threads",
    "custom_field_definitions",
    "custom_field_values",
    "drive_stages",
    "email_delivery_events",
    "incident_reports",
    "institution_policies",
    "interview_evaluations",
    "interview_schedules",
    "jobs",
    "mock_interviews",
    "notification_preferences",
    "notifications",
    "offers",
    "organizations",
    "page_view_events",
    "placement_actions",
    "placement_drives",
    "profile_change_requests",
    "rate_limit_buckets",
    "recruiter_profiles",
    "refresh_sessions",
    "stored_files",
    "student_subscriptions",
    "users",
)


INDEXES = (
    ("ix_learning_notebooks_reviewed_by_user_id", "learning_notebooks", "reviewed_by_user_id"),
    ("ix_learning_video_courses_reviewed_by_user_id", "learning_video_courses", "reviewed_by_user_id"),
    ("ix_learning_video_lessons_reviewed_by_user_id", "learning_video_lessons", "reviewed_by_user_id"),
    ("ix_student_documents_shared_organization_id", "student_documents", "shared_organization_id"),
)


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table in BACKEND_TABLES:
        op.execute(sa.text(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'REVOKE ALL ON TABLE public."{table}" FROM PUBLIC, anon, authenticated'))
        op.execute(sa.text(
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public."{table}" '
            "TO service_role, placeai_render_runtime"
        ))
        op.execute(sa.text(f'DROP POLICY IF EXISTS placeai_backend_runtime ON public."{table}"'))
        op.execute(sa.text(
            f'CREATE POLICY placeai_backend_runtime ON public."{table}" '
            "FOR ALL TO placeai_render_runtime USING (true) WITH CHECK (true)"
        ))

    # New tables stay private unless a future migration opts them into an API role.
    op.execute(sa.text(
        "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
        "REVOKE ALL ON TABLES FROM anon, authenticated"
    ))

    for name, table, column in INDEXES:
        op.execute(sa.text(
            f'CREATE INDEX IF NOT EXISTS "{name}" ON public."{table}" ("{column}")'
        ))


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for name, table, _column in reversed(INDEXES):
        op.execute(sa.text(f'DROP INDEX IF EXISTS public."{name}"'))

    for table in reversed(BACKEND_TABLES):
        op.execute(sa.text(f'DROP POLICY IF EXISTS placeai_backend_runtime ON public."{table}"'))
        op.execute(sa.text(f'ALTER TABLE public."{table}" DISABLE ROW LEVEL SECURITY'))
