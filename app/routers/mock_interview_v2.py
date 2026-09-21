from __future__ import annotations

import json
import logging
import math
import re
import time
from difflib import SequenceMatcher
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.ai_provider import call_ai_text, current_ai_model, current_ai_provider
from app.ai_rate_limit import student_ai_guard
from app.database import get_db
from app.dependencies import require_student
from app.models import ApprovalStatus, Job, MockInterview, StudentProfile, User
from app.placement_access import job_is_visible_to_student
from app.routers.ai import PROMPT_GUARDRAIL, extract_json_from_response
from app.student_entitlements import require_student_premium_access

router = APIRouter(prefix="/mock-interview", tags=["Mock Interview Coach"])
LOGGER = logging.getLogger("placeai.mock_interview")

FULL_MOCK_QUESTION_COUNT = 50
ASSESSMENT_BLUEPRINT = (
    ("quantitative", "Quantitative Aptitude", 8),
    ("logical", "Logical & Analytical Reasoning", 8),
    ("communication", "Verbal & Communication", 6),
    ("technical", "Technical Fundamentals", 8),
    ("programming", "Programming & Debugging", 6),
    ("coding", "Coding Challenges", 2),
    ("resume", "Resume & Project Defence", 4),
    ("behavioral", "Behavioural & HR", 4),
    ("role", "Role / JD / Company", 2),
    ("situational", "Situational & Decision", 2),
)


class MockInterviewStartV2(BaseModel):
    model_config = {"extra": "forbid"}

    job_id: str
    focus: str = Field(default="balanced", pattern="^(balanced|technical|behavioral|hr)$")
    question_count: int = Field(default=8, ge=3, le=FULL_MOCK_QUESTION_COUNT)
    difficulty: str = Field(default="mixed", pattern="^(easy|medium|hard|mixed)$")
    mode: str = Field(default="practice", pattern="^(practice|assessment)$")

    @model_validator(mode="after")
    def validate_standardized_assessment(self):
        if self.mode == "assessment":
            if self.question_count != FULL_MOCK_QUESTION_COUNT:
                raise ValueError("Full assessment mode requires exactly 50 primary items")
            if self.focus != "balanced" or self.difficulty != "mixed":
                raise ValueError("Full assessment mode uses the server-standardized balanced/mixed blueprint")
        elif self.question_count > 15:
            raise ValueError("Legacy practice rounds support 3-15 questions")
        return self


class MockInterviewAnswerV2(BaseModel):
    model_config = {"extra": "forbid"}

    question_id: int
    answer: str = Field(min_length=1, max_length=8000)


class MockInterviewEvaluationV2(BaseModel):
    model_config = {"extra": "forbid"}

    interview_id: str
    answers: list[MockInterviewAnswerV2] = Field(min_length=1, max_length=FULL_MOCK_QUESTION_COUNT)


def _call_interview_ai(prompt: str, *, max_output_tokens: int, fast: bool = False) -> str:
    """Call the canonical provider chain with an explicit interactive latency budget.

    Question generation uses the lower-latency GPT-5.6 Luna model. Evaluation keeps the
    configured production model, but disables extra reasoning because the rubric and
    evidence are already supplied in the prompt.
    """
    return call_ai_text(
        prompt,
        reasoning_effort="none",
        max_output_tokens=max_output_tokens,
        model_override="gpt-5.6-luna" if fast else None,
        timeout_seconds=10 if fast else 24,
        retry_count_per_provider=0,
    )


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
                "section": str(item.get("section", item.get("category", "interview"))).strip().lower(),
                "category": str(item.get("category", "interview")).strip().lower(),
                "difficulty": str(item.get("difficulty", "mixed")).strip().lower(),
                "answer_type": str(item.get("answer_type", "text")).strip().lower(),
                "options": [str(x)[:1000] for x in (item.get("options") or [])[:4]],
                "correct_answer": str(item.get("correct_answer", ""))[:1000],
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
{("Generate exactly 50 NEW primary assessment items for a standardized full campus-placement mock. Use this exact section blueprint and do not omit or merge sections: quantitative 8; logical 8; communication 6; technical 8; programming 6; coding 2; resume 4; behavioral 4; role 2; situational 2. Difficulty must progress from foundational to intermediate and then challenging within each section. At least half of technical/programming/coding/resume/role items must directly test the role description, required skills or candidate's relevant experience. For quantitative, logical and communication items, prefer objective multiple-choice questions with exactly four plausible options. For technical and programming, mix objective and applied questions. Coding, resume, behavioral, role and situational items should normally be applied-response questions." if count == FULL_MOCK_QUESTION_COUNT else f"Generate exactly {count} NEW role-specific practice interview questions. {focus_instruction} Difficulty: {difficulty}. Prefer applied technical reasoning, debugging, design, behavioral evidence, situational judgment and role fit over trivia.")}
Questions must be concise, non-discriminatory and suitable for campus placement preparation.
Use ONLY facts present in ROLE and CANDIDATE CONTEXT. Do not invent company processes, technologies, projects,
metrics, responsibilities, achievements or candidate experience. If a fact is not provided, ask a generic
role-grounded question instead of assuming it.
Do NOT repeat, lightly reword, paraphrase or reuse the concept framing of any prior question in AVOID QUESTIONS.
Do not ask multiple questions that are substantially the same within this new set.

Return ONLY valid JSON.
For a 50-item full assessment use:
{{"questions":[{{"question":"...","section":"quantitative|logical|communication|technical|programming|coding|resume|behavioral|role|situational","category":"...","difficulty":"easy|medium|hard","answer_type":"mcq|text","options":["A","B","C","D"],"correct_answer":"exact option text or empty for text"}}]}}
For legacy practice rounds use:
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


def _difficulty_for(index: int, total: int, requested: str) -> str:
    if requested != "mixed":
        return requested
    ratio = index / max(total, 1)
    if ratio <= 0.34:
        return "easy"
    if ratio <= 0.68:
        return "medium"
    return "hard"


def _fallback_questions(
    *,
    profile: StudentProfile,
    job: Job,
    focus: str,
    difficulty: str,
    count: int,
    previous: list[str],
    already: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Fill missing blueprint sections with deterministic, role-grounded items."""

    if count < FULL_MOCK_QUESTION_COUNT:
        existing = [*previous, *(item["question"] for item in (already or []))]
        skills = [str(x).strip() for x in (job.required_skills or []) if str(x).strip()]
        if not skills:
            skills = [str(x).strip() for x in (profile.skills or []) if str(x).strip()]
        skills = skills[:10] or ["the core skills required for this role"]
        pool: list[tuple[str, str]] = []
        for skill in skills:
            pool.extend([
                (f"For the {job.title} role, describe a practical task where you would use {skill}. How would you verify that your solution works correctly?", "technical"),
                (f"Suppose a task involving {skill} is failing in a project relevant to {job.title}. Walk through how you would diagnose the problem, choose a fix, and check for regressions.", "technical"),
            ])
        pool.extend([
            (f"You are given an unfamiliar task in the {job.title} role with incomplete requirements. How would you clarify the problem and plan your first steps?", "situational"),
            ("Tell me about a time you had to learn a technical concept quickly. What did you do and what was the outcome?", "behavioral"),
            (f"Why are you interested in the {job.title} opportunity, based only on the responsibilities and skills you know about it?", "hr"),
        ])
        chosen: list[dict[str, Any]] = []
        suffix = 1
        while len(chosen) < count:
            if pool:
                question, category = pool[(suffix - 1) % len(pool)]
            else:
                skill = skills[(suffix - 1) % len(skills)]
                question = f"Practice scenario {suffix}: for a {job.title} task involving {skill}, explain your approach, risk and validation."
                category = "technical"
            suffix += 1
            if _too_similar(question, [*existing, *(x["question"] for x in chosen)]):
                continue
            chosen.append({
                "question": question[:2000],
                "section": category if category != "hr" else "behavioral",
                "category": category,
                "difficulty": _difficulty_for(len(chosen) + 1, count, difficulty),
                "answer_type": "text",
                "options": [],
                "correct_answer": "",
            })
        return chosen[:count]

    existing_items = already or []
    existing_text = [*previous, *(item["question"] for item in existing_items)]
    targets = {key: target for key, _, target in ASSESSMENT_BLUEPRINT}
    section_counts = {key: 0 for key in targets}
    for item in existing_items:
        section = str(item.get("section", "")).strip().lower()
        if section in section_counts:
            section_counts[section] += 1

    skills = [str(x).strip() for x in (job.required_skills or []) if str(x).strip()]
    if not skills:
        skills = [str(x).strip() for x in (profile.skills or []) if str(x).strip()]
    skills = skills[:12] or ["the core skills required for this role"]

    objective = {
        "quantitative": [
            ("A placement test has 80 questions and a candidate attempts 68. What percentage was attempted?", ["75%", "80%", "85%", "90%"], "85%"),
            ("A stipend rises from 20,000 to 23,000. What is the percentage increase?", ["10%", "12%", "15%", "18%"], "15%"),
            ("Five students work for 12 hours at the same rate. How many student-hours of work is that?", ["17", "48", "60", "72"], "60"),
            ("The ratio of technical to HR items is 3:2. If there are 30 technical items, how many HR items are there?", ["12", "18", "20", "24"], "20"),
            ("A score rises from 64 to 80. What is the absolute increase?", ["12", "14", "16", "20"], "16"),
            ("Three of eight candidates clear a round. What percentage is that?", ["27.5%", "32.5%", "37.5%", "42.5%"], "37.5%"),
            ("What is the average of 72, 78, 84 and 86?", ["78", "79", "80", "81"], "80"),
            ("A team completes 3/5 of a task. What percentage remains?", ["20%", "30%", "40%", "60%"], "40%"),
        ],
        "logical": [
            ("All backend engineers in a team know APIs. Which statement must be true?", ["All API engineers are backend engineers", "All backend engineers know APIs", "All backend engineers know SQL", "No API engineer knows SQL"], "All backend engineers know APIs"),
            ("Complete the sequence: 3, 6, 12, 24, ?", ["30", "36", "42", "48"], "48"),
            ("If A is before B and B is before C, which must be true?", ["C is before A", "A is before C", "B is after C", "A and C are simultaneous"], "A is before C"),
            ("A candidate must choose SQL and exactly one of Python or Java. Which combination is valid?", ["Python + Java", "SQL only", "Python + SQL", "Java only"], "Python + SQL"),
            ("Find the odd one out.", ["API", "Database", "Operating System", "Resume"], "Resume"),
            ("If every passed coding test implies technical eligibility and Priya passed coding, what follows?", ["Priya is technically eligible", "Priya is hired", "Priya passed HR", "Nothing follows"], "Priya is technically eligible"),
            ("Arrange from smallest to largest.", ["0.25, 40%, 1/2, 0.75", "40%, 0.25, 1/2, 0.75", "0.25, 1/2, 40%, 0.75", "1/2, 0.25, 40%, 0.75"], "0.25, 40%, 1/2, 0.75"),
            ("If X is greater than Y and Y equals Z, which is true?", ["X < Z", "X = Z", "X > Z", "Cannot compare"], "X > Z"),
        ],
        "communication": [
            ("Choose the most professional sentence.", ["Send me the file ASAP.", "Could you please share the file by 3 PM so I can complete the review?", "Need file now.", "You forgot the file."], "Could you please share the file by 3 PM so I can complete the review?"),
            ("Which response best demonstrates active listening?", ["Changing the topic", "Repeating words without context", "Summarising the concern before responding", "Speaking for longer"], "Summarising the concern before responding"),
            ("Which opening is usually strongest for a concise interview answer?", ["A direct response to the question", "A long personal history", "An unrelated example", "An apology"], "A direct response to the question"),
            ("Which phrase communicates uncertainty most clearly?", ["I definitely know, maybe.", "Based on the information available, my current assumption is…", "Whatever works.", "I guess so."], "Based on the information available, my current assumption is…"),
            ("Which framework is commonly useful for behavioural answers?", ["STAR", "FIFO", "HTTP", "CRUD"], "STAR"),
            ("Which response is clearest when you need clarification?", ["I do not know.", "Could you clarify whether you want the technical approach or the business impact first?", "Anything is fine.", "Skip it."], "Could you clarify whether you want the technical approach or the business impact first?"),
        ],
    }

    applied_templates = {
        "technical": [
            "For the {role} role, explain a practical use of {skill} and how you would validate the result.",
            "A production task involving {skill} is failing. Describe how you would isolate the cause and verify a safe fix.",
            "Explain one important trade-off you would consider when using {skill} in a real {role} task.",
            "How would you test a feature involving {skill} before release?",
            "Describe a failure mode related to {skill} that a {role} should anticipate.",
            "How would you explain a design decision involving {skill} to a technical reviewer?",
            "What evidence would you collect before changing an implementation that depends on {skill}?",
            "How would you improve the reliability or maintainability of a solution that uses {skill}?",
        ],
        "programming": [
            "Code using {skill} works for normal inputs but fails on edge cases. Describe a disciplined debugging sequence.",
            "How would you review code involving {skill} for correctness, readability and regression risk?",
            "Explain how you would design tests for a function or module using {skill}.",
            "A change involving {skill} makes the system slower. How would you measure and investigate the regression?",
            "How would you handle invalid or unexpected input in an implementation involving {skill}?",
            "Describe how you would refactor a working but difficult-to-maintain implementation involving {skill}.",
        ],
        "coding": [
            "Design an algorithm for a role-relevant data-processing task. Explain the data structure, time complexity, edge cases and tests.",
            "Given a large collection of records with duplicates, describe an efficient approach to identify and remove duplicates while preserving required ordering.",
        ],
        "resume": [
            "Choose one project or skill from your resume that is relevant to {role}. Explain your exact contribution and the evidence of the outcome.",
            "Describe the hardest technical decision in one project on your resume and why you chose that approach.",
            "Pick one resume claim you would expect an interviewer to challenge. Defend it with specific evidence you can personally explain.",
            "Describe one project limitation or mistake from your experience and what you would change now.",
        ],
        "behavioral": [
            "Describe a time you received difficult feedback. What action did you take and what changed afterward?",
            "Give a specific example of a disagreement in a team. How did you help move the work forward?",
            "Describe a time you had to learn something quickly to complete a task. What was your method and result?",
            "Tell me about a mistake you made in a project or assignment. How did you detect, correct and prevent it?",
        ],
        "role": [
            "Based only on the known requirements of the {role} opportunity, which capability would you prioritise in your first 30 days and why?",
            "Which stated requirement of the {role} opportunity best matches your current background, and what evidence supports that match?",
        ],
        "situational": [
            "A deadline is close and you discover a defect that could affect users. What would you do next and how would you communicate the risk?",
            "You receive an ambiguous task in the {role} role. How would you clarify requirements, plan the work and verify completion?",
        ],
    }

    chosen = []
    for section, _, target in ASSESSMENT_BLUEPRINT:
        missing = max(0, target - section_counts.get(section, 0))
        if section in objective:
            for question, options, correct in objective[section][:missing]:
                chosen.append({
                    "question": question,
                    "section": section,
                    "category": section,
                    "difficulty": _difficulty_for(len(chosen) + 1, FULL_MOCK_QUESTION_COUNT, difficulty),
                    "answer_type": "mcq",
                    "options": options,
                    "correct_answer": correct,
                })
            continue

        templates = applied_templates.get(section, [])
        for index in range(missing):
            template = templates[index % len(templates)]
            skill = skills[index % len(skills)]
            question = template.format(role=job.title, skill=skill)
            if _too_similar(question, [*existing_text, *(item["question"] for item in chosen)]):
                question = f"{question} Focus scenario {index + 1}."
            chosen.append({
                "question": question[:2000],
                "section": section,
                "category": section,
                "difficulty": _difficulty_for(index + 1, max(missing, 1), difficulty),
                "answer_type": "text",
                "options": [],
                "correct_answer": "",
            })

    return chosen[:count]


def _generate_unique_questions(
    *,
    profile: StudentProfile,
    job: Job,
    focus: str,
    difficulty: str,
    count: int,
    previous: list[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Generate one fast AI batch, then fill any gap with a grounded local safety net."""
    started = time.perf_counter()
    accepted: list[dict[str, Any]] = []
    generation_mode = "resilient_fallback"
    provider = "local"
    model = "role-grounded-v1"

    try:
        prompt = _question_prompt(
            profile=profile,
            job=job,
            focus=focus,
            difficulty=difficulty,
            count=count + (2 if count >= 5 else 1),
            avoid=previous,
        )
        raw = _call_interview_ai(prompt, max_output_tokens=7600 if count == FULL_MOCK_QUESTION_COUNT else 1800, fast=True)
        data = extract_json_from_response(raw)
        source = data.get("questions", []) if isinstance(data, dict) else []
        target_map = {key: target for key, _, target in ASSESSMENT_BLUEPRINT}
        section_counts = {key: 0 for key in target_map}
        if isinstance(source, list):
            for item in source:
                if not isinstance(item, dict):
                    continue
                question = str(item.get("question", "")).strip()
                if not question or _too_similar(question, [*previous, *(x["question"] for x in accepted)]):
                    continue
                category = str(item.get("category", "interview")).strip().lower()
                if count == FULL_MOCK_QUESTION_COUNT:
                    section = str(item.get("section", item.get("category", "technical"))).strip().lower()
                    allowed_sections = {key for key, _, _ in ASSESSMENT_BLUEPRINT}
                    if section not in allowed_sections or section_counts[section] >= target_map[section]:
                        continue
                    category = str(item.get("category", section)).strip().lower() or section
                else:
                    section = category if category in {"technical", "behavioral", "situational", "communication"} else "technical"
                    if category not in {"technical", "behavioral", "hr", "situational", "communication"}:
                        category = "interview"
                q_difficulty = str(item.get("difficulty", difficulty if difficulty != "mixed" else "medium")).strip().lower()
                if q_difficulty not in {"easy", "medium", "hard"}:
                    q_difficulty = _difficulty_for(len(accepted) + 1, count, difficulty)
                options = [str(x)[:1000] for x in (item.get("options") or [])[:4]] if count == FULL_MOCK_QUESTION_COUNT else []
                answer_type = "mcq" if count == FULL_MOCK_QUESTION_COUNT and len(options) == 4 else "text"
                correct_answer = str(item.get("correct_answer", ""))[:1000] if answer_type == "mcq" else ""
                accepted.append({
                    "question": question[:2000],
                    "section": section,
                    "category": category,
                    "difficulty": q_difficulty,
                    "answer_type": answer_type,
                    "options": options,
                    "correct_answer": correct_answer,
                })
                if count == FULL_MOCK_QUESTION_COUNT:
                    section_counts[section] += 1
                if len(accepted) >= count:
                    break
        if accepted:
            generation_mode = "ai"
            provider = current_ai_provider()
            model = current_ai_model()
    except Exception as exc:
        LOGGER.warning("Mock interview live AI generation failed; using grounded fallback error_type=%s", type(exc).__name__)

    if len(accepted) < count:
        needed = count - len(accepted)
        accepted.extend(_fallback_questions(
            profile=profile,
            job=job,
            focus=focus,
            difficulty=difficulty,
            count=needed,
            previous=previous,
            already=accepted,
        ))
        generation_mode = "ai_plus_fallback" if provider != "local" else "resilient_fallback"

    questions = [
        {"question_id": index, **item}
        for index, item in enumerate(accepted[:count], start=1)
    ]
    metadata = {
        "generation_mode": generation_mode,
        "provider": provider,
        "model": model,
        "generation_ms": int((time.perf_counter() - started) * 1000),
        "grounding": "approved opportunity + authorized student profile",
    }
    LOGGER.info(
        "Mock interview generated mode=%s provider=%s model=%s questions=%s latency_ms=%s",
        generation_mode,
        provider,
        model,
        len(questions),
        metadata["generation_ms"],
    )
    return questions, metadata


@router.post("/start", dependencies=[Depends(student_ai_guard)])
def start_mock_interview_v2(
    body: MockInterviewStartV2,
    current_user: User = Depends(require_student_premium_access),
    db: Session = Depends(get_db),
):
    profile = _profile(current_user, db)
    job = _accessible_job(profile, body.job_id, db)
    previous = _previous_questions(profile, job, db)
    questions, generation = _generate_unique_questions(
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
    client_questions = [
        {key: value for key, value in item.items() if key != "correct_answer"}
        for item in questions
    ]
    return {
        "interview_id": interview.id,
        "job_id": job.id,
        "job_title": job.title,
        "company_name": job.recruiter.company_name if job.recruiter else None,
        "focus": body.focus,
        "difficulty": body.difficulty,
        "mode": body.mode,
        "question_count": body.question_count,
        "assessment_blueprint": (
            [{"key": key, "label": label, "count": count} for key, label, count in ASSESSMENT_BLUEPRINT]
            if body.mode == "assessment" else []
        ),
        "questions": client_questions,
        "previous_questions_avoided": len(previous),
        **generation,
    }



_BASELINE_STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "for", "on", "with", "how",
    "what", "why", "would", "you", "your", "this", "that", "is", "are", "be", "as",
    "from", "role", "task", "work", "tell", "describe", "explain", "about",
}


def _evidence_terms(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9+#.-]{2,}", (value or "").casefold())
        if token not in _BASELINE_STOPWORDS
    }


def _resilient_baseline_evaluation(
    *,
    issued: list[dict[str, Any]],
    submitted_by_id: dict[int, MockInterviewAnswerV2],
    job: Job,
) -> dict[str, Any]:
    """Return a conservative continuity score when the live evaluator is unavailable.

    This deliberately does NOT claim technical correctness. Scores only reflect observable
    answer completeness, structure, and lexical relevance to the issued question/role.
    """
    role_terms = _evidence_terms(
        " ".join([
            job.title or "",
            job.description or "",
            " ".join(str(x) for x in (job.required_skills or [])),
        ])
    )
    evaluations: list[dict[str, Any]] = []
    all_scores: list[int] = []
    relevance_scores: list[int] = []
    structure_scores: list[int] = []

    for item in issued:
        qid = item["question_id"]
        answer = submitted_by_id[qid].answer.strip()
        words = re.findall(r"\b[\w+#.-]+\b", answer)
        answer_terms = _evidence_terms(answer)
        question_terms = _evidence_terms(item["question"])
        role_hits = len(answer_terms & role_terms)
        question_hits = len(answer_terms & question_terms)
        sentence_count = len([part for part in re.split(r"[.!?]+", answer) if part.strip()])

        completeness = min(28, int(len(words) / 3.5))
        relevance = min(22, role_hits * 5 + question_hits * 3)
        structure = min(14, max(0, sentence_count - 1) * 4)
        baseline = min(72, 24 + completeness + relevance + structure)
        if len(words) < 12:
            baseline = min(baseline, 42)

        all_scores.append(baseline)
        relevance_scores.append(min(72, 32 + relevance + min(18, completeness)))
        structure_scores.append(min(72, 30 + structure + min(20, completeness)))

        missing_points: list[str] = []
        if len(words) < 40:
            missing_points.append("Add a more complete explanation with concrete steps or an example.")
        if role_hits == 0:
            missing_points.append("Connect the answer explicitly to the role or one of its stated required skills.")
        if question_hits == 0:
            missing_points.append("Address the specific wording of the question more directly.")
        missing_points.append("Technical correctness was not scored because the live AI evaluator was temporarily unavailable.")

        feedback = (
            "Continuity-mode feedback: the answer was checked for completeness, structure and relevance to the "
            "issued question and approved role context. Technical correctness requires live AI evaluation."
        )
        evaluations.append({
            "question_id": qid,
            "question": item["question"],
            "answer": answer,
            "score": baseline,
            "feedback": feedback,
            "missing_points": missing_points,
            "key_points": [
                "Answer the exact question first.",
                "Use a concrete example or step-by-step approach.",
                "Tie claims to the role requirements that are actually provided.",
            ],
            "better_answer_outline": "Direct answer → concrete example or method → validation/result → role relevance.",
            "ideal_answer": "",
        })

    overall = round(sum(all_scores) / len(all_scores)) if all_scores else 0
    relevance = round(sum(relevance_scores) / len(relevance_scores)) if relevance_scores else 0
    structure = round(sum(structure_scores) / len(structure_scores)) if structure_scores else 0
    return {
        "overall_score": overall,
        "overall_feedback": (
            "Live AI evaluation was temporarily unavailable. This continuity score measures only observable "
            "completeness, structure and role/question relevance; it does not validate technical correctness."
        ),
        "dimensions": {
            "relevance": relevance,
            "clarity": structure,
            "structure": structure,
            "language_precision": structure,
            "role_knowledge": overall,
            "problem_solving": overall,
            "professionalism": structure,
        },
        "strengths": ["The session was preserved instead of failing when the external AI evaluator was unavailable."],
        "improvements": ["Re-run live AI analysis later for technical-correctness feedback and richer coaching."],
        "weak_topics": [],
        "next_practice_plan": [
            "Strengthen each answer with a concrete example, explicit reasoning and a validation step.",
            "Use live AI analysis when available for technical-correctness and concept-level feedback.",
        ],
        "evaluations": evaluations,
        "disclaimer": (
            "Resilient baseline only: completeness/relevance signal, not a technical-correctness score, "
            "spoken-communication assessment, personality measure, or employability judgment."
        ),
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
            "section": item.get("section"),
            "category": item.get("category"),
            "difficulty": item.get("difficulty"),
            "answer_type": item.get("answer_type"),
            "options": item.get("options") or [],
            "correct_answer": item.get("correct_answer") or "",
            "answer": submitted_by_id[item["question_id"]].answer,
        }
        for item in issued
    ]
    prompt = f"""
{PROMPT_GUARDRAIL}

You are a rigorous role-specific campus interview coach. Evaluate every written answer below against the exact role.
Do not infer accent, spoken fluency, appearance, personality, protected traits or anything not evidenced by the text.
Use only ROLE, CANDIDATE CONTEXT, QUESTIONS AND ANSWERS as evidence. Never invent company facts, candidate projects,
metrics, technologies or experience. If a fact needed for evaluation is absent, explicitly say it is not provided.
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
    evaluation_started = time.perf_counter()
    evaluation_mode = "ai"
    evaluation_provider = "local"
    evaluation_model = "resilient-baseline-v1"
    try:
        raw = _call_interview_ai(prompt, max_output_tokens=5200, fast=False)
        data = extract_json_from_response(raw)
        if not isinstance(data, dict):
            raise ValueError("AI service returned an invalid interview evaluation")
        evaluation_provider = current_ai_provider()
        evaluation_model = current_ai_model()
    except Exception as exc:
        LOGGER.warning("Mock interview live AI evaluation failed; using resilient baseline error_type=%s", type(exc).__name__)
        baseline = _resilient_baseline_evaluation(
            issued=issued,
            submitted_by_id=submitted_by_id,
            job=job,
        )
        interview.answers_json = json.dumps(answers_payload)
        interview.evaluation_json = json.dumps(baseline)
        interview.overall_score = baseline["overall_score"]
        interview.overall_feedback = baseline["overall_feedback"]
        db.commit()
        db.refresh(interview)
        return {
            "interview_id": interview.id,
            "job_title": job.title,
            **baseline,
            "evaluation_mode": "resilient_baseline",
            "provider": "local",
            "model": "resilient-baseline-v1",
            "evaluation_ms": int((time.perf_counter() - evaluation_started) * 1000),
        }

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
    evaluation_ms = int((time.perf_counter() - evaluation_started) * 1000)
    LOGGER.info(
        "Mock interview evaluated mode=%s provider=%s model=%s latency_ms=%s",
        evaluation_mode,
        evaluation_provider,
        evaluation_model,
        evaluation_ms,
    )
    return {
        "interview_id": interview.id,
        "job_title": job.title,
        **result,
        "evaluation_mode": evaluation_mode,
        "provider": evaluation_provider,
        "model": evaluation_model,
        "evaluation_ms": evaluation_ms,
    }
