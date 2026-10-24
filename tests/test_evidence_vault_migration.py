import importlib.util
from pathlib import Path
from sqlalchemy import create_engine, text, inspect
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_evidence_migration_is_additive_repeat_safe_and_preserves_existing_documents():
    filename=Path(__file__).resolve().parents[1]/'alembic/versions/20261024_0025_resume_evidence_and_consent_based_.py'
    spec=importlib.util.spec_from_file_location('evidence_migration',filename)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    engine=create_engine('sqlite://')
    with engine.begin() as db:
        db.execute(text('CREATE TABLE student_profiles (id VARCHAR PRIMARY KEY, degree TEXT, cgpa FLOAT)'))
        db.execute(text('CREATE TABLE resumes (id VARCHAR PRIMARY KEY, filepath TEXT, ai_parsed_data_json TEXT)'))
        db.execute(text('CREATE TABLE student_documents (id VARCHAR PRIMARY KEY, filepath TEXT, visibility TEXT)'))
        db.execute(text("INSERT INTO student_profiles VALUES ('student','B.Tech',8.5)"))
        db.execute(text("INSERT INTO resumes VALUES ('resume','private-original.pdf','{}')"))
        db.execute(text("INSERT INTO student_documents VALUES ('document','private-marksheet.pdf','institution_only')"))
        module.op=Operations(MigrationContext.configure(db))
        module.upgrade();module.upgrade()
        assert db.execute(text('SELECT degree,cgpa FROM student_profiles')).one()==('B.Tech',8.5)
        assert db.execute(text('SELECT filepath FROM resumes')).scalar()=='private-original.pdf'
        document=db.execute(text('SELECT filepath,visibility,shared_at,shared_organization_id FROM student_documents')).one()
        assert document==('private-marksheet.pdf','institution_only',None,None)
        assert 'current_semester' in {x['name'] for x in inspect(db).get_columns('student_profiles')}
    engine.dispose()
