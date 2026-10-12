import io
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pypdf import PdfReader
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import learning_ai, learning_worker
from app.ai_rate_limit import student_ai_guard
from app.database import Base, get_db
from app.dependencies import get_current_user
from app.learning_content import LearningChapter, LearningPlan, validate_chapter
from app.models import LearningNotebook, LearningRuntime, User, UserRole, utcnow
from app.routers import learning_hub


def preferences(**changes):
    return {"topic": "SQL", "field": "Data engineering", "programming_language": "PostgreSQL",
            "level": "beginner", "goals": "Explain queries and joins in depth", "chapters": 8,
            "request_id": "isolated-learning-request-001", **changes}


def plan_data():
    return {"title": "SQL study notebook", "introduction": "Learn relational queries with a consistent PostgreSQL dialect. " * 4,
            "prerequisites": ["Access to a PostgreSQL practice database"],
            "chapters": [{"title": f"SQL chapter {i}", "objective": "Understand and apply this SQL concept through explained examples.",
                          "subtopics": ["Relational structure", "Query behavior", "Practical reasoning"]}
                         for i in range(1, 9)]}


def chapter_data():
    explanation = "This isolated test paragraph checks readable pagination and detailed teaching content without calling a paid AI provider. " * 20
    return {"title": "SQL chapter", "overview": "Work through the example and trace the query against the source tables. " * 3,
            "subtopics": [{"title": title, "explanation": explanation, "source_ids": [1]}
                         for title in ["Relational structure", "Query behavior", "Practical reasoning"]],
            "examples": [{"title": "Filter a table", "language": "SQL", "code": "SELECT name FROM students WHERE score >= 70;",
                          "explanation": "SELECT chooses the name column. FROM identifies the students table. WHERE retains rows with a qualifying score. " * 4,
                          "expected_result": "Names for students whose scores are at least seventy."} for _ in range(2)],
            "diagrams": [{"title": "Query data flow", "nodes": [{"id": "table", "label": "Students table"}, {"id": "filter", "label": "Score filter"}, {"id": "result", "label": "Qualifying names"}],
                          "edges": [{"source": "table", "target": "filter", "label": "Read candidate rows"}, {"source": "filter", "target": "result", "label": "Project name"}],
                          "explanation": "The diagram traces the logical flow from source rows through filtering to the selected output. " * 5}],
            "common_mistakes": ["Confusing logical query order with a physical execution plan.", "Using a dialect-specific function without noting the dialect."],
            "exercises": [{"question": "Write a query that selects students with a score of at least seventy.",
                           "solution": "Use SELECT to choose columns and a WHERE predicate to restrict rows. Check the table and column names against your schema before executing the query."} for _ in range(2)],
            "key_takeaways": ["Name the SQL dialect.", "Trace each clause against rows.", "Verify the expected output."]}


@pytest.fixture
def hub(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    db = sessions()
    owner = User(username="learning-owner", email="owner@example.invalid", hashed_password="isolated-test", role=UserRole.student, is_active=True)
    other = User(username="learning-other", email="other@example.invalid", hashed_password="isolated-test", role=UserRole.student, is_active=True)
    db.add_all([owner, other]); db.commit()
    db.add(LearningRuntime(id=1, provider_configured=True)); db.commit()
    actor = [owner]
    app = FastAPI(); app.include_router(learning_hub.router)
    def database():
        with sessions() as session:
            yield session
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = lambda: actor[0]
    app.dependency_overrides[student_ai_guard] = lambda: None
    monkeypatch.setattr(learning_ai, "configured", lambda: True)
    with TestClient(app) as client:
        yield SimpleNamespace(db=db, sessions=sessions, owner=owner, other=other, actor=actor, client=client)
    db.close(); engine.dispose()


def test_admission_is_saved_idempotent_and_private(hub):
    response = hub.client.post("/learning-hub", json=preferences())
    assert response.status_code == 202
    book = response.json()
    assert book["completed_chapters"] == 0 and not book["pdf_available"]
    assert hub.client.post("/learning-hub", json=preferences()).json()["id"] == book["id"]
    assert hub.client.post("/learning-hub", json=preferences(topic="Python")).status_code == 409
    assert hub.client.post("/learning-hub", json=preferences(request_id="another-learning-request-002")).status_code == 409
    assert hub.client.get(f"/learning-hub/{book['id']}/pdf").status_code == 409
    hub.actor[0] = hub.other
    assert hub.client.get("/learning-hub").json()["items"] == []
    for path, method in [("", "get"), ("/pdf", "get"), ("/retry", "post")]:
        assert getattr(hub.client, method)(f"/learning-hub/{book['id']}" + path).status_code == 404
    hub.actor[0] = SimpleNamespace(role=UserRole.recruiter)
    assert hub.client.get("/learning-hub").status_code == 403


def test_provider_outage_is_honest_and_does_not_create_fake_notes(hub, monkeypatch):
    monkeypatch.setattr(learning_ai, "configured", lambda: False)
    runtime = hub.db.get(LearningRuntime, 1)
    runtime.checked_at = utcnow() - timedelta(minutes=1)
    hub.db.commit()
    learning_worker.heartbeat(hub.db)
    assert hub.client.post("/learning-hub", json=preferences()).status_code == 503
    assert hub.db.query(LearningNotebook).count() == 0


def test_serverless_admission_uses_worker_readiness_not_local_api_secrets(hub, monkeypatch):
    monkeypatch.setattr(learning_ai, "configured", lambda: False)
    assert hub.client.get("/learning-hub").json()["generation_available"]
    assert hub.client.post("/learning-hub", json=preferences()).status_code == 202


def test_validation_rejects_short_notes_broken_diagrams_and_invented_sources():
    planned = LearningPlan.model_validate(plan_data()).chapters[0]
    chapter = chapter_data()
    assert validate_chapter(chapter, planned, 1, True).title == planned.title
    chapter["subtopics"][0]["source_ids"] = [99]
    with pytest.raises(ValueError): validate_chapter(chapter, planned, 1, True)
    chapter = chapter_data(); chapter["diagrams"][0]["edges"][0]["target"] = "missing"
    with pytest.raises(ValidationError): LearningChapter.model_validate(chapter)
    chapter = chapter_data()
    for sub in chapter["subtopics"]: sub["explanation"] = "Short filler explanation. " * 25
    with pytest.raises(ValidationError): LearningChapter.model_validate(chapter)


def test_short_exercise_solution_is_repaired_without_replacing_the_chapter(monkeypatch):
    raw = chapter_data()
    original = raw["subtopics"][0]["explanation"]
    raw["exercises"][1]["solution"] = "SELECT name FROM students;"
    replacement = "Select the name column from the students table. FROM identifies the source relation; every row is included because this query has no WHERE predicate."
    monkeypatch.setattr(learning_ai, "generate_json", lambda *_: (
        {"repairs": [{"path": "exercises.1.solution", "value": replacement}]}, "test:writer"))
    chapter = learning_worker.validate_material(raw, LearningPlan.model_validate(plan_data()).chapters[0], 1, True, "SQL evidence")
    assert chapter.exercises[1].solution == replacement
    assert chapter.subtopics[0].explanation == original.strip()
    assert chapter.examples[0].code == "SELECT name FROM students WHERE score >= 70;"


def test_provider_structure_is_repaired_before_nested_fields_are_accessed(monkeypatch):
    raw = chapter_data()
    expected = chapter_data()
    raw["examples"][0]["expected_symptom"] = raw["examples"][0].pop("expected_result")
    raw["subtopics"][0].pop("source_ids")
    calls = []
    def correct(task, schema):
        calls.append(task)
        return expected, "test:writer"
    monkeypatch.setattr(learning_ai, "generate_json", correct)
    repaired = learning_worker.repair_structure(raw, "Retrieved SQL evidence")
    chapter = validate_chapter(repaired, LearningPlan.model_validate(plan_data()).chapters[0], 1, True)
    assert chapter.examples[0].expected_result == expected["examples"][0]["expected_result"]
    assert chapter.subtopics[0].source_ids == [1]
    assert chapter.subtopics[0].explanation == expected["subtopics"][0]["explanation"].strip()
    assert len(calls) == 1


def test_provider_structure_repair_is_bounded_and_depth_remains_required(monkeypatch):
    raw = chapter_data()
    raw["examples"][0]["unexpected"] = "invalid"
    calls = []
    monkeypatch.setattr(learning_ai, "generate_json", lambda *_: (calls.append(1) or raw, "test:writer"))
    with pytest.raises(ValidationError): learning_worker.repair_structure(raw, "evidence")
    assert len(calls) == 2
    short = chapter_data()
    short["subtopics"][0]["explanation"] = "Too short."
    assert learning_worker.repair_structure(short, "evidence") is short
    with pytest.raises(ValidationError): LearningChapter.model_validate(short)


def test_field_repair_cannot_overwrite_unrequested_content(monkeypatch):
    raw = chapter_data()
    raw["exercises"][1]["solution"] = "SELECT name FROM students;"
    monkeypatch.setattr(learning_ai, "generate_json", lambda *_: (
        {"repairs": [{"path": "title", "value": "Unexpected replacement"}]}, "test:writer"))
    with pytest.raises(ValueError):
        learning_worker.validate_material(raw, LearningPlan.model_validate(plan_data()).chapters[0], 1, True, "SQL evidence")


def test_worker_saves_each_stage_resumes_and_never_publishes_partial_pdf(hub, monkeypatch):
    book = hub.client.post("/learning-hub", json=preferences()).json()
    sources = [{"url": "https://www.postgresql.org/docs/current/sql-select.html", "title": "SELECT"},
               {"url": "https://www.postgresql.org/docs/current/tutorial.html", "title": "Tutorial"},
               {"url": "https://www.postgresql.org/docs/current/queries.html", "title": "Queries"}]
    monkeypatch.setattr(learning_ai, "research", lambda _: ("Verified SQL evidence", sources, "test:research"))
    monkeypatch.setattr(learning_ai, "generate_json", lambda task, schema: (plan_data() if "EXACTLY" in task else chapter_data(), "test:writer"))
    monkeypatch.setattr(learning_ai, "review_chapter", lambda *_: None)
    def step():
        with hub.sessions() as db: item = learning_worker.claim(db)
        assert item
        learning_worker.process(item, hub.sessions)
    step()
    assert len(hub.client.get(f"/learning-hub/{book['id']}").json()["plan"]["chapters"]) == 8
    step()
    def outage(*_): raise RuntimeError("isolated outage")
    with monkeypatch.context() as patch:
        patch.setattr(learning_ai, "generate_json", outage)
        step()
    partial = hub.client.get(f"/learning-hub/{book['id']}").json()
    assert partial["status"] == "retrying" and partial["completed_chapters"] == 1
    assert not partial["pdf_available"]
    with hub.sessions() as db:
        row = db.get(LearningNotebook, book["id"]); row.available_at = utcnow(); db.commit()
    for _ in range(7): step()
    ready = hub.client.get(f"/learning-hub/{book['id']}").json()
    assert ready["status"] == "ready" and ready["completed_chapters"] == 8
    pdf = hub.client.get(f"/learning-hub/{book['id']}/pdf")
    assert pdf.status_code == 200 and pdf.headers["cache-control"] == "private, no-store"
    reader = PdfReader(io.BytesIO(pdf.content))
    assert len(reader.pages) >= 20
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "SQL chapter 8" in text and "Sources and further reading" in text and "Expected result" in text


def test_expired_lease_is_reclaimed_and_stale_writer_cannot_publish(hub, monkeypatch):
    book = hub.client.post("/learning-hub", json=preferences()).json()
    with hub.sessions() as db: old = learning_worker.claim(db)
    with hub.sessions() as db:
        row = db.get(LearningNotebook, book["id"]); row.lease_until = utcnow() - timedelta(seconds=1); db.commit()
    with hub.sessions() as db: new = learning_worker.claim(db)
    assert new[1] != old[1]
    monkeypatch.setattr(learning_ai, "research", lambda _: pytest.fail("Stale worker must stop before provider calls"))
    learning_worker.process(old, hub.sessions)
    assert hub.client.get(f"/learning-hub/{book['id']}").json()["completed_chapters"] == 0


def test_frontend_and_static_copies_are_synchronized():
    root = Path(__file__).resolve().parents[1]
    for filename in ["learning-hub.js", "learning-hub.css"]:
        assert (root / "app/static" / filename).read_bytes() == (root / "public/static" / filename).read_bytes()
    assert (root / "app/static/app.js").read_bytes() == (root / "public/static/app-core.js").read_bytes()
    assert "['Career','learning-hub','Learning Hub']" in (root / "app/static/app.js").read_text(encoding="utf-8")
