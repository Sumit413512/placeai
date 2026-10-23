from __future__ import annotations

import json
import os
from datetime import timedelta

import httpx

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.ai_rate_limit import student_ai_guard
from app.database import get_db
from app.dependencies import require_student
from app.learning_content import LearningRequest
from app.models import LearningNotebook, LearningRuntime, User, utcnow

router = APIRouter(prefix="/learning-hub", tags=["Learning Hub"])


def generation_available(db):
    runtime = db.get(LearningRuntime, 1)
    return bool(runtime and runtime.provider_configured)


def wake_worker():
    # The fixed, existing PlaceAI host receives no student data or credentials.
    # A health request wakes Render after free-instance idle suspension.
    if os.getenv("VERCEL") != "1":
        return
    try:
        httpx.get("https://placeai-production.onrender.com/health", timeout=8)
    except httpx.HTTPError:
        pass


def owned(db, notebook_id, user):
    row = db.query(LearningNotebook).filter_by(id=notebook_id, user_id=user.id).first()
    if not row:
        raise HTTPException(404, "Learning notebook not found")
    return row


def serialize(row, *, detail=False):
    chapters = json.loads(row.chapters_json)
    request = json.loads(row.input_json)
    plan = json.loads(row.plan_json)
    total = len(plan.get("chapters", [])) or request.get("chapters") or 0
    review = plan.get("publication_review") or {}
    checked = request.get("standard_version", 1) < 2 or (
        review.get("passed") is True and review.get("version") == 2
        and review.get("chapters_checked") == total)
    ready = row.state == "ready" and total > 0 and len(chapters) == total and checked
    result = {"id": row.id, "title": row.title, "status": row.state,
              "completed_chapters": len(chapters), "total_chapters": total,
              "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
              "error_code": row.error_code, "retry_after_seconds": 8,
              "preparation_stage": "ready" if ready else "needs_attention" if row.state == "failed" else
                  "waiting_capacity" if row.error_code == "LEARNING_PROVIDER_CAPACITY" else
                  "checking" if total and len(chapters) == total else "preparing",
              "pdf_available": ready, "ready_to_begin": ready}
    if detail:
        result.update(input={k: v for k, v in request.items() if k != "request_id"},
                      plan={k: v for k, v in plan.items() if k != "draft"}, chapters=chapters if ready else [],
                      sources=json.loads(row.sources_json))
    return result


@router.get("")
def library(background_tasks: BackgroundTasks, user: User = Depends(require_student), db: Session = Depends(get_db)):
    rows = db.query(LearningNotebook).filter_by(user_id=user.id).order_by(
        LearningNotebook.created_at.desc()).limit(50).all()
    runtime = db.get(LearningRuntime, 1)
    if not runtime or runtime.checked_at < utcnow() - timedelta(minutes=2):
        background_tasks.add_task(wake_worker)
    return {"items": [serialize(row) for row in rows], "generation_available": generation_available(db)}


@router.post("", status_code=202, dependencies=[Depends(student_ai_guard)])
def create(body: LearningRequest, background_tasks: BackgroundTasks,
           user: User = Depends(require_student), db: Session = Depends(get_db)):
    # A user-row lock serializes duplicate admission and concurrent tabs for this owner.
    db.query(User).filter_by(id=user.id).with_for_update().one()
    existing = db.query(LearningNotebook).filter_by(user_id=user.id, request_id=body.request_id).first()
    def current_standard(request):
        return request.model_copy(update={"standard_version": 2, "authoring_version": 2,
                                          "chapters": None, "level": "beginner", "goals": ""})
    if existing:
        previous = LearningRequest.model_validate_json(existing.input_json)
        incoming = current_standard(body) if previous.standard_version >= 2 else body
        if previous.model_dump(exclude={"authoring_version"}) != incoming.model_dump(exclude={"authoring_version"}):
            raise HTTPException(409, "This request identifier belongs to different learning preferences")
        return serialize(existing, detail=True)
    # Standards are server policy, never a caller-controlled quality downgrade.
    # Previously saved v1 notebooks above keep their exact idempotency contract.
    body = current_standard(body)
    if not generation_available(db):
        raise HTTPException(503, "Learning Hub research is temporarily unavailable. Please try again later.")
    if db.query(LearningNotebook).filter(LearningNotebook.user_id == user.id,
                                        LearningNotebook.state.in_(["queued", "running", "retrying"])).first():
        raise HTTPException(409, "Your current notebook is still being prepared. Open it to see progress.")
    row = LearningNotebook(user_id=user.id, request_id=body.request_id,
                           title=body.topic, input_json=body.model_dump_json())
    db.add(row)
    db.commit()
    db.refresh(row)
    background_tasks.add_task(wake_worker)
    return serialize(row, detail=True)


@router.get("/{notebook_id}")
def get_notebook(notebook_id: str, user: User = Depends(require_student), db: Session = Depends(get_db)):
    return serialize(owned(db, notebook_id, user), detail=True)


@router.post("/{notebook_id}/retry", dependencies=[Depends(student_ai_guard)])
def retry(notebook_id: str, background_tasks: BackgroundTasks,
          user: User = Depends(require_student), db: Session = Depends(get_db)):
    db.query(User).filter_by(id=user.id).with_for_update().one()
    row = owned(db, notebook_id, user)
    if row.state != "failed":
        return serialize(row, detail=True)
    if not generation_available(db):
        raise HTTPException(503, "Learning Hub research is temporarily unavailable.")
    if db.query(LearningNotebook).filter(LearningNotebook.user_id == user.id,
                                        LearningNotebook.state.in_(["queued", "running", "retrying"])).first():
        raise HTTPException(409, "Another notebook is still being prepared")
    row.state, row.attempts, row.error_code, row.available_at = "queued", 0, None, utcnow()
    db.commit()
    background_tasks.add_task(wake_worker)
    return serialize(row, detail=True)


@router.get("/{notebook_id}/pdf")
def download(notebook_id: str, user: User = Depends(require_student), db: Session = Depends(get_db)):
    row = owned(db, notebook_id, user)
    if not serialize(row)["ready_to_begin"]:
        raise HTTPException(409, "The complete PDF will be available when all chapters are ready")
    from app.learning_pdf import render_notebook
    data = render_notebook(serialize(row, detail=True))
    return Response(data, media_type="application/pdf", headers={
        "Content-Disposition": 'attachment; filename="PlaceAI-Learning-Notes.pdf"',
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })
