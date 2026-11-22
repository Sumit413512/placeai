"""Use a published lesson's three knowledge checks as a readiness sequence."""

import hashlib
import json

from app.models import Organization, OrganizationType, StudentProfile, User, UserRole

STEPS = ("diagnostic", "practice", "followup")


def questions(content):
    quiz = content.get("quiz", [])
    if len(quiz) < len(STEPS):
        return None
    selected = quiz[:len(STEPS)]
    if len({item["question"].strip().casefold() for item in selected}) != len(STEPS):
        return None
    return dict(zip(STEPS, selected))


def version(quiz):
    encoded = json.dumps(quiz, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def view(quiz, attempt, question_version):
    results = {}
    for step, item in quiz.items():
        answer = getattr(attempt, f"{step}_answer") if attempt else None
        if answer is None:
            return {
                "step": step, "track": question_version, "results": results,
                "question": {"prompt": item["question"], "options": item["options"]},
            }
        results[step] = {"correct": answer == item["answer"], "feedback": item["explanation"]}
    return {"step": None, "track": question_version, "results": results, "question": None}


def institution(db, user):
    return db.query(Organization).filter_by(
        id=user.organization_id, is_active=True, organization_type=OrganizationType.institution,
    ).first()


def roster(db, organization_id):
    return db.query(User, StudentProfile).join(StudentProfile, StudentProfile.user_id == User.id).filter(
        User.organization_id == organization_id, StudentProfile.organization_id == organization_id,
        User.role == UserRole.student, User.is_active.is_(True),
    )
