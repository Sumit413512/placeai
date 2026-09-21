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

from app.ai_provider import call_ai_text, call_ai_vision_text, current_ai_model, current_ai_provider
from app.ai_rate_limit import student_ai_guard
from app.coding_assessment import (
    SUPPORTED_CODING_LANGUAGES,
    choose_coding_challenges,
    execute_test_suite,
    public_coding_spec,
)
from app.database import get_db
from app.dependencies import require_institution_admin, require_student
from app.models import ApprovalStatus, AuditEvent, Job, MockInterview, StudentProfile, User
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
    answer: str = Field(min_length=1, max_length=20000)
    language: str | None = Field(
        default=None,
        pattern="^(python|java|cpp|javascript)$",
    )


class MockInterviewCodingRunV2(BaseModel):
    model_config = {"extra": "forbid"}

    interview_id: str
    question_id: int = Field(ge=1, le=FULL_MOCK_QUESTION_COUNT)
    language: str = Field(pattern="^(python|java|cpp|javascript)$")
    source_code: str = Field(min_length=1, max_length=20000)
    mode: str = Field(default="run", pattern="^(run|submit)$")


class MockInterviewIntegrityEventV2(BaseModel):
    model_config = {"extra": "forbid"}

    event_type: str = Field(min_length=2, max_length=80)
    detail: str = Field(default="", max_length=1000)
    at: str = Field(default="", max_length=80)
    question: int | None = Field(default=None, ge=1, le=FULL_MOCK_QUESTION_COUNT)
    warning_number: int | None = Field(default=None, ge=1, le=20)
    source: str = Field(default="browser", pattern="^(browser|camera|vision|system|screen|on_device_ml)$")


class MockInterviewEvaluationV2(BaseModel):
    model_config = {"extra": "forbid"}

    interview_id: str
    answers: list[MockInterviewAnswerV2] = Field(min_length=1, max_length=FULL_MOCK_QUESTION_COUNT)
    integrity_events: list[MockInterviewIntegrityEventV2] = Field(default_factory=list, max_length=120)
    integrity_warning_count: int = Field(default=0, ge=0, le=100)
    integrity_auto_submitted: bool = False
    integrity_termination_reason: str | None = Field(default=None, max_length=1000)


class MockInterviewProctorFrameV2(BaseModel):
    model_config = {"extra": "forbid"}

    interview_id: str
    image_data_url: str = Field(min_length=100, max_length=450_000)


class MockInterviewIntegritySignalV2(BaseModel):
    model_config = {"extra": "forbid"}

    interview_id: str
    event: MockInterviewIntegrityEventV2


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
        timeout_seconds=10 if fast else 45,
        retry_count_per_provider=0,
    )


def _call_interview_evaluator(prompt: str, *, max_output_tokens: int) -> str:
    """Use the flagship reasoning model for high-stakes result analysis.

    Generation stays on the lower-latency model. Result evaluation intentionally uses
    GPT-5.6 Sol with high reasoning because correctness matters more than latency here.
    """
    return call_ai_text(
        prompt,
        reasoning_effort="high",
        max_output_tokens=max_output_tokens,
        model_override="gpt-5.6-sol",
        timeout_seconds=60,
        retry_count_per_provider=1,
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
                "coding_spec": item.get("coding_spec") if isinstance(item.get("coding_spec"), dict) else None,
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


def _apply_standard_coding_challenges(
    *,
    items: list[dict[str, Any]],
    job: Job,
    previous_questions: list[str],
) -> list[dict[str, Any]]:
    """Replace the two coding-section prompts with executable, server-tested challenges."""
    coding_positions = [
        index for index, item in enumerate(items)
        if str(item.get("section", "")).strip().lower() == "coding"
    ]
    if not coding_positions:
        return items

    seed_value = f"{getattr(job, 'id', '')}:{job.title}"
    specs = choose_coding_challenges(
        seed_value=seed_value,
        previous_questions=previous_questions,
        count=len(coding_positions),
    )
    updated = list(items)
    for position, spec in zip(coding_positions, specs):
        updated[position] = {
            "question": str(spec["question"])[:2000],
            "section": "coding",
            "category": "coding",
            "difficulty": "hard" if position == coding_positions[-1] else "medium",
            "answer_type": "code",
            "options": [],
            "correct_answer": "",
            "coding_spec": spec,
        }
    return updated


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
        prompt_count = count if count == FULL_MOCK_QUESTION_COUNT else count + (2 if count >= 5 else 1)
        prompt = _question_prompt(
            profile=profile,
            job=job,
            focus=focus,
            difficulty=difficulty,
            count=prompt_count,
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
                options = [str(x).strip()[:1000] for x in (item.get("options") or [])[:4]] if count == FULL_MOCK_QUESTION_COUNT else []
                options = [option for option in options if option]
                raw_correct = str(item.get("correct_answer", ""))[:1000]
                resolved_correct = _resolve_correct_option(options, raw_correct) if len(options) == 4 else ""
                objective_section = count == FULL_MOCK_QUESTION_COUNT and section in {"quantitative", "logical", "communication"}

                # Objective sections are contractually MCQ-only. Reject malformed AI items
                # instead of silently degrading them to a text box; deterministic fallback
                # will fill the missing quota with four-option, server-keyed questions.
                if objective_section and (len(options) != 4 or not resolved_correct):
                    continue

                answer_type = "mcq" if count == FULL_MOCK_QUESTION_COUNT and len(options) == 4 and resolved_correct else "text"
                correct_answer = resolved_correct if answer_type == "mcq" else ""
                if answer_type == "text":
                    options = []
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
        fallback_count = count if count == FULL_MOCK_QUESTION_COUNT else needed
        fallback_items = _fallback_questions(
            profile=profile,
            job=job,
            focus=focus,
            difficulty=difficulty,
            count=fallback_count,
            previous=previous,
            already=accepted,
        )
        accepted.extend(fallback_items[:needed])
        generation_mode = "ai_plus_fallback" if provider != "local" else "resilient_fallback"

    selected_items = accepted[:count]
    if count == FULL_MOCK_QUESTION_COUNT:
        selected_items = _apply_standard_coding_challenges(
            items=selected_items,
            job=job,
            previous_questions=previous,
        )

    questions = [
        {"question_id": index, **item}
        for index, item in enumerate(selected_items, start=1)
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
    client_questions = []
    for item in questions:
        public_item = {
            key: value
            for key, value in item.items()
            if key not in {"correct_answer", "coding_spec"}
        }
        if item.get("answer_type") == "code" and isinstance(item.get("coding_spec"), dict):
            public_item["coding_spec"] = public_coding_spec(item["coding_spec"])
        client_questions.append(public_item)
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



SECTION_LABELS = {key: label for key, label, _ in ASSESSMENT_BLUEPRINT}
SECTION_WEIGHTS = {
    "quantitative": 10,
    "logical": 10,
    "communication": 10,
    "technical": 20,
    "programming": 15,
    "coding": 15,
    "resume": 7,
    "behavioral": 5,
    "role": 5,
    "situational": 3,
}


def _normalized_choice(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().casefold())


def _resolve_correct_option(options: list[str], raw_answer: str) -> str:
    raw = (raw_answer or "").strip()
    if not raw:
        return ""
    normalized = _normalized_choice(raw)
    for option in options:
        if _normalized_choice(option) == normalized:
            return option
    if len(raw) == 1 and raw.upper() in {"A", "B", "C", "D"}:
        index = ord(raw.upper()) - ord("A")
        if 0 <= index < len(options):
            return options[index]
    return ""


def _objective_evaluation(item: dict[str, Any], answer: str) -> dict[str, Any] | None:
    options = [str(x) for x in (item.get("options") or [])]
    correct = _resolve_correct_option(options, str(item.get("correct_answer", "")))
    if item.get("answer_type") != "mcq" or len(options) != 4 or not correct:
        return None
    is_correct = _normalized_choice(answer) == _normalized_choice(correct)
    return {
        "question_id": item["question_id"],
        "question": item["question"],
        "section": item.get("section") or item.get("category") or "interview",
        "category": item.get("category") or "interview",
        "difficulty": item.get("difficulty") or "mixed",
        "answer_type": "mcq",
        "answer": answer,
        "correct_answer": correct,
        "score": 100 if is_correct else 0,
        "verdict": "correct" if is_correct else "incorrect",
        "grading_method": "system",
        "rubric": {
            "correctness": 100 if is_correct else 0,
            "relevance": 100 if is_correct else 0,
            "reasoning": None,
            "completeness": 100 if is_correct else 0,
            "clarity": None,
        },
        "feedback": "Correct answer." if is_correct else "Incorrect answer.",
        "strengths": ["Selected the correct option."] if is_correct else [],
        "issues": [] if is_correct else ["The selected option does not match the server-side answer key."],
        "missing_points": [],
        "key_points": [f"Correct answer: {correct}"],
        "better_answer_outline": "",
        "ideal_answer": correct,
    }


_NON_ANSWER_LITERALS = {
    "anything", "test", "testing", "random", "asdf", "qwerty", "abc", "xyz",
    "hello", "nothing", "idk", "i dont know", "i don't know", "no idea", "na", "n/a",
    "whatever", "something", "answer",
}


def _text_words(value: str) -> list[str]:
    return re.findall(r"[a-z0-9+#.-]+", (value or "").casefold())


def _is_obvious_non_answer(item: dict[str, Any], answer: str) -> bool:
    clean = re.sub(r"\s+", " ", (answer or "").strip().casefold())
    if not clean:
        return True
    plain = re.sub(r"[^a-z0-9 ]+", " ", clean)
    plain = re.sub(r"\s+", " ", plain).strip()
    if plain in _NON_ANSWER_LITERALS:
        return True

    words = _text_words(clean)
    if len(words) <= 2:
        return True
    unique = set(words)
    if len(words) >= 4 and len(unique) / max(len(words), 1) < 0.28:
        return True

    # Only apply lexical irrelevance as a hard gate to very short responses. Longer
    # answers can use valid synonyms and must be judged semantically by the AI evaluator.
    if len(words) <= 5:
        question_terms = _evidence_terms(str(item.get("question", "")))
        answer_terms = _evidence_terms(answer)
        if question_terms and not (question_terms & answer_terms):
            return True
    return False


def _non_answer_evaluation(item: dict[str, Any], answer: str) -> dict[str, Any]:
    section = item.get("section") or item.get("category") or "interview"
    behavioral = section in {"resume", "behavioral", "role", "situational"}
    return {
        "question_id": item["question_id"],
        "question": item["question"],
        "section": section,
        "category": item.get("category") or section,
        "difficulty": item.get("difficulty") or "mixed",
        "answer_type": "text",
        "answer": answer,
        "correct_answer": "",
        "score": 0,
        "verdict": "weak" if behavioral else "insufficient",
        "grading_method": "system_relevance_gate",
        "rubric": {
            "correctness": 0,
            "relevance": 0,
            "reasoning": 0,
            "completeness": 0,
            "clarity": 0,
        },
        "feedback": "The response does not meaningfully answer the issued question, so no performance credit was awarded.",
        "strengths": [],
        "issues": ["The response is empty, placeholder-like, nonsensical, or unrelated to the question."],
        "missing_points": ["Provide a direct question-specific answer with relevant reasoning or evidence."],
        "key_points": [],
        "better_answer_outline": "Direct answer → question-specific reasoning → evidence/example → validation or result.",
        "ideal_answer": "",
    }


def _score_subjective_rubric(
    *,
    item: dict[str, Any],
    answer: str,
    rubric: dict[str, int],
) -> tuple[int, str]:
    section = str(item.get("section") or item.get("category") or "interview")
    correctness = _clamp_score(rubric.get("correctness"))
    relevance = _clamp_score(rubric.get("relevance"))
    reasoning = _clamp_score(rubric.get("reasoning"))
    completeness = _clamp_score(rubric.get("completeness"))
    clarity = _clamp_score(rubric.get("clarity"))

    if section in {"technical", "programming"}:
        score = round(
            correctness * 0.50
            + relevance * 0.25
            + reasoning * 0.15
            + completeness * 0.05
            + clarity * 0.05
        )
    elif section in {"resume", "behavioral", "role", "situational"}:
        score = round(
            correctness * 0.25
            + relevance * 0.30
            + reasoning * 0.20
            + completeness * 0.15
            + clarity * 0.10
        )
    else:
        score = round(
            correctness * 0.35
            + relevance * 0.30
            + reasoning * 0.15
            + completeness * 0.10
            + clarity * 0.10
        )

    word_count = len(_text_words(answer))
    if relevance < 15:
        score = min(score, 10)
    if section in {"technical", "programming"} and correctness < 20:
        score = min(score, 20)
    if word_count < 6:
        score = min(score, 15)
    score = _clamp_score(score)

    if section in {"resume", "behavioral", "role", "situational"}:
        if score >= 80 and relevance >= 65:
            verdict = "strong"
        elif score >= 55 and relevance >= 45:
            verdict = "acceptable"
        elif score <= 10:
            verdict = "insufficient"
        else:
            verdict = "weak"
    else:
        if score >= 80 and correctness >= 70 and relevance >= 65:
            verdict = "correct"
        elif score >= 45 and relevance >= 35:
            verdict = "partially_correct"
        elif score <= 10:
            verdict = "insufficient"
        else:
            verdict = "incorrect"
    return score, verdict


def _code_quality_prompt(
    *,
    profile: StudentProfile,
    job: Job,
    items: list[dict[str, Any]],
) -> str:
    payload = []
    for item in items:
        execution = item["execution"]
        payload.append({
            "question_id": item["question_id"],
            "question": item["question"],
            "language": item["language"],
            "source_code": item["answer"],
            "test_pass_rate": execution["pass_rate"],
            "compile_success": execution["compile_success"],
            "ideal_approach": (item.get("coding_spec") or {}).get("ideal_approach", ""),
        })
    return f"""
{PROMPT_GUARDRAIL}

You are PlaceAI's senior code reviewer. Automated sandbox test cases are the authority for functional correctness.
Do NOT override or reinterpret the test pass rate. Review only code quality, algorithmic reasoning, efficiency,
robustness, maintainability and edge-case awareness.

For each answer return a quality_score from 0-100 plus concise coaching. A compiling solution that fails most tests
may still demonstrate some code quality, but quality feedback must not imply that the solution is functionally correct.
Do not reward length. Do not invent runtime behavior beyond the supplied test evidence.

Return ONLY valid JSON:
{{
  "evaluations": [
    {{
      "question_id": 1,
      "quality_score": 0,
      "feedback": "...",
      "strengths": ["..."],
      "issues": ["..."],
      "complexity": "...",
      "better_answer_outline": "..."
    }}
  ]
}}

ROLE
Title: {job.title}
Required skills: {json.dumps(job.required_skills, ensure_ascii=False)}

AUTHORIZED CANDIDATE CONTEXT
{json.dumps(_candidate_context(profile), ensure_ascii=False, indent=2)[:9000]}

CODE SUBMISSIONS
{json.dumps(payload, ensure_ascii=False, indent=2)[:50000]}
"""


def _public_test_results(execution: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in execution.get("test_results", []):
        hidden = bool(row.get("hidden"))
        item = {
            "index": row.get("index"),
            "hidden": hidden,
            "passed": bool(row.get("passed")),
            "status": str(row.get("status", ""))[:120],
            "time": row.get("time"),
            "memory": row.get("memory"),
        }
        if not hidden:
            item["stdout"] = str(row.get("stdout", ""))[:3000]
            item["stderr"] = str(row.get("stderr", ""))[:3000]
        output.append(item)
    return output


def _evaluate_coding_answers(
    *,
    profile: StudentProfile,
    job: Job,
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not items:
        return [], {"provider": "system", "model": "sandbox-tests", "coding_questions": 0}

    executed: list[dict[str, Any]] = []
    for item in items:
        spec = item.get("coding_spec") if isinstance(item.get("coding_spec"), dict) else None
        language = str(item.get("language") or "").strip().lower()
        if not spec or language not in SUPPORTED_CODING_LANGUAGES:
            continue
        try:
            execution = execute_test_suite(
                source_code=item["answer"],
                language=language,
                test_cases=list(spec.get("test_cases") or []),
            )
            executed.append({**item, "execution": execution})
        except Exception as exc:
            LOGGER.warning(
                "Coding execution failed question_id=%s error_type=%s",
                item.get("question_id"),
                type(exc).__name__,
            )

    if not executed:
        return [], {"provider": "system", "model": "sandbox-tests", "coding_questions": 0}

    ai_by_id: dict[int, dict[str, Any]] = {}
    ai_provider = "unavailable"
    ai_model = "unavailable"
    try:
        raw = _call_interview_evaluator(
            _code_quality_prompt(profile=profile, job=job, items=executed),
            max_output_tokens=3600,
        )
        parsed = extract_json_from_response(raw)
        rows = parsed.get("evaluations", []) if isinstance(parsed, dict) else []
        if isinstance(rows, list):
            ai_by_id = {
                int(row.get("question_id")): row
                for row in rows
                if isinstance(row, dict) and str(row.get("question_id", "")).isdigit()
            }
        ai_provider = current_ai_provider()
        ai_model = current_ai_model()
    except Exception as exc:
        LOGGER.warning("Coding quality AI analysis failed error_type=%s", type(exc).__name__)

    evaluations: list[dict[str, Any]] = []
    for item in executed:
        qid = item["question_id"]
        execution = item["execution"]
        pass_rate = _clamp_score(execution.get("pass_rate"))
        quality_row = ai_by_id.get(qid, {})
        quality = _clamp_score(quality_row.get("quality_score")) if quality_row else 50
        compile_success = bool(execution.get("compile_success"))
        score = 0 if not compile_success else _clamp_score(round(pass_rate * 0.90 + quality * 0.10))
        if pass_rate == 100 and compile_success:
            verdict = "correct"
        elif pass_rate >= 40 and compile_success:
            verdict = "partially_correct"
        else:
            verdict = "incorrect"

        passed = int(execution.get("passed", 0) or 0)
        total = int(execution.get("total", 0) or 0)
        feedback_prefix = (
            f"Compilation successful. {passed}/{total} automated test cases passed."
            if compile_success
            else "Compilation failed; no functional credit was awarded."
        )
        ai_feedback = str(quality_row.get("feedback", "")).strip()
        evaluations.append({
            "question_id": qid,
            "question": item["question"],
            "section": "coding",
            "category": "coding",
            "difficulty": item.get("difficulty") or "mixed",
            "answer_type": "code",
            "answer": item["answer"],
            "language": item["language"],
            "correct_answer": "",
            "score": score,
            "verdict": verdict,
            "grading_method": "code_tests+ai",
            "rubric": {
                "correctness": pass_rate,
                "relevance": 100 if item["answer"].strip() else 0,
                "reasoning": quality,
                "completeness": pass_rate,
                "clarity": quality,
            },
            "feedback": (feedback_prefix + (" " + ai_feedback if ai_feedback else ""))[:5000],
            "strengths": [str(x)[:1000] for x in (quality_row.get("strengths") or [])[:8]],
            "issues": (
                ([] if compile_success else ["The submitted code did not compile successfully."])
                + [str(x)[:1000] for x in (quality_row.get("issues") or [])[:8]]
            ),
            "missing_points": (
                [] if pass_rate == 100 else ["Handle the remaining failing or hidden edge cases."]
            ),
            "key_points": [
                f"Automated tests passed: {passed}/{total}.",
                f"Functional correctness score: {pass_rate}/100.",
            ],
            "better_answer_outline": str(quality_row.get("better_answer_outline", ""))[:5000],
            "ideal_answer": str((item.get("coding_spec") or {}).get("ideal_approach", ""))[:5000],
            "coding": {
                "language": execution.get("language"),
                "language_label": execution.get("language_label"),
                "compile_success": compile_success,
                "passed": passed,
                "total": total,
                "pass_rate": pass_rate,
                "compile_output": str(execution.get("compile_output", ""))[:3000],
                "execution_ms": execution.get("execution_ms"),
                "test_results": _public_test_results(execution),
                "quality_score": quality,
                "complexity": str(quality_row.get("complexity", ""))[:1000],
            },
        })

    return evaluations, {
        "provider": ai_provider,
        "model": ai_model,
        "coding_questions": len(evaluations),
        "coding_correctness": "sandbox test cases",
    }


def _subjective_prompt(
    *,
    profile: StudentProfile,
    job: Job,
    items: list[dict[str, Any]],
) -> str:
    payload = [
        {
            "question_id": item["question_id"],
            "section": item.get("section"),
            "category": item.get("category"),
            "difficulty": item.get("difficulty"),
            "question": item["question"],
            "answer": item["answer"],
        }
        for item in items
    ]
    return f"""
{PROMPT_GUARDRAIL}

You are PlaceAI's senior assessment evaluator. Grade EACH candidate response independently against the exact question.
This is a scoring task, not encouragement. A fluent but irrelevant, fabricated, vague, nonsensical, evasive or technically
wrong answer must receive a low score. Never infer unstated facts. Do not give credit merely for length or vocabulary.

For technical/programming/coding questions use this rubric:
- factual/technical correctness: 45%
- direct relevance to the question: 15%
- reasoning / method / trade-offs: 15%
- completeness and edge cases: 10%
- concrete evidence / validation / examples: 10%
- clarity and precision: 5%

For resume/behavioral/role/situational questions use this rubric:
- direct relevance: 20%
- specific evidence or scenario detail: 25%
- ownership / credibility / consistency: 20%
- reasoning and decision quality: 15%
- structure and completeness: 10%
- role fit / reflection / clarity: 10%

Score EACH rubric dimension from 0-100. PlaceAI calculates the final numeric score server-side; do not try to compensate
one dimension with another. Use these verdicts only:
- correct: substantively correct and complete enough for the question
- partially_correct: meaningful correct content but material gaps/errors remain
- incorrect: substantively wrong, irrelevant, contradictory or unsupported
- insufficient: too little meaningful evidence to evaluate
- strong: high-quality behavioral/resume/role response with specific credible evidence
- acceptable: adequate behavioral/resume/role response but improvable
- weak: vague/generic behavioral/resume/role response with limited evidence

IMPORTANT:
- Random text, repeated words, placeholders such as "anything", gibberish, generic filler, or an answer unrelated to the
  question should normally score 0-15 and use verdict "incorrect", "insufficient", or "weak".
- Do not reward claims that are not supported by the candidate context or answer.
- The score must reflect the response to THIS question, not an overall impression of the candidate.
- Give actionable feedback and an example strong answer/solution, but never invent the candidate's personal experience.
  For behavioral/resume questions, provide a reusable structure/example with explicit placeholders rather than fabricated history.

Return ONLY valid JSON:
{{
  "evaluations": [
    {{
      "question_id": 1,
      "verdict": "correct|partially_correct|incorrect|insufficient|strong|acceptable|weak",
      "rubric": {{
        "correctness": 0,
        "relevance": 0,
        "reasoning": 0,
        "completeness": 0,
        "clarity": 0
      }},
      "feedback": "...",
      "strengths": ["..."],
      "issues": ["..."],
      "missing_points": ["..."],
      "key_points": ["..."],
      "better_answer_outline": "...",
      "ideal_answer": "..."
    }}
  ]
}}

ROLE
Title: {job.title}
Description: {job.description[:7000]}
Required skills: {json.dumps(job.required_skills, ensure_ascii=False)}

AUTHORIZED CANDIDATE CONTEXT
{json.dumps(_candidate_context(profile), ensure_ascii=False, indent=2)[:12000]}

RESPONSES TO GRADE
{json.dumps(payload, ensure_ascii=False, indent=2)[:44000]}
"""


def _evaluate_subjective_with_ai(
    *,
    profile: StudentProfile,
    job: Job,
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not items:
        return [], {"provider": "system", "model": "answer-key", "batches": 0}

    gated: list[dict[str, Any]] = []
    ai_items: list[dict[str, Any]] = []
    for item in items:
        if _is_obvious_non_answer(item, item["answer"]):
            gated.append(_non_answer_evaluation(item, item["answer"]))
        else:
            ai_items.append(item)

    if not ai_items:
        return gated, {
            "provider": "system",
            "model": "strict-relevance-gate",
            "batches": 0,
        }

    # Result analysis deliberately takes longer than question generation. Smaller batches
    # let the flagship reasoning model grade each answer against the exact question without
    # losing detail in a very large 50-item response.
    batches = [ai_items[index:index + 6] for index in range(0, len(ai_items), 6)]
    results: list[dict[str, Any]] = []
    provider = "unknown"
    model = "gpt-5.6-sol"

    for batch in batches:
        try:
            raw = _call_interview_evaluator(
                _subjective_prompt(profile=profile, job=job, items=batch),
                max_output_tokens=5200,
            )
            data = extract_json_from_response(raw)
            source = data.get("evaluations", []) if isinstance(data, dict) else []
            if not isinstance(source, list):
                raise ValueError("AI evaluator returned no batch evaluations")
            results.extend(item for item in source if isinstance(item, dict))
            provider = current_ai_provider()
            model = current_ai_model()
        except Exception as batch_exc:
            LOGGER.warning(
                "Subjective evaluation batch failed error_type=%s question_ids=%s",
                type(batch_exc).__name__,
                [item["question_id"] for item in batch],
            )

    normalized: list[dict[str, Any]] = list(gated)
    by_id = {
        int(item.get("question_id")): item
        for item in results
        if str(item.get("question_id", "")).isdigit()
    }

    for item in ai_items:
        qid = item["question_id"]
        source = by_id.get(qid)
        if not source:
            continue

        rubric_raw = source.get("rubric") if isinstance(source.get("rubric"), dict) else {}
        rubric = {
            "correctness": _clamp_score(rubric_raw.get("correctness")),
            "relevance": _clamp_score(rubric_raw.get("relevance")),
            "reasoning": _clamp_score(rubric_raw.get("reasoning")),
            "completeness": _clamp_score(rubric_raw.get("completeness")),
            "clarity": _clamp_score(rubric_raw.get("clarity")),
        }
        score, verdict = _score_subjective_rubric(
            item=item,
            answer=item["answer"],
            rubric=rubric,
        )

        normalized.append({
            "question_id": qid,
            "question": item["question"],
            "section": item.get("section") or item.get("category") or "interview",
            "category": item.get("category") or "interview",
            "difficulty": item.get("difficulty") or "mixed",
            "answer_type": "text",
            "answer": item["answer"],
            "correct_answer": "",
            "score": score,
            "verdict": verdict,
            "grading_method": "ai_rubric_server_scored",
            "rubric": rubric,
            "feedback": str(source.get("feedback", ""))[:5000],
            "strengths": [str(x)[:1000] for x in (source.get("strengths") or [])[:8]],
            "issues": [str(x)[:1000] for x in (source.get("issues") or [])[:8]],
            "missing_points": [str(x)[:1000] for x in (source.get("missing_points") or [])[:10]],
            "key_points": [str(x)[:1000] for x in (source.get("key_points") or [])[:10]],
            "better_answer_outline": str(source.get("better_answer_outline", ""))[:5000],
            "ideal_answer": str(source.get("ideal_answer", ""))[:7000],
        })

    return normalized, {
        "provider": provider,
        "model": model,
        "batches": len(batches),
        "score_authority": "server-derived rubric",
        "relevance_gate_count": len(gated),
    }


def _verdict_bucket(verdict: str) -> str:
    if verdict in {"correct", "strong"}:
        return "correct"
    if verdict in {"partially_correct", "acceptable"}:
        return "partial"
    if verdict in {"incorrect", "weak"}:
        return "incorrect"
    return "insufficient"


def _build_assessment_result(
    *,
    evaluations: list[dict[str, Any]],
    issued: list[dict[str, Any]],
    ai_meta: dict[str, Any],
) -> dict[str, Any]:
    by_id = {item["question_id"]: item for item in evaluations}
    section_rows = []
    section_scores: dict[str, int] = {}
    total_correct = total_partial = total_incorrect = total_insufficient = 0
    system_graded = ai_graded = coding_graded = 0

    for key, label, _ in ASSESSMENT_BLUEPRINT:
        section_evals = [item for item in evaluations if item.get("section") == key]
        if not section_evals:
            continue
        score = round(sum(item["score"] for item in section_evals) / len(section_evals))
        section_scores[key] = score
        counts = {"correct": 0, "partial": 0, "incorrect": 0, "insufficient": 0}
        for item in section_evals:
            counts[_verdict_bucket(item.get("verdict", "insufficient"))] += 1
            grading_method = str(item.get("grading_method") or "")
            if grading_method in {"system", "system_relevance_gate"}:
                system_graded += 1
            elif grading_method == "code_tests+ai":
                coding_graded += 1
            elif grading_method.startswith("ai"):
                ai_graded += 1
        total_correct += counts["correct"]
        total_partial += counts["partial"]
        total_incorrect += counts["incorrect"]
        total_insufficient += counts["insufficient"]
        section_rows.append({
            "key": key,
            "label": label,
            "score": score,
            "questions": len(section_evals),
            **counts,
        })

    missing_ids = [item["question_id"] for item in issued if item["question_id"] not in by_id]
    analysis_complete = not missing_ids
    raw_score = (
        round(sum(item["score"] for item in evaluations) / len(evaluations))
        if evaluations else 0
    )

    weighted_total = 0.0
    applied_weight = 0
    for section, score in section_scores.items():
        weight = SECTION_WEIGHTS.get(section, 0)
        weighted_total += score * weight
        applied_weight += weight
    readiness_index = (
        round(weighted_total / applied_weight)
        if len(issued) == FULL_MOCK_QUESTION_COUNT and applied_weight
        else raw_score
    )

    strongest = sorted(section_rows, key=lambda row: row["score"], reverse=True)[:3]
    weakest = sorted(section_rows, key=lambda row: row["score"])[:3]
    strengths = [
        f'{row["label"]}: {row["score"]}/100 across {row["questions"]} evaluated item(s).'
        for row in strongest
    ]
    improvements = [
        f'{row["label"]}: {row["score"]}/100 — prioritize this section in the next practice cycle.'
        for row in weakest
    ]
    weak_topics = [row["label"] for row in weakest if row["score"] < 70]
    next_plan = [
        f'Review the {row["label"]} question-level feedback, then complete a targeted drill before the next full mock.'
        for row in weakest
    ]

    objective_items = [
        item for item in evaluations
        if item.get("grading_method") in {"system", "system_relevance_gate"}
        and item.get("answer_type") == "mcq"
    ]
    subjective_items = [
        item for item in evaluations
        if str(item.get("grading_method") or "").startswith("ai")
    ]
    objective_accuracy = (
        round(100 * sum(item["score"] == 100 for item in objective_items) / len(objective_items))
        if objective_items else None
    )
    subjective_average = (
        round(sum(item["score"] for item in subjective_items) / len(subjective_items))
        if subjective_items else None
    )

    overall_feedback = (
        f'PlaceAI evaluated {len(evaluations)} of {len(issued)} responses question-by-question. '
        f'{total_correct} were correct/strong, {total_partial} partial/acceptable, '
        f'{total_incorrect} incorrect/weak, and {total_insufficient} insufficient.'
    )
    if not analysis_complete:
        overall_feedback += (
            f' {len(missing_ids)} open-ended response(s) could not be AI-evaluated, so the final overall score is withheld.'
        )

    return {
        "analysis_status": "complete" if analysis_complete else "incomplete",
        "overall_score": readiness_index if analysis_complete else None,
        "raw_assessment_score": raw_score if analysis_complete else None,
        "overall_feedback": overall_feedback,
        "score_summary": {
            "total_questions": len(issued),
            "evaluated_questions": len(evaluations),
            "correct": total_correct,
            "partial": total_partial,
            "incorrect": total_incorrect,
            "insufficient": total_insufficient,
            "system_graded": system_graded,
            "ai_graded": ai_graded,
            "coding_graded": coding_graded,
            "objective_accuracy": objective_accuracy,
            "subjective_average": subjective_average,
        },
        "section_scores": section_rows,
        "dimensions": {row["key"]: row["score"] for row in section_rows},
        "strengths": strengths,
        "improvements": improvements,
        "weak_topics": weak_topics,
        "next_practice_plan": next_plan,
        "evaluations": sorted(evaluations, key=lambda item: item["question_id"]),
        "missing_evaluation_question_ids": missing_ids,
        "grading": {
            "objective": "server-side answer key",
            "subjective": "AI question-level rubric",
            **ai_meta,
        },
        "disclaimer": (
            "Assessment scores reflect performance on this PlaceAI simulation. "
            "Open-ended answers are AI-evaluated against the issued question and rubric; "
            "integrity signals are reported separately and require human interpretation."
        ),
    }



def _reconcile_integrity_events(
    *,
    server_events: list[dict[str, Any]],
    client_events: list[dict[str, Any]],
    client_warning_count: int,
    client_auto_submitted: bool,
    client_termination_reason: str | None,
) -> dict[str, Any]:
    """Build the final integrity state from server audit evidence plus client fallback data.

    Server-persisted events are the authoritative minimum. Client events are retained as
    supplemental evidence for transient network failures, but cannot erase server events.
    """
    merged: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    for raw in [*server_events, *client_events]:
        if not isinstance(raw, dict):
            continue
        event = {
            "event_type": str(raw.get("event_type", ""))[:80],
            "detail": str(raw.get("detail", ""))[:1000],
            "at": str(raw.get("at", ""))[:80],
            "question": raw.get("question"),
            "warning_number": raw.get("warning_number"),
            "source": str(raw.get("source", "system"))[:40],
        }
        key = (
            event["event_type"],
            event["detail"],
            event["at"],
            event["question"],
            event["warning_number"],
            event["source"],
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(event)

    # Keep the report bounded while preserving the newest evidence.
    if len(merged) > 120:
        merged = merged[-120:]

    warning_numbers = [
        int(event["warning_number"])
        for event in merged
        if isinstance(event.get("warning_number"), int) and int(event["warning_number"]) > 0
    ]
    if warning_numbers:
        warning_count = min(4, max(warning_numbers))
    elif merged:
        warning_count = 0
    else:
        warning_count = min(4, max(0, int(client_warning_count or 0)))

    auto_event = next(
        (event for event in reversed(merged) if event.get("event_type") == "integrity_auto_submit"),
        None,
    )
    auto_submitted = bool(client_auto_submitted or warning_count >= 4 or auto_event)
    termination_reason = (
        str((auto_event or {}).get("detail", "")).strip()
        or str(client_termination_reason or "").strip()
    )

    return {
        "events": merged,
        "warning_count": warning_count,
        "auto_submitted": auto_submitted,
        "termination_reason": termination_reason,
    }


@router.post("/proctor-frame")
def analyze_proctor_frame_v2(
    body: MockInterviewProctorFrameV2,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    """Best-effort webcam object/presence analysis. Frames are processed, not persisted."""
    profile = _profile(current_user, db)
    interview = db.query(MockInterview).filter(
        MockInterview.id == body.interview_id,
        MockInterview.student_id == profile.id,
    ).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Mock interview not found")
    if not body.image_data_url.startswith("data:image/jpeg;base64,"):
        raise HTTPException(status_code=422, detail="Proctor frame must be a compressed JPEG data URL")

    prompt = """
Analyze this single webcam frame only for assessment-integrity signals.
Return ONLY valid JSON:
{"candidate_visible":true,"person_count":1,"mobile_phone_detected":false,"notes":"..."}

Rules:
- candidate_visible means one person's face/body is visibly present enough to reasonably infer candidate presence.
- person_count is the number of clearly visible people; use 0 if no person is visible.
- mobile_phone_detected is true only if a handheld mobile phone/smartphone is clearly visible.
- If uncertain about a phone, return false.
- Do not infer identity, age, gender, race, emotion, attention, honesty, gaze, disability, or intent.
- Do not identify the person.
"""
    try:
        raw = call_ai_vision_text(prompt, body.image_data_url)
        data = extract_json_from_response(raw)
        if not isinstance(data, dict):
            raise ValueError("Invalid vision response")
        person_count = max(0, min(5, int(data.get("person_count", 0) or 0)))
        return {
            "candidate_visible": bool(data.get("candidate_visible", person_count >= 1)),
            "person_count": person_count,
            "mobile_phone_detected": bool(data.get("mobile_phone_detected", False)),
            "notes": str(data.get("notes", ""))[:500],
            "model": current_ai_model(),
            "provider": current_ai_provider(),
            "stored": False,
        }
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.warning("Proctor frame analysis unavailable error_type=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Proctor vision analysis is temporarily unavailable") from exc


@router.post("/integrity-event")
def record_integrity_event_v2(
    body: MockInterviewIntegritySignalV2,
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
    event = body.event.model_dump()
    audit = AuditEvent(
        actor_user_id=current_user.id,
        organization_id=profile.organization_id,
        action="mock_interview_integrity_signal",
        entity_type="mock_interview",
        entity_id=interview.id,
    )
    audit.details = event
    db.add(audit)
    db.commit()
    return {"recorded": True}


@router.post("/coding/run")
def run_coding_question_v2(
    body: MockInterviewCodingRunV2,
    current_user: User = Depends(require_student_premium_access),
    db: Session = Depends(get_db),
):
    profile = _profile(current_user, db)
    interview = db.query(MockInterview).filter(
        MockInterview.id == body.interview_id,
        MockInterview.student_id == profile.id,
    ).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Mock interview not found")

    issued = _issued_questions(interview)
    item = next((row for row in issued if row["question_id"] == body.question_id), None)
    if not item or item.get("answer_type") != "code":
        raise HTTPException(status_code=404, detail="Coding question not found")
    spec = item.get("coding_spec") if isinstance(item.get("coding_spec"), dict) else None
    if not spec:
        raise HTTPException(status_code=409, detail="Coding question configuration is unavailable")
    if body.language not in SUPPORTED_CODING_LANGUAGES:
        raise HTTPException(status_code=422, detail="Unsupported coding language")

    all_cases = list(spec.get("test_cases") or [])
    test_cases = (
        [case for case in all_cases if not bool(case.get("hidden"))]
        if body.mode == "run"
        else all_cases
    )
    try:
        execution = execute_test_suite(
            source_code=body.source_code,
            language=body.language,
            test_cases=test_cases,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        LOGGER.warning(
            "Coding runner unavailable interview_id=%s question_id=%s error_type=%s",
            interview.id,
            body.question_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="Coding execution service is temporarily unavailable. Your code has not been lost; please retry.",
        ) from exc

    response_rows = []
    for row, case in zip(execution.get("test_results", []), test_cases):
        hidden = bool(case.get("hidden"))
        result_row = {
            "index": row.get("index"),
            "hidden": hidden,
            "passed": bool(row.get("passed")),
            "status": row.get("status"),
            "time": row.get("time"),
            "memory": row.get("memory"),
        }
        if not hidden:
            result_row.update({
                "input": str(case.get("input", "")),
                "expected_output": str(case.get("expected_output", "")),
                "actual_output": str(row.get("stdout", ""))[:3000],
                "stderr": str(row.get("stderr", ""))[:3000],
            })
        response_rows.append(result_row)

    hidden_total = sum(1 for case in test_cases if bool(case.get("hidden")))
    hidden_passed = sum(
        1 for row in response_rows if row["hidden"] and row["passed"]
    )
    return {
        "question_id": body.question_id,
        "mode": body.mode,
        "language": execution.get("language"),
        "language_label": execution.get("language_label"),
        "compile_success": bool(execution.get("compile_success")),
        "compile_output": str(execution.get("compile_output", ""))[:3000],
        "passed": int(execution.get("passed", 0) or 0),
        "total": int(execution.get("total", 0) or 0),
        "pass_rate": int(execution.get("pass_rate", 0) or 0),
        "hidden_passed": hidden_passed,
        "hidden_total": hidden_total,
        "execution_ms": execution.get("execution_ms"),
        "test_results": response_rows,
    }


@router.get("/institution-results")
def institution_mock_interview_results_v2(
    current_user: User = Depends(require_institution_admin),
    db: Session = Depends(get_db),
):
    if not current_user.organization_id:
        raise HTTPException(status_code=403, detail="Institution account is not linked to an organization")
    rows = (
        db.query(MockInterview)
        .join(StudentProfile, MockInterview.student_id == StudentProfile.id)
        .filter(StudentProfile.organization_id == current_user.organization_id)
        .order_by(MockInterview.created_at.desc())
        .limit(250)
        .all()
    )
    output = []
    for row in rows:
        try:
            evaluation = json.loads(row.evaluation_json or "{}")
        except json.JSONDecodeError:
            evaluation = {}
        output.append({
            "interview_id": row.id,
            "student_id": row.student_id,
            "student_name": row.student.full_name if row.student else None,
            "student_college": (
                row.student.institution.name
                if row.student and row.student.institution
                else (row.student.college if row.student else None)
            ),
            "job_id": row.job_id,
            "overall_score": row.overall_score,
            "overall_feedback": row.overall_feedback,
            "integrity_report": evaluation.get("integrity_report", {}),
            "score_summary": evaluation.get("score_summary", {}),
            "section_scores": evaluation.get("section_scores", []),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })
    return output


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

    started = time.perf_counter()
    answers_payload: list[dict[str, Any]] = []
    evaluations: list[dict[str, Any]] = []
    subjective_items: list[dict[str, Any]] = []
    coding_items: list[dict[str, Any]] = []

    for item in issued:
        qid = item["question_id"]
        submitted = submitted_by_id[qid]
        answer = submitted.answer.strip()
        language = (submitted.language or "").strip().lower() or None
        answers_payload.append({
            "question_id": qid,
            "question": item["question"],
            "section": item.get("section"),
            "category": item.get("category"),
            "difficulty": item.get("difficulty"),
            "answer_type": item.get("answer_type"),
            "answer": answer,
            "language": language,
        })
        if answer.startswith("[No response submitted"):
            evaluations.append({
                "question_id": qid,
                "question": item["question"],
                "section": item.get("section") or item.get("category") or "interview",
                "category": item.get("category") or "interview",
                "difficulty": item.get("difficulty") or "mixed",
                "answer_type": item.get("answer_type") or "text",
                "answer": answer,
                "correct_answer": (
                    str(item.get("correct_answer", ""))
                    if item.get("answer_type") == "mcq"
                    else ""
                ),
                "score": 0,
                "verdict": "insufficient",
                "grading_method": "system",
                "rubric": {
                    "correctness": 0,
                    "relevance": 0,
                    "reasoning": 0,
                    "completeness": 0,
                    "clarity": 0,
                },
                "feedback": "No candidate response was submitted before the question or assessment closed.",
                "strengths": [],
                "issues": ["Question was not answered."],
                "missing_points": ["Submit a substantive response within the allotted time."],
                "key_points": [],
                "better_answer_outline": "",
                "ideal_answer": "",
            })
            continue
        if item.get("answer_type") == "code":
            coding_items.append({**item, "answer": answer, "language": language})
            continue

        objective = _objective_evaluation(item, answer)
        if objective is not None:
            evaluations.append(objective)
        else:
            subjective_items.append({**item, "answer": answer})

    coding_evaluations, coding_meta = _evaluate_coding_answers(
        profile=profile,
        job=job,
        items=coding_items,
    )
    evaluations.extend(coding_evaluations)

    subjective_evaluations, ai_meta = _evaluate_subjective_with_ai(
        profile=profile,
        job=job,
        items=subjective_items,
    )
    evaluations.extend(subjective_evaluations)
    ai_meta = {**ai_meta, "coding": coding_meta}
    result = _build_assessment_result(
        evaluations=evaluations,
        issued=issued,
        ai_meta=ai_meta,
    )

    server_audits = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.actor_user_id == current_user.id,
            AuditEvent.action == "mock_interview_integrity_signal",
            AuditEvent.entity_type == "mock_interview",
            AuditEvent.entity_id == interview.id,
        )
        .order_by(AuditEvent.created_at.asc())
        .all()
    )
    server_integrity_events = [
        audit.details for audit in server_audits if isinstance(audit.details, dict)
    ]
    reconciled_integrity = _reconcile_integrity_events(
        server_events=server_integrity_events,
        client_events=[event.model_dump() for event in body.integrity_events],
        client_warning_count=body.integrity_warning_count,
        client_auto_submitted=body.integrity_auto_submitted,
        client_termination_reason=body.integrity_termination_reason,
    )
    integrity_events = reconciled_integrity["events"]
    integrity_status = (
        "auto_submitted_review_required"
        if reconciled_integrity["auto_submitted"]
        else ("review_required" if integrity_events else "clear")
    )
    integrity_report = {
        "status": integrity_status,
        "warning_count": reconciled_integrity["warning_count"],
        "warning_limit": 4,
        "auto_submitted": reconciled_integrity["auto_submitted"],
        "termination_reason": reconciled_integrity["termination_reason"],
        "events": integrity_events,
        "evidence_basis": "server_reconciled",
        "institution_name": (
            profile.institution.name
            if profile.institution
            else (profile.college or "")
        ),
        "note": (
            "Integrity signals identify events for institutional review and are not, by themselves, "
            "a finding of cheating or misconduct. Server audit evidence cannot be removed by client submission."
        ),
    }
    result["integrity_report"] = integrity_report

    interview.answers_json = json.dumps(answers_payload)
    interview.evaluation_json = json.dumps(result)
    if result["analysis_status"] == "complete":
        interview.overall_score = result["overall_score"]
        interview.overall_feedback = result["overall_feedback"]
    else:
        # Preserve retryability: an incomplete AI analysis must never be persisted as a
        # misleading final numeric score.
        interview.overall_score = None
        interview.overall_feedback = "AI analysis incomplete; retry evaluation for a final score."
    db.commit()
    db.refresh(interview)

    evaluation_ms = int((time.perf_counter() - started) * 1000)
    LOGGER.info(
        "Mock interview evaluated status=%s objective=%s subjective=%s latency_ms=%s provider=%s model=%s",
        result["analysis_status"],
        result["score_summary"]["system_graded"],
        result["score_summary"]["ai_graded"],
        evaluation_ms,
        ai_meta.get("provider"),
        ai_meta.get("model"),
    )
    return {
        "interview_id": interview.id,
        "job_title": job.title,
        "institution_name": profile.institution.name if profile.institution else (profile.college or ""),
        **result,
        "evaluation_mode": "hybrid_question_level",
        "evaluation_ms": evaluation_ms,
    }
