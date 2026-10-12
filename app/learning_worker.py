"""One resumable chapter per lease; independent from assessment grading capacity."""
from __future__ import annotations

import json
import logging
import signal
from threading import Event, Thread
from datetime import timedelta
from uuid import uuid4

from pydantic import ValidationError

from sqlalchemy import Boolean, DateTime, bindparam, or_, text
from sqlalchemy.orm import sessionmaker

from app.database import engine
from app.models import LearningNotebook, LearningRuntime, User, UserRole, utcnow
from app.learning_content import LearningRequest, LearningPlan, LearningChapter, Subtopic, validate_chapter
from app import learning_ai

LOGGER = logging.getLogger("placeai.learning.worker")
Session = sessionmaker(bind=engine, expire_on_commit=False)
LEASE_SECONDS = 600


def repair_structure(raw, evidence):
    """Repair provider schema deviations before accessing nested teaching fields."""
    for attempt in range(3):
        try:
            LearningChapter.model_validate(raw)
            return raw
        except ValidationError as error:
            structural = [item for item in error.errors()
                          if item["type"] not in {"string_too_short", "value_error"}]
            if not structural:
                return raw  # Depth is expanded and checked by validate_material.
            if attempt == 2:
                raise
            corrected, _ = learning_ai.generate_json(
                "Repair this chapter's JSON structure to match the supplied schema exactly. "
                "Preserve all valid teaching paragraphs, code, examples and citations. "
                "Use expected_result for example outcomes; no unexpected fields are allowed. "
                "Supply missing fields using the retrieved evidence, with valid numbered source_ids. "
                "Do not shorten or summarize the chapter. Return the complete corrected chapter.\n"
                "INVALID FIELD PATHS:\n" + json.dumps([
                    {"path": list(item["loc"]), "type": item["type"]} for item in structural
                ]) + "\nCHAPTER:\n" + json.dumps(raw) + "\nLIVE EVIDENCE:\n" + evidence,
                LearningChapter.model_json_schema(),
            )
            raw = corrected
    raise ValueError("Learning chapter structure could not be repaired")


def validate_material(raw, planned, source_count, programming, evidence):
    for attempt in range(3):
        try:
            return validate_chapter(raw, planned, source_count, programming)
        except ValidationError as error:
            errors = error.errors()
            if attempt == 2 or any(item["type"] != "string_too_short" for item in errors):
                raise
            fields, targets = [], {}
            for item in errors:
                location = item["loc"]
                parent = raw
                for key in location[:-1]: parent = parent[key]
                path = ".".join(map(str, location))
                targets[path] = (parent, location[-1])
                fields.append({"path": path, "minimum_characters": item["ctx"]["min_length"],
                               "current_value": parent[location[-1]], "section_context": parent})
            repaired, _ = learning_ai.generate_json(
                "Improve ONLY the listed short fields. Keep their meaning and provide substantive explanations, "
                "worked reasoning or expected-output context. Do not pad or repeat. Each replacement must be "
                "comfortably longer than its minimum_characters. For solution/explanation/expected_result fields, "
                "include the actual answer PLUS at least THREE full sentences explaining how and why it works. "
                "Never return code alone. For titles/labels, keep a concise descriptive name. "
                "Return the exact path and full replacement text "
                "for every listed field.\nFIELDS:\n" + json.dumps(fields) + "\nLIVE EVIDENCE:\n" + evidence,
                {"type": "object", "properties": {"repairs": {"type": "array", "items": {
                 "type": "object", "properties": {"path": {"type": "string"}, "value": {"type": "string"}},
                 "required": ["path", "value"], "additionalProperties": False}}},
                 "required": ["repairs"], "additionalProperties": False},
            )
            replacements = repaired.get("repairs", [])
            if not isinstance(replacements, list) or len(replacements) != len(targets):
                raise ValueError("Every short field must receive an explanation")
            seen = set()
            for replacement in replacements:
                path = replacement.get("path")
                if path not in targets or path in seen or not isinstance(replacement.get("value"), str):
                    raise ValueError("Repairs must target only the requested teaching fields")
                seen.add(path)
                parent, key = targets[path]
                parent[key] = replacement["value"]


def heartbeat(db):
    now = utcnow()
    runtime = db.get(LearningRuntime, 1)
    if runtime and runtime.checked_at > now - timedelta(seconds=30):
        return runtime.provider_configured
    available = learning_ai.configured()
    db.execute(text("""INSERT INTO learning_runtime(id, provider_configured, checked_at)
        VALUES(1, :available, :now) ON CONFLICT(id) DO UPDATE
        SET provider_configured=excluded.provider_configured, checked_at=excluded.checked_at""").bindparams(
            bindparam("available", type_=Boolean()), bindparam("now", type_=DateTime())),
        {"available": available, "now": now})
    db.commit()
    return available


def claim(db):
    now = utcnow()
    if db.bind.dialect.name == "postgresql":
        # Serialize admission across Render instances; do not share the assessment gate.
        if not db.execute(text("SELECT pg_try_advisory_xact_lock(742081320)")).scalar():
            db.rollback()
            return None
    if db.query(LearningNotebook).filter(LearningNotebook.state == "running",
                                         LearningNotebook.lease_until > now).first():
        db.commit()
        return None
    row = db.query(LearningNotebook).filter(
        LearningNotebook.available_at <= now,
        or_(LearningNotebook.state.in_(["queued", "retrying"]),
            (LearningNotebook.state == "running") & (LearningNotebook.lease_until <= now)),
    ).order_by(LearningNotebook.available_at, LearningNotebook.created_at).with_for_update(skip_locked=True).first()
    if not row:
        db.commit()
        return None
    row.state = "running"
    row.lease_token = uuid4().hex
    row.lease_until = now + timedelta(seconds=LEASE_SECONDS)
    row.attempts += 1
    db.commit()
    return row.id, row.lease_token


def process(item, sessions=Session):
    done = Event()
    def renew():
        while not done.wait(30):
            try:
                with sessions() as db:
                    updated = db.query(LearningNotebook).filter_by(
                        id=item[0], lease_token=item[1], state="running"
                    ).update({LearningNotebook.lease_until: utcnow() + timedelta(seconds=LEASE_SECONDS)})
                    db.commit()
                if not updated:
                    return
            except Exception as error:
                LOGGER.warning("Learning lease renewal unavailable error_type=%s", type(error).__name__)
    renewal = Thread(target=renew, daemon=True, name="learning-lease-renewal")
    renewal.start()
    try:
        _process(item, sessions)
    finally:
        done.set()
        renewal.join(timeout=2)


def _process(item, sessions):
    notebook_id, token = item
    try:
        with sessions() as db:
            row = db.get(LearningNotebook, notebook_id)
            if not row or row.lease_token != token:
                return
            user = db.get(User, row.user_id)
            if not user or not user.is_active or user.role != UserRole.student:
                raise RuntimeError("LEARNING_OWNER_UNAVAILABLE")
            request = LearningRequest.model_validate_json(row.input_json)
            plan_data = json.loads(row.plan_json)
            completed = json.loads(row.chapters_json)
            sources = json.loads(row.sources_json)
            evidence = row.evidence
        preferences = request.model_dump(exclude={"request_id"})
        if not plan_data:
            evidence, sources, research_model = learning_ai.research(json.dumps(preferences))
            raw, model = learning_ai.generate_json(
                "Create a complete, progressively ordered textbook outline with EXACTLY "
                f"{request.chapters} chapters and 3-6 specific subtopics per chapter. "
                "Cover foundations, practical use, pitfalls, deeper concepts and a concluding project. "
                "SQL must distinguish the chosen dialect; if unspecified use PostgreSQL and explain portability. "
                "No duplicate or filler chapters.\nLEARNER DATA:\n" + json.dumps(preferences)
                + "\nLIVE RESEARCH:\n" + evidence, LearningPlan.model_json_schema(),
            )
            plan = LearningPlan.model_validate(raw)
            if len(plan.chapters) != request.chapters:
                raise ValueError("Learning outline chapter count mismatch")
            update = {"plan_json": plan.model_dump_json(), "sources_json": json.dumps(sources),
                      "evidence": evidence, "title": plan.title, "provider": research_model + ";" + model}
        else:
            plan = LearningPlan.model_validate(plan_data)
            index = len(completed)
            planned = plan.chapters[index]
            # Research each chapter separately so detailed explanations have relevant current evidence.
            memo, chapter_sources, research_model = learning_ai.research(json.dumps({
                "learner": preferences, "chapter": planned.model_dump(),
            }))
            for source in chapter_sources:
                if len(sources) < 160 and not any(existing["url"] == source["url"] for existing in sources):
                    sources.append(source)
            numbered = [{"id": i, **s} for i, s in enumerate(sources, 1)]
            raw, model = learning_ai.generate_json(
                "Write ONE complete textbook chapter, not a summary. Target 1,200-1,800 teaching words; "
                "at least 800 words of explanation excluding code/exercises are required. "
                "Explain every listed subtopic in the same order and with the EXACT title. "
                "Write at least 300 words of substantive teaching in EACH subtopic explanation; do not compress the explanations. "
                "Give definitions, why/how, step-by-step reasoning and realistic examples. "
                "Include at least two worked examples (code for programming topics), "
                "explain each important code statement and expected output. Do not execute code. "
                "Include 1-3 accurate diagrams as node/edge data, explaining what each relationship means. "
                "Node labels must be readable and concise. Include pitfalls, solved exercises and takeaways. "
                "Use plain text paragraphs separated by newlines; no HTML or Markdown styling in prose. "
                "Use source_ids to cite numbered retrieved sources for each subtopic. "
                "Preserve dialect/version caveats; distinguish sourced facts from illustrative examples. "
                "Examples must be internally consistent.\nLEARNER DATA:\n" + json.dumps(preferences)
                + "\nCHAPTER:\n" + planned.model_dump_json()
                + "\nEVIDENCE:\n" + memo + "\nNUMBERED SOURCES:\n" + json.dumps(numbered),
                LearningChapter.model_json_schema(),
            )
            raw = repair_structure(raw, memo)
            for _ in range(2):
                if not isinstance(raw.get("subtopics"), list):
                    break
                short_subtopics = [s for s in raw["subtopics"] if isinstance(s, dict)
                                   and len(str(s.get("explanation", ""))) < 1600]
                if not short_subtopics:
                    break
                expanded, model = learning_ai.generate_json(
                    "Write NEW additional teaching paragraphs for EACH supplied subtopic. "
                    "These paragraphs will be APPENDED to the existing explanation, so do not repeat it. "
                    "Add concrete worked reasoning, a practical scenario, important edge cases or deeper context. "
                    "Write 200-300 NEW words for EACH subtopic. Preserve the EXACT titles, order and valid source_ids. "
                    "Return only an object with the subtopics array; explanation contains only the NEW paragraphs.\nLEARNER:\n" + json.dumps(preferences)
                    + "\nCURRENT SUBTOPICS:\n" + json.dumps(short_subtopics)
                    + "\nLIVE EVIDENCE:\n" + memo + "\nSOURCE IDS:\n" + json.dumps(numbered),
                    {"type": "object", "properties": {"subtopics": {"type": "array",
                     "items": Subtopic.model_json_schema()}}, "required": ["subtopics"],
                     "additionalProperties": False},
                )
                additions = expanded.get("subtopics", [])
                if not isinstance(additions, list) or len(additions) != len(short_subtopics):
                    raise ValueError("Every subtopic needs its own additional explanation")
                for subtopic, addition in zip(short_subtopics, additions):
                    if not isinstance(addition, dict) or not isinstance(addition.get("explanation"), str) or not isinstance(addition.get("source_ids"), list):
                        raise ValueError("Additional explanations must include teaching and citations")
                    if subtopic.get("title") != addition.get("title"):
                        raise ValueError("Additional explanations must match their original subtopics")
                    subtopic["explanation"] += "\n\n" + addition["explanation"]
                    subtopic["source_ids"] = list(dict.fromkeys(subtopic["source_ids"] + addition["source_ids"]))
            programming = bool(request.programming_language) or request.topic.casefold() in {
                "sql", "python", "java", "javascript", "typescript", "c", "c++", "c#", "rust", "go", "react",
            }
            chapter = validate_material(raw, planned, len(sources), programming, memo)
            learning_ai.review_chapter(chapter.model_dump(), memo, preferences)
            completed.append(chapter.model_dump())
            update = {"chapters_json": json.dumps(completed), "sources_json": json.dumps(sources),
                      "provider": research_model + ";" + model}
        with sessions() as db:
            row = db.query(LearningNotebook).filter_by(id=notebook_id).with_for_update().first()
            if not row or row.lease_token != token or row.lease_until <= utcnow():
                return
            for key, value in update.items():
                setattr(row, key, value)
            row.state = "ready" if len(completed) == request.chapters else "queued"
            row.attempts = 0
            row.error_code = None
            row.lease_token = None
            row.lease_until = None
            row.available_at = utcnow()
            db.commit()
    except Exception as error:
        fields = [".".join(map(str, item["loc"])) for item in error.errors()] if isinstance(error, ValidationError) else []
        LOGGER.warning("Learning stage deferred error_type=%s validation_fields=%s", type(error).__name__, fields)
        with sessions() as db:
            row = db.query(LearningNotebook).filter_by(id=notebook_id).with_for_update().first()
            if not row or row.lease_token != token:
                return
            row.state = "failed" if row.attempts >= 4 else "retrying"
            row.error_code = "CONTENT_VALIDATION" if isinstance(error, ValueError) else "RESEARCH_OR_AUTHOR_UNAVAILABLE"
            row.available_at = utcnow() + timedelta(seconds=min(60 * 2 ** row.attempts, 600))
            row.lease_until = None
            row.lease_token = None
            db.commit()


def run(stop):
    while not stop.is_set():
        try:
            with Session() as db:
                item = claim(db) if heartbeat(db) else None
            if item:
                process(item)
                continue
        except Exception as error:
            LOGGER.warning("Learning queue unavailable error_type=%s", type(error).__name__)
        stop.wait(3)


if __name__ == "__main__":
    stop_event = Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop_event.set())
    logging.basicConfig(level=logging.INFO)
    run(stop_event)
