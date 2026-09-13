from __future__ import annotations

import json
import math
import re
from difflib import SequenceMatcher
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai_provider import call_ai_text
from app.ai_rate_limit import student_ai_guard
from app.database import get_db
from app.dependencies import require_student
from app.models import ApprovalStatus, Job, MockInterview, StudentProfile, User
from app.placement_access import job_is_visible_to_student
from app.routers.ai import PROMPT_GUARDRAIL, extract_json_from_response

router = APIRouter(prefix="/mock-interview", tags=["Mock Interview Coach"])


class MockInterviewStartV2(BaseModel):
    model_config = {"extra": "forbid"}

    job_id: str
    focus: str = Field(default="balanced", pattern="^(balanced|technical|behavioral|hr)$")
    question_count: int = Field(default=8, ge=5, le=15)
    difficulty: str = Field(default="mixed", pattern="^(easy|medium|hard|mixed)$")
    mode: str = Field(default="practice", pattern="^(practice|assessment)$")


class MockInterviewAnswerV2(BaseModel):
    model_config = {"extra": "forbid"}

    question_id: int
    answer: str = Field(min_length=1, max_length=8000)


class MockInterviewEvaluationV2(BaseModel):
    model_config = {"extra": "forbid"}

    interview_id: str
    answers: list[MockInterviewAnswerV2] = Field(min_length=1, max_length=15)


def _clamp_score(value: Any) -> int:
    try:
        score = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    if not math.isfinite(score):
        return 0
    return max(0, min(100, int(round(score))))


def _profile(user: User, db: Session) -> StudentProfile:
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Student profile not found")
    return profile


def _accessible_job(profile: StudentProfile, job_id: str, db: Session) -> Job:
    job = db.query(Job).filter(
        Job.id == job_id,
        Job.is_active.is_(True),
        Job.approval_status == ApprovalStatus.approved,
    ).first()
    if not job or not job_is_visible_to_student(profile, job, db):
        raise HTTPException(status_code=404, detail="Job not found")
    return job


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
            continue
        try:
            question_id = int(item["question_id"])
            question = str(item["question"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if question:
            normalized.append({
                "question_id": question_id,
                "question": question,
                "category": str(item.get("category", "interview")).strip().lower(),
                "difficulty": str(item.get("difficulty", "mixed")).strip().lower(),
            })
    if not normalized:
        raise HTTPException(status_code=409, detail="Interview question set is unavailable")
    return normalized


def _question_norm(value: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", value.casefold()).strip()


def _too_similar(question: str, existing: list[str]) -> bool:
    candidate = _question_norm(question)
    if not candidate:
        return True
    for prior in existing:
        normalized = _question_norm(prior)
        if not normalized:
            continue
        if candidate == normalized or candidate in normalized or normalized in candidate:
            return True
        if SequenceMatcher(None, candidate, normalized).ratio() >= 0.82:
            return True
    return False


def _previous_questions(profile: StudentProfile, job: Job, db: Session) -> list[str]:
    rows = db.query(MockInterview).filter(
        MockInterview.student_id == profile.id,
        MockInterview.job_id == job.id,
    ).order_by(MockInterview.created_at.desc()).limit(20).all()
    questions: list[str] = []
    for row in rows:
        try:
            payload = json.loads(row.questions_json or "[]")
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, list):
            continue
        for item in payload:
            if isinstance(item, dict) and str(item.get("question", "")).strip():
                questions.append(str(item["question"]).strip())
                if len(questions) >= 120:
                    return questions
    return questions


def _candidate_context(profile: StudentProfile) -> dict[str, Any]:
    resume_data = profile.resume.ai_parsed_data if profile.resume and profile.resume.ai_parsed_data else {}
    return {
        "degree": profile.degree,
        "branch": profile.branch,
        "skills": profile.skills or [],
        "desired_roles": profile.desired_roles or [],
        "resume_summary": resume_data.get("summary"),
        "experience": resume_data.get("experience", [])[:8],
        "projects_or_resume_skills": resume_data.get("skills", [])[:80],
    }


def _question_prompt(
    *,
    profile: StudentProfile,
    job: Job,
    focus: str,
    difficulty: str,
    count: int,
    avoid: list[str],
) -> str:
    focus_instruction = {
        "balanced": "Use a balanced mix of role-specific technical, problem-solving, behavioral, situational and HR questions.",
        "technical": "Prioritize role-specific technical reasoning, debugging, architecture, practical implementation and trade-offs.",
        "behavioral": "Prioritize evidence-based teamwork, ownership, conflict, ambiguity, leadership and STAR-style questions.",
        "hr": "Prioritize motivation, role fit, self-awareness, communication, professionalism, career goals and situational judgment.",
    }[focus]
    avoid_text = json.dumps(avoid[-120:], ensure_ascii=False) if avoid else "[]"
    return f"""
{PROMPT_GUARDRAIL}

You are a senior interviewer preparing a realistic campus interview for the exact role below.
Generate exactly {count} NEW questions. {focus_instruction}
Difficulty: {difficulty}. If difficulty is mixed, deliberately progress from foundational to intermediate and then challenging.
At least half of the questions must directly test the role description, required skills or candidate's relevant experience.
For technical questions, prefer applied reasoning, debugging, design, code/SQL/API/cloud scenarios or trade-offs over trivia.
Questions must be concise, non-discriminatory and answerable in a written practice session.
Do NOT repeat, lightly reword, paraphrase or reuse the concept framing of any prior question in AVOID QUESTIONS.
Do not ask multiple questions that are substantially the same within this new set.

Return ONLY valid JSON:
{{"questions":[{{"question":"...","category":"technical|behavioral|hr|situational|communication","difficulty":"easy|medium|hard"}}]}}

ROLE
Title: {job.title}
Description: {job.description[:7000]}
Required skills: {json.dumps(job.required_skills, ensure_ascii=False)}
Preferred roles: {json.dumps(job.preferred_roles, ensure_ascii=False)}
Experience required: {job.experience_required or 'Entry level / not specified'}

CANDIDATE CONTEXT
{json.dumps(_candidate_context(profile), ensure_ascii=False, indent=2)[:12_000]}

AVOID QUESTIONS FROM PREVIOUS PRACTICE
{avoid_text[:18_000]}
"""


def _generate_unique_questions(
    *,
    profile: StudentProfile,
    job: Job,
    focus: str,
    difficulty: str,
    count: int,
    previous: list[str],
) -> list[dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    avoid = list(previous)
    for round_index in range(2):
        needed = count - len(accepted)
        if needed <= 0:
            break
        prompt = _question_prompt(
            profile=profile,
            job=job,
            focus=focus,
            difficulty=difficulty,
            count=needed + (2 if round_index == 0 and needed >= 5 else 0),
            avoid=avoid,
        )
        raw = call_ai_text(prompt, reasoning_effort="low", max_output_tokens=3200)
        data = extract_json_from_response(raw)
        source = data.get("questions", []) if isinstance(data, dict) else []
        if not isinstance(source, list):
            source = []
        for item in source:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question", "")).strip()
            if not question or _too_similar(question, [*avoid, *(x["question"] for x in accepted)]):
                continue
            category = str(item.get("category", "interview")).strip().lower()
            q_difficulty = str(item.get("difficulty", difficulty if difficulty != "mixed" else "medium")).strip().lower()
            if category not in {"technical", "behavioral", "hr", "situational", "communication"}:
                category = "interview"
            if q_difficulty not in {"easy", "medium", "hard"}:
                q_difficulty = "medium"
            accepted.append({"question": question[:2000], "category": category, "difficulty": q_difficulty})
            if len(accepted) >= count:
                break
        avoid.extend(item["question"] for item in accepted)
    if len(accepted) < max(5, count - 1):
        raise HTTPException(status_code=502, detail="AI service could not generate a sufficiently unique interview set. Please try again.")
    return [
        {"question_id": index, **item}
        for index, item in enumerate(accepted[:count], start=1)
    ]


@router.post("/start", dependencies=[Depends(student_ai_guard)])
def start_mock_interview_v2(
    body: MockInterviewStartV2,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    profile = _profile(current_user, db)
    job = _accessible_job(profile, body.job_id, db)
    previous = _previous_questions(profile, job, db)
    questions = _generate_unique_questions(
        profile=profile,
        job=job,
        focus=body.focus,
        difficulty=body.difficulty,
        count=body.question_count,
        previous=previous,
    )
    interview = MockInterview(
        student_id=profile.id,
        job_id=job.id,
        questions_json=json.dumps(questions),
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
        "difficulty": body.difficulty,
        "mode": body.mode,
        "questions": questions,
        "previous_questions_avoided": len(previous),
    }


@router.post("/evaluate", dependencies=[Depends(student_ai_guard)])
def evaluate_mock_interview_v2(
    body: MockInterviewEvaluationV2,
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
            "category": item.get("category"),
            "difficulty": item.get("difficulty"),
            "answer": submitted_by_id[item["question_id"]].answer,
        }
        for item in issued
    ]
    prompt = f"""
{PROMPT_GUARDRAIL}

You are a rigorous role-specific campus interview coach. Evaluate every written answer below against the exact role.
Do not infer accent, spoken fluency, appearance, personality, protected traits or anything not evidenced by the text.
Be diagnostic, practical and specific. For every question explain what was good, what was missing and provide a strong
example answer/solution grounded in the role. The example answer is a learning reference, not something to memorize.

Return ONLY valid JSON with this exact top-level structure:
{{
  "overall_score": 0,
  "overall_feedback": "...",
  "dimensions": {{"relevance":0,"clarity":0,"structure":0,"language_precision":0,"role_knowledge":0,"problem_solving":0,"professionalism":0}},
  "strengths": ["..."],
  "improvements": ["..."],
  "weak_topics": ["..."],
  "next_practice_plan": ["..."],
  "evaluations": [
    {{
      "question_id": 1,
      "score": 0,
      "feedback": "...",
      "missing_points": ["..."],
      "key_points": ["..."],
      "better_answer_outline": "...",
      "ideal_answer": "..."
    }}
  ]
}}

All scores are integers 0-100. Reward correctness, concrete examples, structured reasoning, role relevance and honest
uncertainty. Do not reward verbosity. Technical solutions must be technically sound and mention trade-offs where relevant.

ROLE
Title: {job.title}
Description: {job.description[:7000]}
Required skills: {json.dumps(job.required_skills, ensure_ascii=False)}

CANDIDATE CONTEXT
{json.dumps(_candidate_context(profile), ensure_ascii=False, indent=2)[:12_000]}

QUESTIONS AND ANSWERS
{json.dumps(answers_payload, ensure_ascii=False, indent=2)[:42_000]}
"""
    raw = call_ai_text(prompt, reasoning_effort="medium", max_output_tokens=7600)
    data = extract_json_from_response(raw)
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="AI service returned an invalid interview evaluation")

    dimensions_raw = data.get("dimensions") if isinstance(data.get("dimensions"), dict) else {}
    dimension_keys = ["relevance", "clarity", "structure", "language_precision", "role_knowledge", "problem_solving", "professionalism"]
    dimensions = {key: _clamp_score(dimensions_raw.get(key)) for key in dimension_keys}
    ai_evaluations = data.get("evaluations") if isinstance(data.get("evaluations"), list) else []
    evaluations: list[dict[str, Any]] = []
    for item in issued:
        qid = item["question_id"]
        source = next(
            (candidate for candidate in ai_evaluations if isinstance(candidate, dict) and str(candidate.get("question_id")) == str(qid)),
            {},
        )
        evaluations.append({
            "question_id": qid,
            "question": item["question"],
            "answer": submitted_by_id[qid].answer,
            "score": _clamp_score(source.get("score")),
            "feedback": str(source.get("feedback", "No detailed feedback returned."))[:5000],
            "missing_points": [str(x)[:1000] for x in (source.get("missing_points") or [])[:10]],
            "key_points": [str(x)[:1000] for x in (source.get("key_points") or [])[:10]],
            "better_answer_outline": str(source.get("better_answer_outline", ""))[:5000],
            "ideal_answer": str(source.get("ideal_answer", ""))[:7000],
        })

    overall_score = _clamp_score(data.get("overall_score"))
    result = {
        "overall_score": overall_score,
        "overall_feedback": str(data.get("overall_feedback", ""))[:7000],
        "dimensions": dimensions,
        "strengths": [str(x)[:1200] for x in (data.get("strengths") or [])[:10]],
        "improvements": [str(x)[:1200] for x in (data.get("improvements") or [])[:10]],
        "weak_topics": [str(x)[:1000] for x in (data.get("weak_topics") or [])[:10]],
        "next_practice_plan": [str(x)[:1200] for x in (data.get("next_practice_plan") or [])[:10]],
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
