"""Private separate spoken answers; opt-in until schema and provider checks pass."""
from alembic import op
import sqlalchemy as sa

revision = "20261005_0017"
down_revision = "20261005_0016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("answer_recordings",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("interview_id", sa.String(), sa.ForeignKey("mock_interviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("mime_type", sa.String(80), nullable=False),
        sa.Column("exam_started_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("deadline_at", sa.DateTime(), nullable=False),
        sa.Column("consent_at", sa.DateTime(), nullable=False),
        sa.Column("sealed_at", sa.DateTime()),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("segments_json", sa.Text(), nullable=False),
        sa.Column("analysis_json", sa.Text()),
        sa.Column("analysis_lease_until", sa.DateTime()),
        sa.Column("provider_file_name", sa.String(200)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("interview_id", "question_id", name="uq_answer_recording_question"))
    op.create_index("ix_answer_recordings_expires_at", "answer_recordings", ["expires_at"])
    op.create_table("answer_recording_chunks",
        sa.Column("recording_id", sa.String(), sa.ForeignKey("answer_recordings.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("sequence", sa.Integer(), primary_key=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False))
    if op.get_bind().dialect.name == "postgresql":
        for table in ("answer_recordings", "answer_recording_chunks"):
            op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"REVOKE ALL ON public.{table} FROM anon, authenticated")
        op.execute("""DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'placeai_render_runtime') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON public.answer_recordings TO placeai_render_runtime;
            GRANT SELECT, INSERT, DELETE ON public.answer_recording_chunks TO placeai_render_runtime;
            CREATE POLICY render_private_answer_access ON public.answer_recordings
              FOR ALL TO placeai_render_runtime USING (true) WITH CHECK (true);
            CREATE POLICY render_private_answer_chunk_access ON public.answer_recording_chunks
              FOR ALL TO placeai_render_runtime USING (true) WITH CHECK (true);
          END IF;
        END $$""")
        # Retention runs as the migration owner, never as a public client role.
        # Reports survive; only expired recording bytes are removed in batches.
        op.execute("""DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
            PERFORM cron.schedule('placeai-expired-answer-recordings', '23 * * * *', $job$
              WITH expired AS (
                SELECT id FROM public.answer_recordings
                WHERE expires_at <= timezone('UTC', now()) AND status <> 'expired'
                ORDER BY expires_at LIMIT 100 FOR UPDATE SKIP LOCKED
              ), removed AS (
                DELETE FROM public.answer_recording_chunks
                WHERE recording_id IN (SELECT id FROM expired)
              )
              UPDATE public.answer_recordings SET status = 'expired'
              WHERE id IN (SELECT id FROM expired);
            $job$);
          END IF;
        END $$""")


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""DO $$ DECLARE scheduled bigint; BEGIN
          IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
            FOR scheduled IN SELECT jobid FROM cron.job WHERE jobname = 'placeai-expired-answer-recordings' LOOP
              PERFORM cron.unschedule(scheduled);
            END LOOP;
          END IF;
        END $$""")
    op.drop_table("answer_recording_chunks")
    op.drop_index("ix_answer_recordings_expires_at", table_name="answer_recordings")
    op.drop_table("answer_recordings")
