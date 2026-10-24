import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, StrictInt
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_student
from app.models import utcnow
from app.rate_limit import enforce_rate_limit
from app.technical_practice import TechnicalPracticeAttempt, finish, questions

router = APIRouter(prefix='/technical-practice', tags=['Technical practice'])


class Start(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID


class Answer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question_id: StrictInt
    option: StrictInt


def owned(db, user, identifier, lock=False):
    query = db.query(TechnicalPracticeAttempt).filter_by(id=identifier, user_id=user.id)
    row = (query.with_for_update() if lock else query).first()
    if not row:
        raise HTTPException(404, 'Practice attempt not found')
    return row


def payload(row, db):
    if not row.result_json and utcnow() >= row.deadline_at:
        finish(row)
        db.commit()
    result = json.loads(row.result_json) if row.result_json else None
    return dict(id=row.id, version=row.version, deadline_at=row.deadline_at.isoformat() + 'Z',
                server_time=utcnow().isoformat() + 'Z', answers=json.loads(row.answers_json),
                questions=[{k: q[k] for k in ('id', 'section', 'question', 'options')} for q in json.loads(row.questions_json)],
                result=result)


@router.get('')
def history(user=Depends(require_student), db: Session = Depends(get_db)):
    rows = db.query(TechnicalPracticeAttempt).filter_by(user_id=user.id).order_by(TechnicalPracticeAttempt.created_at.desc()).limit(20).all()
    return [dict(id=r.id, created_at=r.created_at.isoformat() + 'Z',
                 score=json.loads(r.result_json)['score'] if r.result_json else None) for r in rows]


@router.post('/start')
def start(body: Start, request: Request, user=Depends(require_student), db: Session = Depends(get_db)):
    enforce_rate_limit(db, request, scope='technical-practice:start', identifier=user.id,
                       limit=12, window_seconds=600, block_seconds=600, include_client_address=False)
    # Lock the existing user row to serialise starts, including identical retries.
    from app.models import User
    db.query(User).filter_by(id=user.id).with_for_update().one()
    row = db.query(TechnicalPracticeAttempt).filter_by(user_id=user.id, request_id=str(body.request_id)).first()
    if not row:
        # Resume an active attempt instead of creating parallel timers.
        row = db.query(TechnicalPracticeAttempt).filter_by(user_id=user.id, result_json=None).filter(TechnicalPracticeAttempt.deadline_at > utcnow()).first()
    if not row:
        row = TechnicalPracticeAttempt(user_id=user.id, request_id=str(body.request_id), questions_json=json.dumps(questions()), answers_json='{}')
        db.add(row)
        db.commit()
        db.refresh(row)
    return payload(row, db)


@router.get('/{identifier}')
def get(identifier: str, user=Depends(require_student), db: Session = Depends(get_db)):
    return payload(owned(db, user, identifier, True), db)


@router.put('/{identifier}/answer')
def answer(identifier: str, body: Answer, user=Depends(require_student), db: Session = Depends(get_db)):
    row = owned(db, user, identifier, True)
    if row.result_json or utcnow() >= row.deadline_at:
        raise HTTPException(409, 'This practice attempt has ended. Open its report.')
    issued = json.loads(row.questions_json)
    question = next((q for q in issued if q['id'] == body.question_id), None)
    if question is None or not 0 <= body.option < len(question['options']):
        raise HTTPException(422, 'Choose a valid option for an issued question')
    answers = json.loads(row.answers_json)
    answers[str(body.question_id)] = body.option
    row.answers_json = json.dumps(answers)
    db.commit()
    return {'saved': True}


@router.post('/{identifier}/submit')
def submit(identifier: str, user=Depends(require_student), db: Session = Depends(get_db)):
    row = owned(db, user, identifier, True)
    finish(row)
    db.commit()
    return payload(row, db)
