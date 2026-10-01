from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import ApprovalStatus, Job, StudentProfile
from app.roadmap_market import search_current_market
from app.routers.ai import PROMPT_GUARDRAIL, extract_json_from_response

ROADMAP_DISCLAIMER = (
    "This roadmap is personalized guidance based on your profile and a current-market research snapshot. "
    "Hiring demand changes over time, so use the cited sources and refresh the roadmap when your goal or market changes."
)


def _clean(value: Any, limit: int = 1200) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _string_list(value: Any, *, limit: int = 20, item_limit: int = 240) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    seen: set[str] = set()
    for raw in value:
        item = _clean(raw, item_limit)
        if len(item) < 2:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
        if len(output) >= limit:
            break
    return output


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _normalize_skills(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    output: list[dict[str, str]] = []
    for raw in value[:16]:
        if isinstance(raw, str):
            name = _clean(raw, 120)
            if name:
                output.append({"name": name, "level": "working", "why": ""})
            continue
        if not isinstance(raw, dict):
            continue
        name = _clean(raw.get("name"), 120)
        if not name:
            continue
        output.append({
            "name": name,
            "level": _clean(raw.get("level"), 80) or "working",
            "why": _clean(raw.get("why"), 500),
        })
    return output


def _normalize_projects(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    output: list[dict[str, Any]] = []
    for raw in value[:8]:
        if not isinstance(raw, dict):
            continue
        title = _clean(raw.get("title"), 180)
        if not title:
            continue
        output.append({
            "title": title,
            "scope": _clean(raw.get("scope"), 1000),
            "deliverables": _string_list(raw.get("deliverables"), limit=10, item_limit=300),
            "portfolio_proof": _clean(raw.get("portfolio_proof"), 600),
        })
    return output


def _normalize_phases(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    output: list[dict[str, Any]] = []
    for index, raw in enumerate(value[:10], start=1):
        if not isinstance(raw, dict):
            continue
        name = _clean(raw.get("name"), 180)
        if not name:
            continue
        output.append({
            "phase": _bounded_int(raw.get("phase"), default=index, minimum=1, maximum=20),
            "name": name,
            "days": _bounded_int(raw.get("days"), default=14, minimum=1, maximum=180),
            "outcomes": _string_list(raw.get("outcomes"), limit=12, item_limit=350),
            "skills": _normalize_skills(raw.get("skills")),
            "projects": _normalize_projects(raw.get("projects")),
            "practice": _string_list(raw.get("practice"), limit=12, item_limit=350),
            "milestone": _clean(raw.get("milestone"), 700),
        })
    return output


def _normalize_learning_pattern(value: Any) -> dict[str, str]:
    raw = value if isinstance(value, dict) else {}
    return {
        "recommended_style": _clean(raw.get("recommended_style"), 500),
        "weekly_cycle": _clean(raw.get("weekly_cycle"), 1000),
        "daily_session": _clean(raw.get("daily_session"), 1000),
        "revision_strategy": _clean(raw.get("revision_strategy"), 1000),
    }


def normalize_roadmap_payload(payload: dict[str, Any], *, request_data: dict[str, Any]) -> dict[str, Any]:
    phases = _normalize_phases(payload.get("phases"))
    phase_days = sum(phase["days"] for phase in phases)
    requested_days = request_data.get("desired_timeline_days")
    fallback_days = requested_days or phase_days or 90
    estimated_days = phase_days or _bounded_int(
        payload.get("estimated_days"),
        default=int(fallback_days),
        minimum=14,
        maximum=730,
    )

    market_raw = payload.get("market_snapshot") if isinstance(payload.get("market_snapshot"), dict) else {}
    market_snapshot = {
        "as_of": date.today().isoformat(),
        "region": _clean(market_raw.get("region"), 120) or request_data["market_region"],
        "target_roles": _string_list(market_raw.get("target_roles"), limit=10, item_limit=180)
        or request_data["target_roles"],
        "demand_signals": _string_list(market_raw.get("demand_signals"), limit=12, item_limit=500),
        "in_demand_skills": _string_list(market_raw.get("in_demand_skills"), limit=20, item_limit=160),
        "tools_and_technologies": _string_list(market_raw.get("tools_and_technologies"), limit=20, item_limit=160),
        "entry_level_expectations": _string_list(market_raw.get("entry_level_expectations"), limit=12, item_limit=500),
        "market_notes": _string_list(market_raw.get("market_notes"), limit=10, item_limit=600),
    }

    title = _clean(payload.get("title"), 240)
    if not title:
        target = request_data["target_roles"][0] if request_data["target_roles"] else (
            request_data["target_fields"][0] if request_data["target_fields"] else "Career"
        )
        title = f"{target} Career Roadmap"

    return {
        "title": title,
        "market_snapshot": market_snapshot,
        "estimated_days": estimated_days,
        "weekly_hours": _bounded_int(
            payload.get("weekly_hours"),
            default=request_data["hours_per_week"],
            minimum=1,
            maximum=80,
        ),
        "learning_pattern": _normalize_learning_pattern(payload.get("learning_pattern")),
        "phases": phases,
        "advanced_next_steps": _string_list(payload.get("advanced_next_steps"), limit=15, item_limit=500),
        "portfolio_plan": _string_list(payload.get("portfolio_plan"), limit=15, item_limit=500),
        "interview_preparation": _string_list(payload.get("interview_preparation"), limit=15, item_limit=500),
        "disclaimer": ROADMAP_DISCLAIMER,
    }


def _public_market_context(db: Session) -> dict[str, Any]:
    rows = (
        db.query(Job)
        .filter(
            Job.is_active.is_(True),
            Job.approval_status == ApprovalStatus.approved,
            Job.visibility == "public",
        )
        .order_by(Job.created_at.desc())
        .limit(80)
        .all()
    )
    role_counts = Counter(_clean(job.title, 180) for job in rows if _clean(job.title, 180))
    skill_counts: Counter[str] = Counter()
    for job in rows:
        for skill in job.required_skills or []:
            cleaned = _clean(skill, 120)
            if cleaned:
                skill_counts[cleaned] += 1
    return {
        "public_placeai_jobs_sampled": len(rows),
        "frequent_public_role_titles": [name for name, _ in role_counts.most_common(15)],
        "frequent_required_skills": [name for name, _ in skill_counts.most_common(20)],
    }


def _profile_context(profile: StudentProfile) -> dict[str, Any]:
    resume_data = profile.resume.ai_parsed_data if profile.resume and profile.resume.ai_parsed_data else {}
    experience = resume_data.get("experience", []) if isinstance(resume_data, dict) else []
    return {
        "degree": profile.degree,
        "branch": profile.branch,
        "graduation_year": profile.graduation_year,
        "cgpa": profile.cgpa,
        "profile_skills": profile.skills or [],
        "desired_roles": profile.desired_roles or [],
        "certifications": profile.certifications or [],
        "resume_experience": experience[:12] if isinstance(experience, list) else [],
        "resume_summary": resume_data.get("summary") if isinstance(resume_data, dict) else None,
    }


def generate_market_roadmap(
    *,
    db: Session,
    profile: StudentProfile,
    request_data: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, str]], str]:
    evidence = {
        "student": _profile_context(profile),
        "student_input": request_data,
        "placeai_public_market_context": _public_market_context(db),
    }
    today = date.today().isoformat()
    prompt = f"""
{PROMPT_GUARDRAIL}

You are PlaceAI Career Roadmap, a career-planning system for students.
You MUST use live web search in this request to research the CURRENT employment market as of {today}.
Focus on the student's requested market region ({request_data["market_region"]}) and target roles/fields.
Prefer recent employer career pages, official technology documentation, reputable labour/industry reports,
and current job-market evidence. Do not claim a skill is in demand unless current evidence supports it.

Create a realistic learning roadmap grounded in BOTH:
1. the student's current profile and explicit interests/goals, and
2. the current market research you perform now.

The plan must be actionable for a student, not a generic list. Avoid guaranteeing employment, salary,
interviews or placement. Do not recommend unethical shortcuts. Estimate time based on the requested
hours per week and the actual learning/project load. If the student's requested timeline is unrealistic,
use a realistic duration and explain that through the phases.

Return ONLY valid JSON with exactly this top-level structure:
{{
  "title": "Personalized roadmap title",
  "market_snapshot": {{
    "region": "market region",
    "target_roles": ["role"],
    "demand_signals": ["current evidence-based signal"],
    "in_demand_skills": ["skill"],
    "tools_and_technologies": ["tool"],
    "entry_level_expectations": ["expectation"],
    "market_notes": ["important caveat or trend"]
  }},
  "estimated_days": 120,
  "weekly_hours": 12,
  "learning_pattern": {{
    "recommended_style": "how this student should learn",
    "weekly_cycle": "repeatable weekly routine",
    "daily_session": "repeatable daily session structure",
    "revision_strategy": "how to revise and retain skills"
  }},
  "phases": [
    {{
      "phase": 1,
      "name": "Foundation",
      "days": 30,
      "outcomes": ["measurable outcome"],
      "skills": [{{"name":"Python","level":"working","why":"market/profile reason"}}],
      "projects": [{{
        "title":"Project name",
        "scope":"what to build and why",
        "deliverables":["GitHub repo","README","demo"],
        "portfolio_proof":"what evidence demonstrates competence"
      }}],
      "practice": ["specific practice routine"],
      "milestone": "objective completion check"
    }}
  ],
  "advanced_next_steps": ["advanced topic or next action"],
  "portfolio_plan": ["portfolio action"],
  "interview_preparation": ["role-specific interview preparation"]
}}

Student and PlaceAI evidence:
{json.dumps(evidence, ensure_ascii=False, indent=2)[:24_000]}
"""
    raw, sources, model = search_current_market(prompt)
    try:
        parsed = extract_json_from_response(raw)
    except HTTPException as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "CURRENT_MARKET_RESPONSE_INVALID",
                "message": "Current-market research returned an invalid structured response. Please try again.",
            },
        ) from exc
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=502,
            detail={
                "code": "CURRENT_MARKET_RESPONSE_INVALID",
                "message": "Current-market research returned an invalid structured response. Please try again.",
            },
        )
    normalized = normalize_roadmap_payload(parsed, request_data=request_data)
    if not normalized["phases"]:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "CURRENT_MARKET_RESPONSE_INCOMPLETE",
                "message": "Current-market research did not return an actionable learning plan. Please try again.",
            },
        )
    return normalized, sources, model
