"""Shared educational media with isolated enrollments, progress and audio checkpoints."""
from alembic import op
import sqlalchemy as sa

revision = "20261017_0023"
down_revision = "20261016_0022"
branch_labels = None
depends_on = None

DDL = """
ALTER TABLE public.learning_video_courses ADD COLUMN IF NOT EXISTS shared_key VARCHAR(64);
CREATE UNIQUE INDEX IF NOT EXISTS uq_video_shared_key ON public.learning_video_courses (shared_key);
ALTER TABLE public.learning_video_courses ALTER COLUMN user_id DROP NOT NULL;
ALTER TABLE public.learning_video_courses DROP CONSTRAINT IF EXISTS learning_video_courses_user_id_fkey;
ALTER TABLE public.learning_video_courses ADD CONSTRAINT learning_video_courses_user_id_fkey
  FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;
CREATE TABLE IF NOT EXISTS public.learning_video_enrollments (
  user_id VARCHAR NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  course_id VARCHAR NOT NULL REFERENCES public.learning_video_courses(id) ON DELETE CASCADE,
  request_id VARCHAR(80) NOT NULL, created_at TIMESTAMP NOT NULL,
  PRIMARY KEY(user_id,course_id), CONSTRAINT uq_video_enrollment_request UNIQUE(user_id,request_id)
);
CREATE INDEX IF NOT EXISTS ix_video_enrollment_course ON public.learning_video_enrollments(course_id);
CREATE TABLE IF NOT EXISTS public.learning_video_viewer_progress (
  user_id VARCHAR NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  lesson_id VARCHAR NOT NULL REFERENCES public.learning_video_lessons(id) ON DELETE CASCADE,
  position_seconds FLOAT NOT NULL, watched_seconds FLOAT NOT NULL, coverage_json TEXT NOT NULL,
  video_completed BOOLEAN NOT NULL, practice_completed BOOLEAN NOT NULL, updated_at TIMESTAMP NOT NULL,
  PRIMARY KEY(user_id,lesson_id)
);
CREATE INDEX IF NOT EXISTS ix_video_viewer_lesson ON public.learning_video_viewer_progress(lesson_id);
CREATE TABLE IF NOT EXISTS public.learning_video_narration (
  lesson_id VARCHAR NOT NULL REFERENCES public.learning_video_lessons(id) ON DELETE CASCADE,
  scene_key VARCHAR(64) NOT NULL, audio_data BYTEA NOT NULL, created_at TIMESTAMP NOT NULL,
  PRIMARY KEY(lesson_id,scene_key)
);
"""
TABLES = ("learning_video_enrollments", "learning_video_viewer_progress", "learning_video_narration")


def provision_sql():
    statements = [DDL]
    for table in TABLES:
        statements.append(f"""
ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.{table} FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.{table} TO service_role, placeai_render_runtime;
DROP POLICY IF EXISTS placeai_video_runtime ON public.{table};
CREATE POLICY placeai_video_runtime ON public.{table} FOR ALL TO placeai_render_runtime USING (true) WITH CHECK (true);
""")
    return "\n".join(statements)


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        if "shared_key" not in {column["name"] for column in sa.inspect(bind).get_columns("learning_video_courses")}:
            op.add_column("learning_video_courses", sa.Column("shared_key", sa.String(64)))
            op.create_index("uq_video_shared_key", "learning_video_courses", ["shared_key"], unique=True)
        from app.models import VideoEnrollment, VideoViewerProgress, VideoNarration
        for model in (VideoEnrollment, VideoViewerProgress, VideoNarration):
            model.__table__.create(bind, checkfirst=True)
        return
    if bind.execute(sa.text("SELECT current_user")).scalar() != "placeai_render_runtime":
        for statement in provision_sql().split(";"):
            if statement.strip():
                bind.execute(sa.text(statement))
    valid = bind.execute(sa.text("""
SELECT count(*)=3 AND bool_and(c.relrowsecurity
 AND has_table_privilege('placeai_render_runtime',c.oid,'SELECT')
 AND has_table_privilege('placeai_render_runtime',c.oid,'INSERT')
 AND has_table_privilege('placeai_render_runtime',c.oid,'UPDATE')
 AND has_table_privilege('placeai_render_runtime',c.oid,'DELETE')
 AND NOT has_table_privilege('anon',c.oid,'SELECT,INSERT,UPDATE,DELETE')
 AND NOT has_table_privilege('authenticated',c.oid,'SELECT,INSERT,UPDATE,DELETE'))
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relname IN
 ('learning_video_enrollments','learning_video_viewer_progress','learning_video_narration')
""")).scalar()
    if not valid:
        raise RuntimeError("SHARED_VIDEO_PRIVATE_ACCESS_NOT_PROVISIONED")


def downgrade():
    # Rollback must preserve shared videos and student progress.
    pass
