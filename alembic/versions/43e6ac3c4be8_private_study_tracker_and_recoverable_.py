"""Private study tracker and recoverable notebooks. Existing content is retained."""
from alembic import op
import sqlalchemy as sa
revision='43e6ac3c4be8'
down_revision='20261017_0023'
branch_labels=None
depends_on=None
DDL='ALTER TABLE public.learning_notebooks ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;\nALTER TABLE public.learning_notebooks ADD COLUMN IF NOT EXISTS deleted_state VARCHAR(24);\n\nCREATE TABLE IF NOT EXISTS study_plans (\n\tid VARCHAR NOT NULL, \n\tuser_id VARCHAR NOT NULL, \n\ttitle VARCHAR(180) NOT NULL, \n\troadmap_id VARCHAR, \n\tdaily_minutes INTEGER NOT NULL, \n\ttarget_date DATE, \n\ttimezone VARCHAR(64) NOT NULL, \n\tpaused BOOLEAN NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE\n)\n\n;\nCREATE INDEX IF NOT EXISTS ix_study_plan_owner ON study_plans (user_id, created_at);\nALTER TABLE public.study_plans ENABLE ROW LEVEL SECURITY;\nREVOKE ALL ON public.study_plans FROM PUBLIC,anon,authenticated;\nGRANT SELECT,INSERT,UPDATE,DELETE ON public.study_plans TO service_role,placeai_render_runtime;\nDROP POLICY IF EXISTS placeai_study_runtime ON public.study_plans;\nCREATE POLICY placeai_study_runtime ON public.study_plans FOR ALL TO placeai_render_runtime USING (true) WITH CHECK (true);\n\nCREATE TABLE IF NOT EXISTS study_goals (\n\tid VARCHAR NOT NULL, \n\tplan_id VARCHAR NOT NULL, \n\tkind VARCHAR(20) NOT NULL, \n\tresource_id VARCHAR(100) NOT NULL, \n\ttitle VARCHAR(240) NOT NULL, \n\ttarget INTEGER NOT NULL, \n\tmanual_completed INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_study_goal_resource UNIQUE (plan_id, kind, resource_id), \n\tFOREIGN KEY(plan_id) REFERENCES study_plans (id) ON DELETE CASCADE\n)\n\n;\nCREATE INDEX IF NOT EXISTS ix_study_goals_plan_id ON study_goals (plan_id);\nALTER TABLE public.study_goals ENABLE ROW LEVEL SECURITY;\nREVOKE ALL ON public.study_goals FROM PUBLIC,anon,authenticated;\nGRANT SELECT,INSERT,UPDATE,DELETE ON public.study_goals TO service_role,placeai_render_runtime;\nDROP POLICY IF EXISTS placeai_study_runtime ON public.study_goals;\nCREATE POLICY placeai_study_runtime ON public.study_goals FOR ALL TO placeai_render_runtime USING (true) WITH CHECK (true);\n\nCREATE TABLE IF NOT EXISTS learning_notebook_progress (\n\tnotebook_id VARCHAR NOT NULL, \n\tsection_key VARCHAR(24) NOT NULL, \n\tcompleted BOOLEAN NOT NULL, \n\tcompleted_at TIMESTAMP WITHOUT TIME ZONE, \n\tlast_read_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tsource VARCHAR(12) NOT NULL, \n\tlast_event_id VARCHAR(36), \n\tPRIMARY KEY (notebook_id, section_key), \n\tFOREIGN KEY(notebook_id) REFERENCES learning_notebooks (id) ON DELETE CASCADE\n)\n\n;\nALTER TABLE public.learning_notebook_progress ENABLE ROW LEVEL SECURITY;\nREVOKE ALL ON public.learning_notebook_progress FROM PUBLIC,anon,authenticated;\nGRANT SELECT,INSERT,UPDATE,DELETE ON public.learning_notebook_progress TO service_role,placeai_render_runtime;\nDROP POLICY IF EXISTS placeai_study_runtime ON public.learning_notebook_progress;\nCREATE POLICY placeai_study_runtime ON public.learning_notebook_progress FOR ALL TO placeai_render_runtime USING (true) WITH CHECK (true);\n\nCREATE TABLE IF NOT EXISTS study_daily_activity (\n\tuser_id VARCHAR NOT NULL, \n\tday DATE NOT NULL, \n\tnotes_seconds INTEGER NOT NULL, \n\tvideo_seconds INTEGER NOT NULL, \n\tsections_completed INTEGER NOT NULL, \n\tlast_pulse_at TIMESTAMP WITHOUT TIME ZONE, \n\tPRIMARY KEY (user_id, day), \n\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE\n)\n\n;\nALTER TABLE public.study_daily_activity ENABLE ROW LEVEL SECURITY;\nREVOKE ALL ON public.study_daily_activity FROM PUBLIC,anon,authenticated;\nGRANT SELECT,INSERT,UPDATE,DELETE ON public.study_daily_activity TO service_role,placeai_render_runtime;\nDROP POLICY IF EXISTS placeai_study_runtime ON public.study_daily_activity;\nCREATE POLICY placeai_study_runtime ON public.study_daily_activity FOR ALL TO placeai_render_runtime USING (true) WITH CHECK (true);\n'
TABLES=('study_plans','study_goals','learning_notebook_progress','study_daily_activity')
def upgrade():
    bind=op.get_bind()
    if bind.dialect.name != 'postgresql':
        from app.study_models import StudyPlan,StudyGoal,NotebookProgress,StudyDaily
        columns={c['name'] for c in sa.inspect(bind).get_columns('learning_notebooks')}
        if 'deleted_at' not in columns:op.add_column('learning_notebooks',sa.Column('deleted_at',sa.DateTime()))
        if 'deleted_state' not in columns:op.add_column('learning_notebooks',sa.Column('deleted_state',sa.String(24)))
        for model in (StudyPlan,StudyGoal,NotebookProgress,StudyDaily):model.__table__.create(bind,checkfirst=True)
        return
    if bind.execute(sa.text('SELECT current_user')).scalar() != 'placeai_render_runtime':
        for statement in DDL.split(';'):
            if statement.strip():bind.execute(sa.text(statement))
    for table in TABLES:
        valid=bind.execute(sa.text("""SELECT c.relrowsecurity
            AND NOT has_table_privilege('anon',c.oid,'SELECT,INSERT,UPDATE,DELETE')
            AND NOT has_table_privilege('authenticated',c.oid,'SELECT,INSERT,UPDATE,DELETE')
            AND has_table_privilege('placeai_render_runtime',c.oid,'SELECT,INSERT,UPDATE,DELETE')
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relname=:name"""),{'name':table}).scalar()
        if not valid:raise RuntimeError('Private study schema must be provisioned before deploying this release')
    columns={c['name'] for c in sa.inspect(bind).get_columns('learning_notebooks',schema='public')}
    if not {'deleted_at','deleted_state'}<=columns:raise RuntimeError('Notebook recovery columns are missing')
def downgrade():
    raise RuntimeError('Forward-only: preserve student study records and deleted-notebook recovery')
