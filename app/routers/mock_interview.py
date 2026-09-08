from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_student
from app.models import ApprovalStatus, Job, MockInterview, StudentProfile, User
from app.routers.ai import PROMPT_GUARDRAIL, call_gemini, extract_json_from_response, get_gemini_client

router = APIRouter(prefix="/mock-interview", tags=["Mock Interview Coach"])


class MockInterviewStart(BaseModel):
    job_id: str
    focus: str = Field(default="balanced", pattern="^(balanced|technical|behavioral|hr)$")
    question_count: int = Field(default=5, ge=3, le=8)


class MockInterviewAnswer(BaseModel):
    question_id: int
    answer: str = Field(min_length=1, max_length=8000)


class MockInterviewEvaluation(BaseModel):
    interview_id: str
    answers: list[MockInterviewAnswer] = Field(min_length=1, max_length=8)


def _profile(current_user: User, db: Session) -> StudentProfile:
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Student profile not found")
    return profile


def _accessible_job(profile: StudentProfile, job_id: str, db: Session) -> Job:
    job = db.query(Job).filter(
        Job.id == job_id,
        Job.is_active.is_(True),
        Job.approval_status == ApprovalStatus.approved,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.visibility == "public":
        return job
    if profile.organization_id and job.target_organization_id == profile.organization_id:
        return job
    raise HTTPException(status_code=404, detail="Job not found")


def _issued_questions(row: MockInterview) -> list[dict[str, Any]]:
    try:
        questions = json.loads(row.questions_json or "[]")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=409, detail="Interview question set is unavailable") from exc
    if not isinstance(questions, list) or not questions:
        raise HTTPException(status_code=409, detail="Interview question set is unavailable")
    normalized = []
    for item in questions:
        if not isinstance(item, dict):
            raise HTTPException(status_code=409, detail="Interview question set is unavailable")
        try:
            question_id = int(item["question_id"])
            question = str(item["question"]).strip()
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail="Interview question set is unavailable") from exc
        if not question:
            raise HTTPException(status_code=409, detail="Interview question set is unavailable")
        normalized.append({
            "question_id": question_id,
            "question": question,
            "category": str(item.get("category", "interview")).strip().lower(),
        })
    return normalized


@router.get("/jobs")
def mock_interview_jobs(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    profile = _profile(current_user, db)
    jobs = db.query(Job).filter(Job.is_active.is_(True), Job.approval_status == ApprovalStatus.approved).all()
    visible = [
        job for job in jobs
        if job.visibility == "public" or (profile.organization_id and job.target_organization_id == profile.organization_id)
    ]
    return [
        {
            "id": job.id,
            "title": job.title,
            "company_name": job.recruiter.company_name if job.recruiter else None,
            "required_skills": job.required_skills,
            "experience_required": job.experience_required,
        }
        for job in visible
    ]


@router.post("/start")
def start_mock_interview(
    body: MockInterviewStart,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    profile = _profile(current_user, db)
    job = _accessible_job(profile, body.job_id, db)

    focus_instruction = {
        "balanced": "Mix technical, behavioral, situational, communication, and HR-style questions.",
        "technical": "Prioritize technical reasoning, debugging, architecture, and role-specific knowledge.",
        "behavioral": "Prioritize teamwork, ownership, conflict, ambiguity, leadership, and STAR-style behavioral questions.",
        "hr": "Prioritize HR screening, motivation, self-awareness, communication, professionalism, career goals, and situational judgment.",
    }[body.focus]

    prompt = f"""
{PROMPT_GUARDRAIL}

You are a senior campus interviewer conducting a realistic mock interview.
Generate exactly {body.question_count} interview questions for this candidate and role.
{focus_instruction}
Questions must be concise, non-discriminatory, job-relevant, and suitable for a college-placement interview.
Return ONLY a valid JSON object with this exact shape:
{{"questions":[{{"question_id":1,"question":"...","category":"technical|behavioral|hr|situational|communication"}}]}}

ROLE
Title: {job.title}
Description: {job.description[:6000]}
Required skills: {json.dumps(job.required_skills)}
Experience: {job.experience_required or 'Entry level / not specified'}

CANDIDATE CONTEXT
Degree: {profile.degree or 'Not provided'}
Branch: {profile.branch or 'Not provided'}
Skills: {json.dumps(profile.skills)}
Desired roles: {json.dumps(profile.desired_roles)}
"""
    raw = call_gemini(get_gemini_client(), prompt)
    data = extract_json_from_response(raw)
    questions = data.get("questions", []) if isinstance(data, dict) else []
    if not questions:
        raise HTTPException(status_code=502, detail="AI service returned no interview questions")
    normalized = []
    for index, item in enumerate(questions[: body.question_count], start=1):
        if not isinstance(item, dict) or not str(item.get("question", "")).strip():
            continue
        normalized.append({
            "question_id": index,
            "question": str(item["question"]).strip(),
            "category": str(item.get("category", "interview")).strip().lower(),
        })
    if len(normalized) < 3:
        raise HTTPException(status_code=502, detail="AI service returned an incomplete interview set")

    # Persist the server-issued question set before it reaches the browser. Evaluation
    # is later bound to this student-owned row so clients cannot substitute easier
    # questions and save an artificial coaching score.
    interview = MockInterview(
        student_id=profile.id,
        job_id=job.id,
        questions_json=json.dumps(normalized),
        answers_json="[]",
        evaluation_json=None,
        overall_score=None,
        overall_feedback=None,
    )
    db.add(interview)
    db.commit()
    db.refresh(interview)

    return {
        "interview_id": interview.id,
        "job_id": job.id,
        "job_title": job.title,
        "company_name": job.recruiter.company_name if job.recruiter else None,
        "focus": body.focus,
        "questions": normalized,
    }


@router.post("/evaluate")
def evaluate_mock_interview(
    body: MockInterviewEvaluation,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    profile = _profile(current_user, db)
    interview = db.query(MockInterview).filter(
        MockInterview.id == body.interview_id,
        MockInterview.student_id == profile.id,
    ).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Mock interview not found")
    if interview.overall_score is not None:
        raise HTTPException(status_code=409, detail="This mock interview has already been evaluated")

    job = db.query(Job).filter(Job.id == interview.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Interview role is no longer available")

    issued = _issued_questions(interview)
    expected_by_id = {item["question_id"]: item for item in issued}
    submitted_by_id = {item.question_id: item for item in body.answers}
    if len(submitted_by_id) != len(body.answers):
        raise HTTPException(status_code=422, detail="Duplicate interview answers are not allowed")
    if set(submitted_by_id) != set(expected_by_id):
        raise HTTPException(status_code=422, detail="Answers must match the server-issued interview question set")

    answers_payload = [
        {
            "question_id": item["question_id"],
            "question": item["question"],
            "answer": submitted_by_id[item["question_id"]].answer,
        }
        for item in issued
    ]

    prompt = f"""
{PROMPT_GUARDRAIL}

You are a rigorous campus interview coach. Evaluate the candidate's WRITTEN mock-interview answers for the role below.
Do not infer accent, spoken fluency, appearance, personality, protected traits, or any attribute not evidenced by the text.
Treat communication scores as a text-based proxy only.

Return ONLY valid JSON in this exact shape:
{{
  "overall_score": 0,
  "overall_feedback": "...",
  "dimensions": {{
    "relevance": 0,
    "clarity": 0,
    "structure": 0,
    "language_precision": 0,
    "role_knowledge": 0,
    "problem_solving": 0,
    "professionalism": 0
  }},
  "strengths": ["..."],
  "improvements": ["..."],
  "evaluations": [
    {{"question_id":1,"score":0,"feedback":"...","better_answer_outline":"..."}}
  ],
  "disclaimer": "Text-only coaching signal; not a measure of spoken communication, accent, personality, or employability."
}}

Scoring: every score is an integer from 0 to 100. Be evidence-based and specific. Reward concrete examples, structured reasoning, role relevance, concise language, and honest uncertainty. Do not reward verbosity.

ROLE
Title: {job.title}
Description: {job.description[:6000]}
Required skills: {json.dumps(job.required_skills)}

SERVER-ISSUED QUESTIONS AND ANSWERS
{json.dumps(answers_payload, indent=2)[:30000]}
"""
    raw = call_gemini(get_gemini_client(), prompt)
    data: dict[str, Any] = extract_json_from_response(raw)
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="AI service returned an invalid interview evaluation")

    def clamp(value: Any) -> int:
        try:
            return max(0, min(100, int(round(float(value)))))
        except (TypeError, ValueError):
            return 0

    dimensions = data.get("dimensions") if isinstance(data.get("dimensions"), dict) else {}
    dimension_keys = ["relevance", "clarity", "structure", "language_precision", "role_knowledge", "problem_solving", "professionalism"]
    normalized_dimensions = {key: clamp(dimensions.get(key)) for key in dimension_keys}
    evaluations = []
    ai_evaluations = data.get("evaluations") if isinstance(data.get("evaluations"), list) else []
    for item in issued:
        question_id = item["question_id"]
        source = next((candidate for candidate in ai_evaluations if isinstance(candidate, dict) and candidate.get("question_id") == question_id), {})
        evaluations.append({
            "question_id": question_id,
            "question": item["question"],
            "answer": submitted_by_id[question_id].answer,
            "score": clamp(source.get("score")),
            "feedback": str(source.get("feedback", "No detailed feedback returned."))[:4000],
            "better_answer_outline": str(source.get("better_answer_outline", ""))[:4000],
        })

    overall_score = clamp(data.get("overall_score"))
    result = {
        "overall_score": overall_score,
        "overall_feedback": str(data.get("overall_feedback", ""))[:6000],
        "dimensions": normalized_dimensions,
        "strengths": [str(x)[:1000] for x in (data.get("strengths") or [])[:8]],
        "improvements": [str(x)[:1000] for x in (data.get("improvements") or [])[:8]],
        "evaluations": evaluations,
        "disclaimer": "Text-only coaching signal; not a measure of spoken communication, accent, personality, or employability.",
    }

    interview.answers_json = json.dumps(answers_payload)
    interview.evaluation_json = json.dumps(result)
    interview.overall_score = overall_score
    interview.overall_feedback = result["overall_feedback"]
    db.commit()
    db.refresh(interview)
    return {"interview_id": interview.id, "job_title": job.title, **result}


@router.get("/history")
def mock_interview_history(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    profile = _profile(current_user, db)
    rows = db.query(MockInterview).filter(
        MockInterview.student_id == profile.id,
        MockInterview.overall_score.isnot(None),
    ).order_by(MockInterview.created_at.desc()).limit(50).all()
    result = []
    for row in rows:
        evaluation = {}
        try:
            evaluation = json.loads(row.evaluation_json or "{}")
        except json.JSONDecodeError:
            evaluation = {}
        result.append({
            "id": row.id,
            "job_id": row.job_id,
            "job_title": row.job.title if row.job else "Role",
            "company_name": row.job.recruiter.company_name if row.job and row.job.recruiter else None,
            "overall_score": row.overall_score,
            "dimensions": evaluation.get("dimensions", {}),
            "overall_feedback": row.overall_feedback,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })
    return result
