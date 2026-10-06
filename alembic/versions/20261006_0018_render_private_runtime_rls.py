"""Persist private Render worker access for HR media and assessment queue tables.

Revision ID: 20261006_0018
Revises: 20261005_0017

Production uses a dedicated ``placeai_render_runtime`` PostgreSQL role. The HR
recording and durable assessment queue tables intentionally have RLS enabled and
are revoked from public client roles, so that dedicated role needs explicit
least-scope grants plus RLS policies. This migration mirrors the verified live
configuration and is safe on environments where the Render role does not exist.
"""
from alembic import op

revision = "20261006_0018"
down_revision = "20261005_0017"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'placeai_render_runtime') THEN
        -- Keep browser/client roles excluded; grant only the dedicated private runtime.
        REVOKE ALL ON public.hr_recordings,
                      public.hr_video_chunks,
                      public.assessment_jobs,
                      public.assessment_queue_control
          FROM placeai_render_runtime;

        GRANT SELECT, INSERT, UPDATE, DELETE ON public.hr_recordings
          TO placeai_render_runtime;
        GRANT SELECT, INSERT, UPDATE, DELETE ON public.hr_video_chunks
          TO placeai_render_runtime;
        GRANT SELECT, INSERT, UPDATE, DELETE ON public.assessment_jobs
          TO placeai_render_runtime;
        GRANT SELECT, INSERT, UPDATE, DELETE ON public.assessment_queue_control
          TO placeai_render_runtime;

        DROP POLICY IF EXISTS placeai_render_recording_access ON public.hr_recordings;
        CREATE POLICY placeai_render_recording_access ON public.hr_recordings
          FOR ALL TO placeai_render_runtime USING (true) WITH CHECK (true);

        DROP POLICY IF EXISTS placeai_render_chunk_access ON public.hr_video_chunks;
        CREATE POLICY placeai_render_chunk_access ON public.hr_video_chunks
          FOR ALL TO placeai_render_runtime USING (true) WITH CHECK (true);

        DROP POLICY IF EXISTS placeai_render_runtime_all_assessment_jobs ON public.assessment_jobs;
        CREATE POLICY placeai_render_runtime_all_assessment_jobs ON public.assessment_jobs
          FOR ALL TO placeai_render_runtime USING (true) WITH CHECK (true);

        DROP POLICY IF EXISTS placeai_render_runtime_all_assessment_queue_control
          ON public.assessment_queue_control;
        CREATE POLICY placeai_render_runtime_all_assessment_queue_control
          ON public.assessment_queue_control
          FOR ALL TO placeai_render_runtime USING (true) WITH CHECK (true);
      END IF;
    END $$""")


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("DROP POLICY IF EXISTS placeai_render_runtime_all_assessment_queue_control ON public.assessment_queue_control")
    op.execute("DROP POLICY IF EXISTS placeai_render_runtime_all_assessment_jobs ON public.assessment_jobs")
    op.execute("DROP POLICY IF EXISTS placeai_render_chunk_access ON public.hr_video_chunks")
    op.execute("DROP POLICY IF EXISTS placeai_render_recording_access ON public.hr_recordings")

    # Preserve table ownership/RLS; only remove the dedicated runtime grants added here.
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'placeai_render_runtime') THEN
        REVOKE ALL ON public.hr_recordings,
                      public.hr_video_chunks,
                      public.assessment_jobs,
                      public.assessment_queue_control
          FROM placeai_render_runtime;
      END IF;
    END $$""")
