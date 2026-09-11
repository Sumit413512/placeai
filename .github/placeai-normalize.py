from __future__ import annotations

from pathlib import Path
import re


def replace_once(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    return updated


def extract_once(text: str, pattern: str, label: str) -> str:
    match = re.search(pattern, text, flags=re.S)
    if not match:
        raise SystemExit(f"{label}: source block not found")
    return match.group(0)


hardening_path = Path("app/routers/hardening.py")
if not hardening_path.exists():
    raise SystemExit("hardening.py is required as the verified source of hardened route logic")
hardening = hardening_path.read_text(encoding="utf-8")

# Institution dashboard: copy the already-tested hardened implementation into
# the canonical institutions router, changing only route prefix and function name.
dashboard = extract_once(
    hardening,
    r'@router\.get\("/institutions/dashboard", response_model=InstitutionDashboardOut\).*?(?=\n\n@router\.patch\("/institutions/jobs/\{job_id\}/approval")',
    "hardened institution dashboard",
)
dashboard = dashboard.replace(
    '@router.get("/institutions/dashboard", response_model=InstitutionDashboardOut)',
    '@router.get("/dashboard", response_model=InstitutionDashboardOut)',
    1,
).replace("def hardened_institution_dashboard(", "def dashboard(", 1)

approval = extract_once(
    hardening,
    r'@router\.patch\("/institutions/jobs/\{job_id\}/approval", response_model=JobOut\).*?(?=\n\n@router\.post\()',
    "hardened institution approval",
)
approval = approval.replace(
    '@router.patch("/institutions/jobs/{job_id}/approval", response_model=JobOut)',
    '@router.patch("/jobs/{job_id}/approval", response_model=JobOut)',
    1,
).replace("def hardened_approve_job(", "def approve_job(", 1)

institutions_path = Path("app/routers/institutions.py")
institutions = institutions_path.read_text(encoding="utf-8")
institutions = replace_once(
    institutions,
    r'@router\.get\("/dashboard", response_model=InstitutionDashboardOut\).*?(?=\n\n@router\.get\("/students")',
    dashboard,
    "canonical institution dashboard",
)
institutions = replace_once(
    institutions,
    r'@router\.patch\("/jobs/\{job_id\}/approval", response_model=JobOut\).*?(?=\n\n@router\.get\("/drives")',
    approval,
    "canonical institution approval",
)
institutions_path.write_text(institutions, encoding="utf-8")

# Candidate ranking: use the tested hardened implementation as the canonical
# /ai route, preserving validation/clamping and bounded reasoning.
helpers = extract_once(
    hardening,
    r'MAX_AI_REASONING_CHARS = 2000.*?(?=\n\n@router\.get\("/institutions/dashboard")',
    "AI ranking helpers",
)
ranking = extract_once(
    hardening,
    r'@router\.post\(\n    "/ai/rank-candidates/\{job_id\}".*\Z',
    "hardened AI ranking",
)
ranking = ranking.replace('"/ai/rank-candidates/{job_id}"', '"/rank-candidates/{job_id}"', 1)
ranking = ranking.replace("def hardened_rank_candidates(", "def rank_candidates(", 1)

ai_path = Path("app/routers/ai.py")
ai = ai_path.read_text(encoding="utf-8")
if "import math\n" not in ai:
    ai = ai.replace("import json\n", "import json\nimport math\n", 1)
if "MAX_AI_REASONING_CHARS = 2000" not in ai:
    anchor = "\n\ndef _student_job_or_404"
    if anchor not in ai:
        raise SystemExit("AI helper insertion anchor not found")
    ai = ai.replace(anchor, "\n\n" + helpers + anchor, 1)
ai = replace_once(
    ai,
    r'# ─+\n# 2\. Candidate Ranking \(Recruiter\)\n# ─+\n.*?(?=# ─+\n# 3\. Job Matching for Student)',
    ranking + "\n\n",
    "canonical AI ranking",
)
ai = replace_once(
    ai,
    r'# ─+\n# 6\. AI Mock Interview Prep\n# ─+\n.*?(?=# ─+\n# 9\. Role-aware Placement Assistant)',
    "",
    "retired AI interview definitions",
)
ai_path.write_text(ai, encoding="utf-8")

# Remove runtime route surgery and the now-redundant hardening router.
app_path = Path("app/app.py")
app = app_path.read_text(encoding="utf-8")
if 'hardening = _import_router("hardening")\n' not in app:
    raise SystemExit("hardening router import not found")
app = app.replace('hardening = _import_router("hardening")\n', "", 1)
app = replace_once(
    app,
    r'\nif ai is not None:\n.*?(?=\nif enterprise is not None:)',
    "\n",
    "AI/institution bootstrap shadow filters",
)
if "    hardening,\n" not in app:
    raise SystemExit("hardening router tuple entry not found")
app = app.replace("    hardening,\n", "", 1)
app_path.write_text(app, encoding="utf-8")
hardening_path.unlink()

Path("tests/test_router_ownership.py").write_text(
    '''from pathlib import Path\n\nfrom app.app import app\n\n\ndef test_canonical_router_ownership_has_no_bootstrap_shadow_filters():\n    source = Path("app/app.py").read_text()\n    assert "_RETIRED_AI_PATHS" not in source\n    assert "_HARDENED_INSTITUTION_PATHS" not in source\n    assert 'hardening = _import_router("hardening")' not in source\n    assert not Path("app/routers/hardening.py").exists()\n\n\ndef test_canonical_routes_keep_hardened_and_compatibility_owners():\n    schema = app.openapi()["paths"]\n    assert "rank_candidates" in schema["/ai/rank-candidates/{job_id}"]["post"]["operationId"]\n    assert "dashboard" in schema["/institutions/dashboard"]["get"]["operationId"]\n    assert "approve_job" in schema["/institutions/jobs/{job_id}/approval"]["patch"]["operationId"]\n    assert schema["/ai/interview/questions"]["post"]["deprecated"] is True\n    assert schema["/ai/interview/evaluate"]["post"]["deprecated"] is True\n    assert "completed_interview_history" in schema["/ai/interviews"]["get"]["operationId"]\n''',
    encoding="utf-8",
)
