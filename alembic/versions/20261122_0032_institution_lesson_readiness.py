"""Add tenant-specific readiness assignments and evidence."""

import sqlalchemy as sa
from alembic import op

revision = "20261122_0032"
down_revision = "20261122_0031"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "institution_lesson_readiness",
        sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("student_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("lesson_id", sa.String(), sa.ForeignKey("learning_video_lessons.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("question_version", sa.String(64), primary_key=True),
        sa.Column("assigned_at", sa.DateTime(), nullable=False),
        sa.Column("diagnostic_answer", sa.SmallInteger()),
        sa.Column("practice_answer", sa.SmallInteger()),
        sa.Column("followup_answer", sa.SmallInteger()),
    )
    op.create_index("ix_institution_readiness_report", "institution_lesson_readiness",
                    ["organization_id", "lesson_id", "question_version"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE public.institution_lesson_readiness ENABLE ROW LEVEL SECURITY")
        op.execute("REVOKE ALL ON public.institution_lesson_readiness FROM PUBLIC, anon, authenticated")
        op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON public.institution_lesson_readiness "
                   "TO service_role, placeai_render_runtime")
        op.execute("CREATE POLICY placeai_backend_runtime ON public.institution_lesson_readiness "
                   "FOR ALL TO placeai_render_runtime USING (true) WITH CHECK (true)")


def downgrade():
    op.drop_table("institution_lesson_readiness")
