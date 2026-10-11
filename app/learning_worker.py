"""One resumable chapter per lease; independent from assessment grading capacity."""
from __future__ import annotations

import json
import logging
import signal
from threading import Event
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, bindparam, or_, text
from sqlalchemy.orm import sessionmaker

from app.database import engine
from app.models import LearningNotebook, LearningRuntime, User, UserRole, utcnow
from app.learning_content import LearningRequest, LearningPlan, LearningChapter, validate_chapter
from app import learning_ai

LOGGER = logging.getLogger("placeai.learning.worker")
Session = sessionmaker(bind=engine, expire_on_commit=False)
LEASE_SECONDS = 600


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
            programming = bool(request.programming_language) or request.topic.casefold() in {
                "sql", "python", "java", "javascript", "typescript", "c", "c++", "c#", "rust", "go", "react",
            }
            chapter = validate_chapter(raw, planned, len(sources), programming)
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
        LOGGER.warning("Learning stage deferred error_type=%s", type(error).__name__)
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
