import copy
import io
import json
from textwrap import wrap

import pytest
from pypdf import PdfReader

from app import learning_ai, learning_worker
from app.learning_content import LearningChapter, LearningRequest
from app.learning_quality import validate_standard
from app.models import LearningNotebook, utcnow
from test_learning_hub import hub, chapter_data, plan_data  # noqa: F401


def standard_chapter():
    raw = chapter_data()
    for sub in raw["subtopics"]:
        paragraphs = wrap(sub["explanation"], width=420, break_long_words=False)
        sub["explanation"] = "**Predicate** is a condition evaluated for each candidate row.\n- Check the condition against each row before choosing the output.\n\n" + "\n\n".join(paragraphs)
    original = raw["examples"][0]
    raw["examples"] = [{**copy.deepcopy(original), "title": "Example for " + sub["title"],
                        "subtopic": sub["title"]} for sub in raw["subtopics"]]
    raw["diagrams"][0]["subtopics"] = [raw["subtopics"][0]["title"]]
    return raw


def test_standard_rejects_missing_examples_dense_prose_and_unrelated_diagrams():
    raw = standard_chapter()
    assert validate_standard(LearningChapter.model_validate(raw))
    cases = []
    missing = copy.deepcopy(raw); missing["examples"][0]["subtopic"] = "Unrelated"; cases.append(missing)
    dense = copy.deepcopy(raw); dense["subtopics"][0]["explanation"] = dense["subtopics"][0]["explanation"].replace("\n", " "); cases.append(dense)
    diagram = copy.deepcopy(raw); diagram["diagrams"][0]["subtopics"] = ["Unrelated"]; cases.append(diagram)
    isolated = copy.deepcopy(raw); isolated["diagrams"][0]["nodes"].append({"id": "unused", "label": "Unrelated icon"}); cases.append(isolated)
    for invalid in cases:
        with pytest.raises(ValueError): validate_standard(LearningChapter.model_validate(invalid))


def test_new_requests_have_no_depth_but_saved_requests_keep_their_contract():
    new = LearningRequest(topic="SQL", request_id="standard-topic-request-001")
    assert new.standard_version == 2 and new.chapters is None
    old = LearningRequest(topic="SQL", chapters=8, request_id="legacy-topic-request-001")
    assert old.standard_version == 1 and old.chapters == 8


def test_v2_checks_and_pdf_must_finish_before_publication(hub, monkeypatch):
    book = hub.client.post("/learning-hub", json={"topic": "PostgreSQL predicates", "standard_version": 2,
        "request_id": "standard-worker-request-001"}).json()
    plan = plan_data(); plan["chapters"] = plan["chapters"][:1]
    chapter = standard_chapter()
    sources = [{"title": "PostgreSQL SELECT", "url": "https://www.postgresql.org/docs/current/sql-select.html"}]
    monkeypatch.setattr(learning_ai, "research", lambda _: ("SQL predicate evidence", sources, "isolated:research"))
    calls = []
    def generate(task, schema, **kwargs):
        calls.append(task)
        props = schema["properties"]
        if "approved" in props: result = {"approved": True, "issues": []}
        elif "chapters" in props: result = plan
        elif "concept" in props:
            title = task.split("CONCEPT: ", 1)[1].split("\n", 1)[0]
            result = {"concept": next(x for x in chapter["subtopics"] if x["title"] == title),
                      "example": next(x for x in chapter["examples"] if x["subtopic"] == title)}
        else: result = {k: v for k, v in chapter.items() if k not in {"subtopics", "examples"}}
        return result, "isolated:writer"
    monkeypatch.setattr(learning_ai, "generate_json", generate)
    monkeypatch.setattr(learning_ai, "review_chapter", lambda *_: None)
    def step():
        with hub.sessions() as db: item = learning_worker.claim(db)
        assert item
        learning_worker.process(item, hub.sessions)
    step(); step()
    partial = hub.client.get(f"/learning-hub/{book['id']}").json()
    assert partial["completed_chapters"] == 1 and partial["total_chapters"] == 1
    assert partial["preparation_stage"] == "checking" and not partial["pdf_available"]
    assert partial["chapters"] == []
    assert hub.client.get(f"/learning-hub/{book['id']}/pdf").status_code == 409
    step()
    ready = hub.client.get(f"/learning-hub/{book['id']}").json()
    assert ready["ready_to_begin"] and ready["plan"]["publication_review"]["passed"]
    assert ready["plan"]["publication_review"]["version"] == 2
    pdf = hub.client.get(f"/learning-hub/{book['id']}/pdf")
    reader = PdfReader(io.BytesIO(pdf.content))
    assert reader.outline and reader.pages
    assert any("Worked example" in page.extract_text() for page in reader.pages)
    # Finalization is local; it does not call the model again.
    assert len(calls) == 6


def test_v2_ready_flag_cannot_bypass_missing_publication_review(hub):
    row = LearningNotebook(user_id=hub.owner.id, request_id="publication-check-001", title="SQL",
        state="ready", input_json=json.dumps({"topic": "SQL", "standard_version": 2}),
        plan_json=json.dumps({**plan_data(), "chapters": plan_data()["chapters"][:1]}),
        chapters_json=json.dumps([standard_chapter()]))
    hub.db.add(row); hub.db.commit()
    assert not hub.client.get(f"/learning-hub/{row.id}").json()["pdf_available"]
    assert hub.client.get(f"/learning-hub/{row.id}/pdf").status_code == 409


def test_provider_interruption_resumes_after_saved_concept(hub, monkeypatch):
    book = hub.client.post("/learning-hub", json={"topic": "SQL", "standard_version": 2,
        "request_id": "standard-resume-request-001"}).json()
    plan = plan_data(); plan["chapters"] = plan["chapters"][:1]
    row = hub.db.get(LearningNotebook, book["id"]); row.plan_json = json.dumps(plan); hub.db.commit()
    chapter = standard_chapter()
    titles = [s["title"] for s in chapter["subtopics"]]
    authored = []; outage = [True]
    monkeypatch.setattr(learning_ai, "research", lambda _: ("SQL evidence", [{"title": "SQL", "url": "https://www.postgresql.org/docs/current/"}], "isolated:research"))
    monkeypatch.setattr(learning_ai, "review_chapter", lambda *_: None)
    def generate(task, schema, **kwargs):
        if "concept" in schema["properties"]:
            title = task.split("CONCEPT: ", 1)[1].split("\n", 1)[0]
            if title == titles[1] and outage[0]:
                outage[0] = False
                raise RuntimeError("isolated provider outage")
            authored.append(title)
            return {"concept": next(s for s in chapter["subtopics"] if s["title"] == title),
                    "example": next(e for e in chapter["examples"] if e["subtopic"] == title)}, "isolated:writer"
        return {k: v for k, v in chapter.items() if k not in {"subtopics", "examples"}}, "isolated:writer"
    monkeypatch.setattr(learning_ai, "generate_json", generate)
    def step():
        with hub.sessions() as db: item = learning_worker.claim(db)
        learning_worker.process(item, hub.sessions)
    step()
    hub.db.refresh(row)
    assert row.state == "retrying" and len(json.loads(row.plan_json)["draft"]["concepts"]) == 1
    assert "draft" not in hub.client.get(f"/learning-hub/{row.id}").json()["plan"]
    row.available_at = utcnow(); hub.db.commit()
    step()
    assert authored == titles  # First completed concept was not regenerated.
    step()
    assert hub.client.get(f"/learning-hub/{row.id}").json()["ready_to_begin"]
