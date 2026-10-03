from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from html import unescape
import re
from typing import Any
from urllib.parse import quote

import httpx

REMOTE_OK_API = "https://remoteok.com/api"
ARBEITNOW_API = "https://www.arbeitnow.com/api/job-board-api"
PUBLIC_MARKET_TIMEOUT_SECONDS = 7.0
MAX_MATCHED_JOBS = 36
MIN_MATCHED_JOBS = 3
MIN_MARKET_SKILLS = 3

_STOPWORDS = {
    "and", "the", "for", "with", "from", "role", "jobs", "job", "career",
    "engineer", "developer", "specialist", "associate", "junior", "senior",
}

_SKILL_VARIANTS: dict[str, tuple[str, ...]] = {
    "SQL": ("sql", "postgresql", "mysql", "sql server"),
    "Python": ("python",),
    "Excel": ("excel", "spreadsheets", "spreadsheet"),
    "Power BI": ("power bi", "powerbi"),
    "Tableau": ("tableau",),
    "Statistics": ("statistics", "statistical", "hypothesis testing"),
    "Data visualization": ("data visualization", "visualisation", "dashboarding", "dashboards"),
    "Pandas": ("pandas",),
    "NumPy": ("numpy",),
    "R": (" r ", "r programming", "r language"),
    "ETL": ("etl", "elt", "data pipeline", "data pipelines"),
    "Data modeling": ("data modeling", "data modelling", "dimensional modeling"),
    "dbt": ("dbt",),
    "Snowflake": ("snowflake",),
    "BigQuery": ("bigquery", "big query"),
    "Spark": ("apache spark", "pyspark", "spark"),
    "AWS": ("aws", "amazon web services"),
    "Azure": ("azure",),
    "Google Cloud": ("gcp", "google cloud", "bigquery"),
    "Git": ("git", "github", "version control"),
    "APIs": (" api ", "apis", "rest api", "restful"),
    "Docker": ("docker", "containerization", "containers"),
    "Kubernetes": ("kubernetes", " k8s "),
    "Machine learning": ("machine learning", "ml model", "scikit-learn", "sklearn"),
    "scikit-learn": ("scikit-learn", "sklearn"),
    "TensorFlow": ("tensorflow",),
    "PyTorch": ("pytorch",),
    "Java": ("java",),
    "C++": ("c++", "cpp"),
    "JavaScript": ("javascript",),
    "TypeScript": ("typescript",),
    "React": ("react", "react.js", "reactjs"),
    "Node.js": ("node.js", "nodejs"),
    "FastAPI": ("fastapi",),
    "Communication": ("communication", "communicate", "presentation", "present findings"),
    "Stakeholder management": ("stakeholder", "business partner", "cross-functional"),
    "Problem solving": ("problem solving", "problem-solving", "analytical thinking"),
    "Business intelligence": ("business intelligence", " bi ", "bi reporting"),
}

_TOOL_SKILLS = {
    "SQL", "Python", "Excel", "Power BI", "Tableau", "Pandas", "NumPy", "R",
    "dbt", "Snowflake", "BigQuery", "Spark", "AWS", "Azure", "Google Cloud",
    "Git", "Docker", "Kubernetes", "scikit-learn", "TensorFlow", "PyTorch",
    "Java", "C++", "JavaScript", "TypeScript", "React", "Node.js", "FastAPI",
}


class PublicMarketFallbackUnavailable(RuntimeError):
    pass


def _clean_text(value: Any, limit: int = 12_000) -> str:
    raw = unescape(str(value or ""))
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw[:limit]


def _query_terms(request_data: dict[str, Any]) -> list[str]:
    values = list(request_data.get("target_roles") or []) + list(request_data.get("target_fields") or [])
    seen: set[str] = set()
    terms: list[str] = []
    for value in values:
        for token in re.findall(r"[a-zA-Z][a-zA-Z+#.]{2,}", str(value).lower()):
            normalized = token.strip(".")
            if normalized in _STOPWORDS or normalized in seen:
                continue
            seen.add(normalized)
            terms.append(normalized)
    return terms[:12]


def _role_phrase(request_data: dict[str, Any]) -> str:
    roles = request_data.get("target_roles") or []
    fields = request_data.get("target_fields") or []
    return _clean_text((roles or fields or ["Career"])[0], 160)


def _normalize_remote_ok(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    jobs: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("position"):
            continue
        url = str(item.get("url") or "").strip()
        if not url.startswith("http"):
            continue
        tags = [str(tag) for tag in (item.get("tags") or []) if str(tag).strip()]
        jobs.append({
            "source": "Remote OK",
            "title": _clean_text(item.get("position"), 240),
            "company": _clean_text(item.get("company"), 180),
            "location": _clean_text(item.get("location"), 180),
            "description": _clean_text(item.get("description")),
            "tags": tags[:20],
            "url": url[:2000],
            "date": str(item.get("date") or item.get("epoch") or ""),
        })
    return jobs


def _normalize_arbeitnow(raw: Any) -> list[dict[str, Any]]:
    data = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(data, list):
        return []
    jobs: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        url = str(item.get("url") or "").strip()
        if not url.startswith("http"):
            continue
        tags = [str(tag) for tag in (item.get("tags") or []) if str(tag).strip()]
        jobs.append({
            "source": "Arbeitnow",
            "title": _clean_text(item.get("title"), 240),
            "company": _clean_text(item.get("company_name"), 180),
            "location": _clean_text(item.get("location"), 180),
            "description": _clean_text(item.get("description")),
            "tags": tags[:20],
            "url": url[:2000],
            "date": str(item.get("created_at") or ""),
        })
    return jobs


def _fetch_json(url: str) -> Any:
    response = httpx.get(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "PlaceAI-Career-Roadmap/1.0 (+https://www.placeai.in)",
        },
        timeout=httpx.Timeout(PUBLIC_MARKET_TIMEOUT_SECONDS, connect=4.0),
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.json()


def _fetch_jobs(request_data: dict[str, Any]) -> list[dict[str, Any]]:
    terms = _query_terms(request_data)
    tag = terms[0] if terms else "tech"
    jobs: list[dict[str, Any]] = []
    errors: list[Exception] = []

    try:
        jobs.extend(_normalize_remote_ok(_fetch_json(f"{REMOTE_OK_API}?tag={quote(tag)}")))
    except Exception as exc:
        errors.append(exc)

    try:
        jobs.extend(_normalize_arbeitnow(_fetch_json(ARBEITNOW_API)))
    except Exception as exc:
        errors.append(exc)

    if not jobs:
        raise PublicMarketFallbackUnavailable("No public market feeds were reachable") from (errors[-1] if errors else None)
    return jobs


def _job_score(job: dict[str, Any], request_data: dict[str, Any]) -> int:
    phrase = _role_phrase(request_data).lower()
    terms = _query_terms(request_data)
    title = str(job.get("title") or "").lower()
    searchable = " ".join([
        title,
        str(job.get("location") or "").lower(),
        " ".join(str(tag).lower() for tag in job.get("tags") or []),
        str(job.get("description") or "").lower(),
    ])
    score = 0
    if phrase and phrase in title:
        score += 8
    for term in terms:
        if term in title:
            score += 3
        elif term in searchable:
            score += 1
    region = str(request_data.get("market_region") or "").strip().lower()
    if region and region in searchable:
        score += 2
    return score


def _matched_jobs(request_data: dict[str, Any], jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(
        (( _job_score(job, request_data), job) for job in jobs),
        key=lambda pair: pair[0],
        reverse=True,
    )
    direct = [job for score, job in ranked if score >= 3][:MAX_MATCHED_JOBS]
    if len(direct) >= MIN_MATCHED_JOBS:
        return direct
    broader = [job for score, job in ranked if score >= 1][:MAX_MATCHED_JOBS]
    return broader


def _skill_counts(jobs: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for job in jobs:
        text = " " + " ".join([
            str(job.get("title") or ""),
            str(job.get("description") or ""),
            " ".join(str(tag) for tag in job.get("tags") or []),
        ]).lower() + " "
        for canonical, variants in _SKILL_VARIANTS.items():
            if any(variant in text for variant in variants):
                counts[canonical] += 1
    return counts


def _known_skills(request_data: dict[str, Any]) -> set[str]:
    raw = [str(skill).casefold().replace(" ", "") for skill in request_data.get("current_skills") or []]
    known: set[str] = set(raw)
    for canonical, variants in _SKILL_VARIANTS.items():
        options = [canonical.casefold().replace(" ", "")] + [variant.casefold().replace(" ", "") for variant in variants]
        if any(any(option and option in item for option in options) for item in raw):
            known.add(canonical.casefold().replace(" ", ""))
    return known


def _phase_days(total: int) -> list[int]:
    total = max(42, min(int(total or 90), 365))
    raw = [max(10, round(total * part)) for part in (0.24, 0.24, 0.32)]
    final = max(10, total - sum(raw))
    return [*raw, final]


def _skill_objects(skills: list[str], counts: Counter[str], sampled: int) -> list[dict[str, str]]:
    return [
        {
            "name": skill,
            "level": "working",
            "why": f"Appeared in {counts[skill]} of {sampled} matched current public job listings.",
        }
        for skill in skills
    ]


def _source_rows(jobs: list[dict[str, Any]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for job in jobs:
        url = str(job.get("url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        title = " — ".join(
            part for part in [str(job.get("source") or ""), str(job.get("company") or ""), str(job.get("title") or "")]
            if part
        )
        output.append({"title": title[:300], "url": url[:2000]})
        if len(output) >= 12:
            break
    return output


def build_public_market_roadmap(request_data: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]], str]:
    """Build a cited roadmap from fresh public job feeds when AI research providers are unavailable."""
    jobs = _fetch_jobs(request_data)
    matched = _matched_jobs(request_data, jobs)
    if len(matched) < MIN_MATCHED_JOBS:
        raise PublicMarketFallbackUnavailable("Insufficient role-matched public listings")

    counts = _skill_counts(matched)
    market_skills = [skill for skill, count in counts.most_common(14) if count > 0]
    if len(market_skills) < MIN_MARKET_SKILLS:
        raise PublicMarketFallbackUnavailable("Insufficient current skill signals")

    sources = _source_rows(matched)
    if len(sources) < MIN_MATCHED_JOBS:
        raise PublicMarketFallbackUnavailable("Insufficient verifiable public sources")

    known = _known_skills(request_data)
    gaps = [skill for skill in market_skills if skill.casefold().replace(" ", "") not in known]
    # A valid sample may contain only three to seven distinct skills. Never
    # wait for eight or invent extra signals to fill the plan.
    priority = list(dict.fromkeys([*gaps, *market_skills]))[:8]

    target = _role_phrase(request_data)
    region = _clean_text(request_data.get("market_region"), 120) or "the selected market"
    requested_days = request_data.get("desired_timeline_days") or 90
    days = _phase_days(int(requested_days))
    weekly_hours = max(1, min(int(request_data.get("hours_per_week") or 10), 80))
    learning_style = _clean_text(request_data.get("learning_style"), 300) or "project-first, deliberate practice"
    sampled = len(matched)

    top_signals = [
        f"{skill} appeared in {counts[skill]} of {sampled} matched current public job listings."
        for skill in market_skills[:6]
    ]
    source_mix = Counter(str(job.get("source") or "") for job in matched)
    top_signals.insert(
        0,
        "Fresh public-market sample: "
        + ", ".join(f"{count} matched listings from {source}" for source, count in source_mix.items())
        + ".",
    )

    tools = [skill for skill in market_skills if skill in _TOOL_SKILLS][:12]
    expectations: list[str] = []
    corpus = " ".join(str(job.get("description") or "").lower() for job in matched)
    if "communication" in corpus or "stakeholder" in corpus:
        expectations.append("Communicate findings clearly to technical and non-technical stakeholders.")
    if "experience" in corpus or "years" in corpus:
        expectations.append("Demonstrate applied experience through projects, internships or equivalent work evidence.")
    if "degree" in corpus or "bachelor" in corpus or "university" in corpus:
        expectations.append("Some sampled employers mention formal education; strong project evidence remains useful.")
    if "portfolio" in corpus or "github" in corpus:
        expectations.append("Maintain reviewable project evidence such as repositories, case studies or demos.")
    if not expectations:
        expectations = [
            "Show measurable project outcomes and explain the decisions behind your work.",
            "Be ready to demonstrate the market-priority skills in practical tasks and interviews.",
        ]

    phase_skills = [
        priority[:3],
        priority[3:6] or priority[:3],
        (priority[6:8] + market_skills[:2])[:4],
        market_skills[:4],
    ]
    phases = [
        {
            "phase": 1,
            "name": "Close the highest-priority market gaps",
            "days": days[0],
            "outcomes": [
                f"Reach working proficiency in {', '.join(phase_skills[0])}.",
                "Create small exercises that prove each skill independently.",
            ],
            "skills": _skill_objects(phase_skills[0], counts, sampled),
            "projects": [{
                "title": f"{target} market-skill sprint",
                "scope": "Build small, reviewable exercises around the strongest live-market skill signals before combining them.",
                "deliverables": ["Git repository", "Practice notebooks/scripts", "Short README with lessons learned"],
                "portfolio_proof": "Commit history and working examples showing the newly learned skills.",
            }],
            "practice": [
                "Use focused drills on one skill at a time before combining tools.",
                "Review mistakes weekly and convert repeated errors into a personal checklist.",
            ],
            "milestone": "Complete one independently reproducible exercise for every priority skill in this phase.",
        },
        {
            "phase": 2,
            "name": "Build an end-to-end role workflow",
            "days": days[1],
            "outcomes": [
                f"Combine {', '.join(phase_skills[1])} in one realistic {target} workflow.",
                "Document inputs, transformations, decisions and outputs clearly.",
            ],
            "skills": _skill_objects(phase_skills[1], counts, sampled),
            "projects": [{
                "title": f"End-to-end {target} workflow",
                "scope": "Solve one realistic problem from raw input through analysis/implementation to a decision-ready output.",
                "deliverables": ["Working project", "README", "Reproducible setup", "Results/demo"],
                "portfolio_proof": "A reviewer can reproduce the project and understand why each tool was used.",
            }],
            "practice": [
                "Spend at least half of project time building rather than watching tutorials.",
                "Explain one technical decision aloud after each work session.",
            ],
            "milestone": "Run the project from a clean setup and reproduce the final output without manual fixes.",
        },
        {
            "phase": 3,
            "name": "Create a market-aligned portfolio case study",
            "days": days[2],
            "outcomes": [
                f"Publish a polished case study aligned with current {target} requirements.",
                "Show measurable outcomes, trade-offs and validation rather than only screenshots.",
            ],
            "skills": _skill_objects(phase_skills[2], counts, sampled),
            "projects": [{
                "title": f"{region} {target} portfolio case study",
                "scope": "Choose a domain-relevant public dataset/problem and build a professional case study using the strongest current skill signals.",
                "deliverables": ["Public repository", "Case-study README", "Demo/dashboard/report", "Architecture or workflow diagram"],
                "portfolio_proof": "A recruiter can understand the problem, method, result and your individual contribution in under five minutes.",
            }],
            "practice": [
                "Request peer feedback on clarity and reproducibility.",
                "Refactor the project after feedback and record what changed.",
            ],
            "milestone": "Publish a portfolio-ready case study with a concise problem → approach → result narrative.",
        },
        {
            "phase": 4,
            "name": "Convert skills into interview and application readiness",
            "days": days[3],
            "outcomes": [
                "Explain portfolio decisions concisely under interview conditions.",
                "Practice role-specific technical questions and evidence-based behavioral answers.",
            ],
            "skills": _skill_objects(phase_skills[3], counts, sampled),
            "projects": [{
                "title": f"{target} interview evidence pack",
                "scope": "Turn completed projects into concise interview stories, technical walkthroughs and application-ready evidence.",
                "deliverables": ["Project talking points", "Role-specific question bank", "Updated resume bullets", "Application tracker"],
                "portfolio_proof": "Each claimed skill links to a concrete project artifact or measurable example.",
            }],
            "practice": [
                "Run timed technical drills each week.",
                "Practice a 2-minute and a 5-minute walkthrough for each major project.",
                "Apply selectively and record recurring requirements to inform the next roadmap refresh.",
            ],
            "milestone": "Complete two mock interview rounds and a portfolio/resume review against current role requirements.",
        },
    ]

    payload = {
        "title": f"{target} Career Roadmap — Current Market",
        "market_snapshot": {
            "region": region,
            "target_roles": list(request_data.get("target_roles") or [target]),
            "demand_signals": top_signals,
            "in_demand_skills": market_skills[:12],
            "tools_and_technologies": tools,
            "entry_level_expectations": expectations[:8],
            "market_notes": [
                "This emergency fallback uses fresh public job feeds rather than an AI research provider.",
                f"The requested market is {region}; public feeds may include remote/global listings, so treat the sample as directional rather than a complete regional labour-market census.",
                "Refresh the roadmap periodically because job listings and skill demand change.",
            ],
        },
        "estimated_days": sum(days),
        "weekly_hours": weekly_hours,
        "learning_pattern": {
            "recommended_style": learning_style,
            "weekly_cycle": "Use roughly 35% of weekly time for focused learning, 50% for building, and 15% for review/interview practice.",
            "daily_session": "Start with retrieval practice, do one focused build block, then record what worked, what failed and the next concrete action.",
            "revision_strategy": "Review weak areas weekly, revisit project mistakes, and refresh market signals before starting a new major phase.",
        },
        "phases": phases,
        "advanced_next_steps": [
            f"Deepen {skill} after the core roadmap if it remains common in refreshed market evidence."
            for skill in market_skills[8:12]
        ] or ["Refresh current-market evidence and deepen the strongest recurring specialization signal."],
        "portfolio_plan": [
            "Keep repositories reproducible with setup instructions and meaningful commit history.",
            "Write one concise case study that connects the technical work to a real decision or outcome.",
            "Link every major resume skill claim to a demonstrable project artifact.",
        ],
        "interview_preparation": [
            f"Practice questions that require using or explaining {skill}."
            for skill in market_skills[:5]
        ] + [
            "Prepare structured stories for debugging, trade-offs, teamwork and learning from failure.",
            "Practice explaining one project to both a technical interviewer and a non-technical stakeholder.",
        ],
    }
    return payload, sources, "public_market:remote_feeds_v1"
