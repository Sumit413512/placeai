from __future__ import annotations

import io
import json
import re
import unicodedata
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

try:
    import pypdf
except ImportError:
    pypdf = None

from app.ai_provider import call_ai_text
from app.ai_rate_limit import student_ai_guard
from app.database import get_db
from app.dependencies import require_student
from app.models import StudentProfile, User
from app.schemas import AIResumeParseResult, AISummaryResult
from app.storage import read_file_bytes
from app.routers.ai import PROMPT_GUARDRAIL, extract_json_from_response

router = APIRouter(prefix="/ai", tags=["AI Features ✨"])

_MAX_RESUME_TEXT = 24_000


def _repair_pdf_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    text = text.replace("\u00ad", "").replace("\u200b", "").replace("\ufeff", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Join words split by a PDF line-wrap hyphen: "develop-\nment" -> "development".
    text = re.sub(r"(?<=\w)-[ \t]*\n[ \t]*(?=\w)", "", text)
    # Repair a common PDF-font extraction artifact such as "P y t h o n".
    spaced_word = re.compile(r"\b(?:[A-Za-z0-9]\s+){3,}[A-Za-z0-9]\b")
    text = spaced_word.sub(lambda match: re.sub(r"\s+", "", match.group(0)), text)
    lines: list[str] = []
    for raw in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", raw).strip()
        if line:
            lines.append(line)
    return "\n".join(lines).strip()


def _page_text(page: Any) -> str:
    candidates: list[str] = []
    try:
        layout = page.extract_text(extraction_mode="layout") or ""
        if layout.strip():
            candidates.append(layout)
    except (TypeError, ValueError, NotImplementedError):
        pass
    try:
        plain = page.extract_text() or ""
        if plain.strip():
            candidates.append(plain)
    except Exception:
        pass
    if not candidates:
        return ""

    def quality(text: str) -> tuple[int, int]:
        repaired = _repair_pdf_text(text)
        tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9+#./&()_-]*", repaired)
        return len(tokens), len(repaired)

    return max(candidates, key=quality)


def extract_resume_text(data: bytes) -> str:
    if pypdf is None:
        raise HTTPException(status_code=503, detail="PDF extraction dependency is unavailable")
    try:
        reader = pypdf.PdfReader(io.BytesIO(data), strict=False)
        if getattr(reader, "is_encrypted", False):
            raise HTTPException(status_code=422, detail="Encrypted or password-protected resumes are not supported")
        if len(reader.pages) > 30:
            raise HTTPException(status_code=422, detail="Resume PDF must be 30 pages or fewer")
        parts: list[str] = []
        total = 0
        for page in reader.pages:
            part = _page_text(page)
            if part:
                parts.append(part)
                total += len(part)
            if total >= 50_000:
                break
        text = _repair_pdf_text("\n".join(parts))[:50_000]
        if len(text) < 50:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Could not extract readable text from the PDF. Export the resume as a text-based PDF and try again.",
            )
        return text
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Could not safely extract text from the uploaded PDF") from exc


def _clean_string(value: Any, limit: int = 4000) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _dedupe_strings(values: Any, *, limit: int = 120, item_limit: int = 120) -> list[str]:
    if not isinstance(values, list):
        return []
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = _clean_string(value, item_limit).strip("•·,;| ")
        if not item or len(item) < 2:
            continue
        key = re.sub(r"\s+", " ", item).casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
        if len(output) >= limit:
            break
    return output


def _normalize_records(values: Any, allowed: tuple[str, ...], *, max_rows: int = 40) -> list[dict[str, str]]:
    if not isinstance(values, list):
        return []
    rows: list[dict[str, str]] = []
    for value in values[:max_rows]:
        if not isinstance(value, dict):
            continue
        row = {key: _clean_string(value.get(key), 3000 if key == "description" else 500) for key in allowed}
        if any(row.values()):
            rows.append(row)
    return rows


def _merge_profile_skills(existing: list[str] | None, parsed: list[str]) -> list[str]:
    # Resume parsing should enrich a profile, not silently discard skills the student entered manually.
    return _dedupe_strings([*(existing or []), *parsed], limit=150, item_limit=120)


@router.post(
    "/parse-resume",
    dependencies=[Depends(student_ai_guard)],
    response_model=AIResumeParseResult,
)
def parse_resume_v2(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == current_user.id).first()
    if not profile or not profile.resume:
        raise HTTPException(status_code=404, detail="Please upload a resume first")
    resume = profile.resume
    resume_bytes = read_file_bytes(db, resume.filepath)
    if not resume_bytes:
        raise HTTPException(status_code=404, detail="Resume file not found")

    resume_text = extract_resume_text(resume_bytes)
    prompt = f"""
{PROMPT_GUARDRAIL}

You are a high-accuracy resume parser for a campus placement platform.
Read the ENTIRE resume text. Preserve the candidate's actual spelling, capitalization, company names,
degrees and technology names; do not correct a proper noun unless the source itself is unambiguous.
Extract every explicit skill from Skills/Technical Skills sections and also technologies actually used in
projects or experience. Include programming languages, frameworks, libraries, databases, cloud/services,
devops/tooling, operating systems, testing tools and explicitly stated professional skills. Do not invent skills.
Deduplicate aliases only when they are clearly the same skill. Do not truncate the skills list merely because it is long.

Return ONLY valid JSON with exactly this structure:
{{
  "skills": ["skill1", "skill2"],
  "experience": [{{"company":"...","role":"...","duration":"...","description":"..."}}],
  "education": [{{"institution":"...","degree":"...","field":"...","year":"...","cgpa_or_percentage":"..."}}],
  "certifications": ["..."],
  "languages": ["..."],
  "summary": "A factual 3-4 sentence professional summary grounded only in the resume"
}}

FULL RESUME TEXT
---
{resume_text[:_MAX_RESUME_TEXT]}
---
"""
    raw = call_ai_text(prompt, reasoning_effort="low", max_output_tokens=3500)
    data = extract_json_from_response(raw)
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="AI service returned an invalid resume structure")

    skills = _dedupe_strings(data.get("skills"), limit=150, item_limit=120)
    result = {
        "skills": skills,
        "experience": _normalize_records(data.get("experience"), ("company", "role", "duration", "description")),
        "education": _normalize_records(data.get("education"), ("institution", "degree", "field", "year", "cgpa_or_percentage")),
        "certifications": _dedupe_strings(data.get("certifications"), limit=80, item_limit=240),
        "languages": _dedupe_strings(data.get("languages"), limit=40, item_limit=80),
        "summary": _clean_string(data.get("summary"), 3000) or None,
    }
    resume.ai_parsed_data = result
    resume.is_parsed = True
    profile.skills = _merge_profile_skills(profile.skills, skills)
    if result["certifications"]:
        profile.certifications = _dedupe_strings(
            [*(profile.certifications or []), *result["certifications"]], limit=100, item_limit=240
        )
    db.commit()
    return AIResumeParseResult(**result)


@router.post(
    "/generate-summary",
    dependencies=[Depends(student_ai_guard)],
    response_model=AISummaryResult,
)
def generate_summary_v2(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Student profile not found")
    resume_data = profile.resume.ai_parsed_data if profile.resume and profile.resume.ai_parsed_data else {}
    evidence = {
        "name": profile.full_name,
        "college": profile.college,
        "degree": profile.degree,
        "branch": profile.branch,
        "graduation_year": profile.graduation_year,
        "cgpa": profile.cgpa,
        "skills": profile.skills or [],
        "desired_roles": profile.desired_roles or [],
        "experience": resume_data.get("experience", []),
        "certifications": _dedupe_strings([*(profile.certifications or []), *(resume_data.get("certifications", []) or [])]),
        "resume_summary": resume_data.get("summary"),
        "bio": profile.bio,
    }
    prompt = f"""
{PROMPT_GUARDRAIL}

Write a recruiter-facing professional summary in 3-4 concise sentences using ONLY the evidence below.
Prioritize the candidate's strongest role-relevant technical skills, concrete experience/projects and education.
Do not invent years of experience, achievements, technologies, employment status or career claims.
Avoid generic filler such as 'hard-working' unless supported by evidence.
Return ONLY the final summary paragraph as plain text, with no markdown and no JSON.

CANDIDATE EVIDENCE
{json.dumps(evidence, ensure_ascii=False, indent=2)[:18_000]}
"""
    summary_text = _clean_string(
        call_ai_text(prompt, reasoning_effort="none", max_output_tokens=700),
        3000,
    )
    if not summary_text:
        raise HTTPException(status_code=502, detail="AI service returned an empty profile summary")
    profile.ai_summary = summary_text
    db.commit()
    return AISummaryResult(student_id=profile.id, summary=summary_text)
