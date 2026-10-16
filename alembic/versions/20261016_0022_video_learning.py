"""Private video learning courses, rendered media and per-lesson progress."""
from alembic import op
import sqlalchemy as sa

revision = "20261016_0022"
down_revision = "a35d4cded877"
branch_labels = None
depends_on = None

DDL = """
CREATE TABLE IF NOT EXISTS learning_video_courses (
	id VARCHAR NOT NULL, 
	user_id VARCHAR NOT NULL, 
	request_id VARCHAR(80) NOT NULL, 
	title VARCHAR(240) NOT NULL, 
	input_json TEXT NOT NULL, 
	state VARCHAR(24) NOT NULL, 
	plan_json TEXT NOT NULL, 
	sources_json TEXT NOT NULL, 
	evidence TEXT NOT NULL, 
	attempts INTEGER NOT NULL, 
	error_code VARCHAR(80), 
	lease_token VARCHAR(40), 
	lease_until TIMESTAMP WITHOUT TIME ZONE, 
	available_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_video_course_request UNIQUE (user_id, request_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_video_course_owner ON learning_video_courses (user_id, created_at);
ALTER TABLE public.learning_video_courses ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.learning_video_courses FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.learning_video_courses TO service_role, placeai_render_runtime;
DROP POLICY IF EXISTS placeai_video_runtime ON public.learning_video_courses;
CREATE POLICY placeai_video_runtime ON public.learning_video_courses FOR ALL TO placeai_render_runtime USING (true) WITH CHECK (true);
CREATE TABLE IF NOT EXISTS learning_video_lessons (
	id VARCHAR NOT NULL, 
	course_id VARCHAR NOT NULL, 
	position INTEGER NOT NULL, 
	title VARCHAR(240) NOT NULL, 
	state VARCHAR(24) NOT NULL, 
	content_json TEXT NOT NULL, 
	video_data BYTEA, 
	duration_seconds FLOAT NOT NULL, 
	attempts INTEGER NOT NULL, 
	error_code VARCHAR(80), 
	lease_token VARCHAR(40), 
	lease_until TIMESTAMP WITHOUT TIME ZONE, 
	available_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_video_lesson_position UNIQUE (course_id, position), 
	FOREIGN KEY(course_id) REFERENCES learning_video_courses (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_video_lesson_queue ON learning_video_lessons (state, available_at);
ALTER TABLE public.learning_video_lessons ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.learning_video_lessons FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.learning_video_lessons TO service_role, placeai_render_runtime;
DROP POLICY IF EXISTS placeai_video_runtime ON public.learning_video_lessons;
CREATE POLICY placeai_video_runtime ON public.learning_video_lessons FOR ALL TO placeai_render_runtime USING (true) WITH CHECK (true);
CREATE TABLE IF NOT EXISTS learning_video_progress (
	lesson_id VARCHAR NOT NULL, 
	position_seconds FLOAT NOT NULL, 
	watched_seconds FLOAT NOT NULL, 
	coverage_json TEXT NOT NULL, 
	video_completed BOOLEAN NOT NULL, 
	practice_completed BOOLEAN NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (lesson_id), 
	FOREIGN KEY(lesson_id) REFERENCES learning_video_lessons (id) ON DELETE CASCADE
);
ALTER TABLE public.learning_video_progress ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.learning_video_progress FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.learning_video_progress TO service_role, placeai_render_runtime;
DROP POLICY IF EXISTS placeai_video_runtime ON public.learning_video_progress;
CREATE POLICY placeai_video_runtime ON public.learning_video_progress FOR ALL TO placeai_render_runtime USING (true) WITH CHECK (true);
"""


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        from app.models import VideoCourse, VideoLesson, VideoProgress
        for model in (VideoCourse, VideoLesson, VideoProgress):
            model.__table__.create(bind, checkfirst=True)
        return
    if bind.execute(sa.text("SELECT current_user")).scalar() != "placeai_render_runtime":
        for statement in DDL.split(";"):
            if statement.strip():
                bind.execute(sa.text(statement))
    valid = bind.execute(sa.text("""
      SELECT count(*)=3 AND bool_and(c.relrowsecurity
        AND has_table_privilege('placeai_render_runtime',c.oid,'SELECT')
        AND has_table_privilege('placeai_render_runtime',c.oid,'INSERT')
        AND has_table_privilege('placeai_render_runtime',c.oid,'UPDATE')
        AND has_table_privilege('placeai_render_runtime',c.oid,'DELETE')
        AND NOT has_table_privilege('anon',c.oid,'SELECT,INSERT,UPDATE,DELETE')
        AND NOT has_table_privilege('authenticated',c.oid,'SELECT,INSERT,UPDATE,DELETE')
        AND EXISTS (SELECT 1 FROM pg_policies p WHERE p.schemaname='public'
          AND p.tablename=c.relname AND p.policyname='placeai_video_runtime'
          AND p.qual='true' AND p.with_check='true'
          AND 'placeai_render_runtime'::name=ANY(p.roles)))
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='public' AND c.relname IN
        ('learning_video_courses','learning_video_lessons','learning_video_progress')
    """)).scalar()
    if not valid:
        raise RuntimeError("VIDEO_LEARNING_PRIVATE_ACCESS_NOT_PROVISIONED")


def downgrade():
    # Preserve students' courses and viewing history when rolling application code back.
    pass
