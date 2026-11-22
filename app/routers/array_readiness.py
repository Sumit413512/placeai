"""Arrays practice for students and cohort actions for their placement office."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from app.array_readiness_models import ArrayReadiness
from app.database import get_db
from app.dependencies import require_institution_admin, require_student
from app.lesson_readiness import institution, roster
from app.models import StudentProfile, User
from app.routers.learning_video import DEMO_COURSE_ID
from app.study_service import lock_owner

router = APIRouter(prefix="/array-readiness", tags=["Arrays readiness"])
SKILL = "arrays.zero-based-indexing.v1"
LESSON = f"/?view=learning-hub&course={DEMO_COURSE_ID}&lesson=2&t=76"
PERSONAL = "personal"

QUESTIONS = {
    "diagnostic": {
        "prompt": "What value does the expression below return?",
        "code": "values = [8, 14, 21, 35]\nvalues[len(values) - 3]",
        "options": ["8", "14", "21", "There is no element at index 1"],
        "correct": 1,
        "feedback": [
            "You chose the first element. Its index is 0. Review Indexed Access & Safety.",
            "Correct. Length 4 minus 3 gives index 1, which selects the second element.",
            "You chose the third element. Count from index 0.",
            "Index 1 is valid. In this array the valid indices are 0 through 3.",
        ],
    },
    "practice": {
        "prompt": "Which index selects the last element in this array?",
        "code": "scores = [6, 17, 23, 41, 54]",
        "options": ["5", "3", "4", "54"],
        "correct": 2,
        "feedback": [
            "Length is 5, so the last valid index is 5 − 1.",
            "Index 3 selects the fourth element. The last element is at index 4.",
            "Correct. The last index is the array length minus one.",
            "54 is a value in the array. Its position is index 4.",
        ],
    },
    "followup": {
        "prompt": "What value does the expression below return?",
        "code": "levels = [13, 24, 37, 58, 72]\nlevels[len(levels) - 3]",
        "options": ["24", "58", "Index out of bounds", "37"],
        "correct": 3,
        "feedback": [
            "The expression computes index 2, which selects the third element, 37.",
            "58 is at index 3. The expression computes index 2.",
            "The expression computes index 2, a valid index for an array of length 5.",
            "Correct. Length 5 minus 3 gives index 2, which selects 37.",
        ],
    },
}


class Answer(BaseModel):
    step: Literal["diagnostic", "practice", "followup"]
    choice: int = Field(ge=0, le=3, strict=True)
    track: str = Field(min_length=1, max_length=100)


def current_attempt(db, user):
    org = institution(db, user) if user.organization_id else None
    if org and roster(db, org.id).filter(User.id == user.id).first():
        assigned = db.get(ArrayReadiness, (user.id, org.id))
        if assigned:
            return assigned, org.name
    return db.get(ArrayReadiness, (user.id, PERSONAL)), None


def view(row, institution_name):
    results = {}
    next_step = None
    for step, question in QUESTIONS.items():
        answer = getattr(row, f"{step}_answer") if row else None
        if answer is None:
            next_step = step
            break
        results[step] = {"correct": answer == question["correct"], "feedback": question["feedback"][answer]}
    question = QUESTIONS[next_step] if next_step else None
    return {
        "skill": SKILL, "title": "Zero-based array indexing", "lesson_url": LESSON,
        "track": row.scope if row else PERSONAL, "institution": institution_name,
        "step": next_step, "results": results,
        "question": {key: question[key] for key in ("prompt", "code", "options")} if question else None,
    }


@router.get("/me")
def my_readiness(user: User = Depends(require_student), db: Session = Depends(get_db)):
    return view(*current_attempt(db, user))


@router.post("/me/answers")
def submit(body: Answer, user: User = Depends(require_student), db: Session = Depends(get_db)):
    lock_owner(db, user)
    row, name = current_attempt(db, user)
    before = view(row, name)
    if body.track != before["track"]:
        raise HTTPException(409, "Your assignment changed. Refresh before submitting.")
    field = f"{body.step}_answer"
    previous = getattr(row, field) if row else None
    if previous is not None:
        if previous == body.choice:
            return before
        raise HTTPException(409, "This answer is already saved. Refresh to continue.")
    if body.step != before["step"]:
        raise HTTPException(409, "Complete the current step first.")
    if row is None:
        row = ArrayReadiness(student_id=user.id, scope=PERSONAL)
        db.add(row)
    setattr(row, field, body.choice)
    db.commit()
    return view(row, name)


@router.get("/institution")
def institution_readiness(
    search: str = Query(default="", max_length=80),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_institution_admin), db: Session = Depends(get_db),
):
    org = institution(db, user)
    if not org:
        raise HTTPException(403, "Your account is not linked to an active institution.")
    r = ArrayReadiness
    baseline = QUESTIONS["diagnostic"]["correct"]
    followup = QUESTIONS["followup"]["correct"]
    students = roster(db, org.id).outerjoin(r, and_(r.student_id == User.id, r.organization_id == org.id))
    summary = students.with_entities(
        func.count(r.student_id),
        func.count(r.diagnostic_answer),
        func.count(r.followup_answer),
        func.count(case((and_(r.diagnostic_answer != baseline, r.followup_answer == followup), 1))),
        func.count(case((and_(r.followup_answer.is_not(None), r.followup_answer != followup), 1))),
    ).one()
    if search.strip():
        term = search.strip().lower()
        students = students.filter(or_(func.lower(User.username).contains(term, autoescape=True),
                                       func.lower(StudentProfile.full_name).contains(term, autoescape=True)))
    rows = students.add_entity(r).order_by(
        case((and_(r.followup_answer.is_not(None), r.followup_answer != followup), 0),
             (and_(r.student_id.is_not(None), r.followup_answer.is_(None)), 1), else_=2),
        User.username, User.id,
    ).offset(offset).limit(51).all()
    return {
        "assigned": summary[0], "started": summary[1], "reassessed": summary[2],
        "improved": summary[3], "needs_help": summary[4], "has_more": len(rows) > 50,
        "students": [{
            "id": student.id, "name": profile.full_name or student.username,
            "assigned": attempt is not None,
            "diagnostic_correct": (attempt.diagnostic_answer == baseline
                                   if attempt and attempt.diagnostic_answer is not None else None),
            "followup_correct": (attempt.followup_answer == followup
                                 if attempt and attempt.followup_answer is not None else None),
        } for student, profile, attempt in rows[:50]],
    }


@router.put("/institution/assignments/{student_id}", status_code=204)
def assign(student_id: str, user: User = Depends(require_institution_admin), db: Session = Depends(get_db)):
    org = institution(db, user)
    if not org:
        raise HTTPException(403, "Your account is not linked to an active institution.")
    target = roster(db, org.id).filter(User.id == student_id).with_for_update(of=User).first()
    if not target:
        raise HTTPException(404, "Student not found in this institution.")
    if not db.get(ArrayReadiness, (student_id, org.id)):
        db.add(ArrayReadiness(student_id=student_id, scope=org.id, organization_id=org.id))
    db.commit()
