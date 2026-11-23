"""Add private recurring study targets and track completed video lessons by day."""

import sqlalchemy as sa
from alembic import op

revision = "20261123_0033"
down_revision = "20261122_0032"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("mock_interviews", sa.Column("completed_at", sa.DateTime()))
    op.add_column("study_daily_activity",
                  sa.Column("lessons_completed", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "study_targets",
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("daily_json", sa.Text(), nullable=False),
        sa.Column("weekly_json", sa.Text(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("reminders", sa.Boolean(), nullable=False),
        sa.Column("reminder_start_day", sa.Date()),
        sa.Column("last_digest_day", sa.Date()),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE public.study_targets ENABLE ROW LEVEL SECURITY")
        op.execute("REVOKE ALL ON public.study_targets FROM PUBLIC, anon, authenticated")
        op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON public.study_targets TO service_role, placeai_render_runtime")
        op.execute("CREATE POLICY placeai_backend_runtime ON public.study_targets "
                   "FOR ALL TO placeai_render_runtime USING (true) WITH CHECK (true)")


def downgrade():
    op.drop_table("study_targets")
    op.drop_column("mock_interviews", "completed_at")
    op.drop_column("study_daily_activity", "lessons_completed")
