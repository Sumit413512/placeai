from pathlib import Path
import hashlib
import json
import re


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    Path(path).write_text(content, encoding="utf-8")


# Runtime shell: retire obsolete demo branches and use real access requests.
p = "app/static/app.js"
s = read(p)
s = s.replace("['login-view','signup-view','demo-view','reset-view']", "['login-view','signup-view','reset-view']")
s = s.replace("view === 'demo' ? 'demo-view' : view === 'reset' ? 'reset-view' : 'login-view'", "view === 'reset' ? 'reset-view' : 'login-view'")
s = s.replace("['Sales','leads','Demo requests']", "['Access','leads','Access requests']")
s = re.sub(r"\n  const demoNotificationsByRole = \{.*?\n  \};\n\n  async function updateNotificationBadge", "\n  async function updateNotificationBadge", s, flags=re.S)
s = s.replace("'Tenant, adoption and sales-pipeline operating metrics.'", "'Tenant and controlled-access operating metrics.'")
s = s.replace("<small>Sales leads</small><strong>${o.demo_requests}</strong><span>Open walkthrough requests</span>", "<small>Access requests</small><strong>${o.access_requests}</strong><span>Privileged workspace requests awaiting review</span>")
s = re.sub(
    r"    \} else if \(view === 'leads'\) \{\n      setPage\('Demo requests','Sales pipeline'\);.*?\n    \}\n  \}\n\n  function inputField",
    "    } else if (view === 'leads') {\n      setPage('Access requests','Platform control'); setContextAction();\n      const rows = await api('/platform/access-requests');\n      $('#app-content').innerHTML = `${pageHead('Access requests','Privileged workspace access requests stored in the production database.')}${rows.length ? `<div class=\"data-panel\"><div class=\"data-toolbar\"><span class=\"table-secondary\">${rows.length} requests</span></div><div class=\"table-wrap\"><table class=\"data-table\"><thead><tr><th>Requester</th><th>Role</th><th>Organization</th><th>Received</th><th>Status</th></tr></thead><tbody>${rows.map(r => `<tr><td><span class=\"table-primary\">${esc(r.full_name)}</span><span class=\"table-secondary\">${esc(r.work_email)}</span></td><td>${esc(r.requested_role.replaceAll('_',' '))}</td><td>${esc(r.organization_name || '—')}</td><td>${fmtDate(r.created_at)}</td><td>${statusBadge(r.status)}</td></tr>`).join('')}</tbody></table></div></div>` : emptyState('AR','No access requests','Privileged workspace requests will appear here when submitted.')}`;\n    }\n  }\n\n  function inputField",
    s,
    flags=re.S,
)
s = s.replace('placeholder="e.g. northstar"', 'placeholder="e.g. campus-main"')
s = re.sub(r"\n      if\(e\.target\.classList\.contains\('lead-status-select'\).*?\n", "\n", s)
s = re.sub(r"      if\(f\.id==='demo-request-form'\)\{.*?\}\n      else if\(f\.id==='login-form'\)", "      if(f.id==='login-form')", s, flags=re.S)
write(p, s)

# Role access overlay no longer needs a compatibility cleanup shim.
p = "app/static/access-portal.js"
s = read(p)
s = s.replace('placeholder="e.g. aarav.shah"', 'placeholder="e.g. student.name"')
s = s.replace("No simulated leads are displayed.", "Only persisted production requests are displayed.")
s = re.sub(r"\n  function removeSimulatedPublicContent\(\) \{.*?\n  \}\n\n  function relabelPlatformNavigation", "\n  function relabelPlatformNavigation", s, flags=re.S)
s = s.replace("    removeSimulatedPublicContent();\n", "")
write(p, s)

# HTML/CSS terminology and compatibility placeholder cleanup.
p = "app/templates/index.html"
s = read(p).replace('class="role-demo"', 'class="role-production"')
s = re.sub(r'\n        <div id="demo-view"[^\n]*</div>', "", s)
write(p, s)

p = "app/static/app.css"
s = read(p).replace(".role-demo", ".role-production")
s = re.sub(r"\.demo-steps\{.*?\.demo-note\{[^}]*\}", "", s, flags=re.S)
s = re.sub(r"/\* PlaceAI v2\.2 targeted UI fixes: resume heading \+ demo notifications \*/\n?", "", s)
s = re.sub(r"\.demo-badge\{[^}]*\}\n?", "", s)
write(p, s)

# Import template contains no invented student row.
p = "app/static/student-import-template.csv"
lines = read(p).splitlines()
write(p, lines[0] + "\n")

# Retire public sales-lead router and app registration.
Path("app/routers/public.py").unlink(missing_ok=True)
p = "app/app.py"
s = read(p).replace('public = _import_router("public")\n', "").replace("    public,\n", "")
write(p, s)

# Platform overview counts real privileged access requests; legacy lead endpoints are removed.
p = "app/routers/platform.py"
s = read(p)
s = s.replace(
    "from app.models import DemoRequest, Job, Organization, OrganizationType, RecruiterProfile, StudentProfile, User, UserRole",
    "from app.models import Job, Organization, OrganizationType, RecruiterProfile, StudentProfile, User, UserRole",
)
s = s.replace(
    "from app.schemas import AdminUserProvision, DemoRequestOut, DemoRequestStatusUpdate, OrganizationCreate, OrganizationOut, PlatformOverviewOut, UserOut",
    "from app.schemas import AdminUserProvision, OrganizationCreate, OrganizationOut, PlatformOverviewOut, UserOut",
)
if "from app.access_models import AccessRequest" not in s:
    s = s.replace("from app.services import record_audit\n", "from app.services import record_audit\nfrom app.access_models import AccessRequest\n")
s = s.replace(
    'demo_requests=db.query(DemoRequest).filter(DemoRequest.status != "lost").count(),',
    'access_requests=db.query(AccessRequest).filter(AccessRequest.status.in_(["new", "under_review", "approved"])).count(),',
)
s = re.sub(r"\n@router\.get\(\"/demo-requests\".*?\n    return lead\n?", "\n", s, flags=re.S)
write(p, s)

# Retire ORM and Pydantic types for the removed lead system.
p = "app/models.py"
s = re.sub(r"\n\nclass DemoRequest\(Base\):.*?(?=\n\nclass AuditEvent\(Base\):)", "", read(p), flags=re.S)
write(p, s)

p = "app/schemas.py"
s = read(p).replace("    demo_requests: int\n", "    access_requests: int\n")
s = re.sub(r"\n\nclass DemoRequestCreate\(BaseModel\):.*?(?=\n\nclass AuditEventOut\(BaseModel\):)", "", s, flags=re.S)
write(p, s)

# Synthetic AI fallbacks are removed; provider failures fail closed.
p = "app/config.py"
s = re.sub(r"^\s*self\.enable_ai_demo_fallback\s*=.*\n", "", read(p), flags=re.M)
write(p, s)

p = "app/routers/ai.py"
s = read(p).replace(
    '"""Call Gemini. Synthetic fallback is available only when explicitly enabled for demos."""',
    '"""Call Gemini and fail closed when the provider is unavailable or unconfigured."""',
)
s = re.sub(r"\n        if settings\.enable_ai_demo_fallback:.*?(?=\n        api_key = )", "", s, flags=re.S)
write(p, s)

# Documentation alignment.
replacements = {
    "README.md": [
        ("Public B2B website and product-demo lead capture.", "Public B2B website and controlled workspace access requests."),
        ("Generate strong JWT secrets even in a shared demo environment.", "Generate strong JWT secrets in every shared environment."),
        ("ENABLE_AI_DEMO_FALLBACK=true` is intended only for controlled local demos.", "Synthetic AI fallback is not supported; configure GEMINI_API_KEY for AI features."),
        ("See `docs/SALES_DEMO.md` for the walkthrough sequence.", "Use the production access flow and role workspaces for product walkthroughs."),
    ],
    "docs/FEATURE_MATRIX.md": [
        ("Demo-request capture feeding the Platform Admin sales-lead pipeline.", "Privileged access-request capture feeding the Platform Admin access-review queue."),
        ("Platform overview and inbound demo-request pipeline.", "Platform overview and privileged access-request queue."),
    ],
    "docs/CLIENT_HANDOFF.md": [
        ("Inbound demo-request sales pipeline.", "Inbound privileged access-request review."),
        ("Demo seed, bootstrap tooling and Postman API collection.", "Bootstrap tooling and Postman API collection."),
        ("Remove demo data and keep `ENABLE_AI_DEMO_FALLBACK=false`.", "Keep production data verified and configure real AI credentials when AI is enabled."),
    ],
    "docs/SECURITY_RELEASE_CHECKLIST.md": [
        ("Keep `ENABLE_AI_DEMO_FALLBACK=false`.", "Synthetic AI fallback is not supported."),
        ("Review all institution/recruiter accounts and remove demo users/data.", "Review all institution/recruiter accounts and remove unauthorized or test users/data."),
    ],
    "docs/DEPLOYMENT.md": [("AI demo fallback disabled", "Synthetic AI fallback removed")],
    "docs/SALES_PLAYBOOK.md": [
        ("## Demo close", "## Walkthrough close"),
        ("Do not end a demo with “what do you think?”.", "Do not end a product walkthrough with “what do you think?”."),
    ],
    "VERCEL_DEPLOYMENT.md": [("`ENABLE_AI_DEMO_FALLBACK=false`", "Synthetic AI fallback is not supported")],
    "RELEASE_NOTES.md": [
        ("public demo requests", "public access requests"),
        ("demo accounts", "legacy test accounts"),
        ("demo Notifications", "temporary Notifications"),
        ("Public demo-request form feeding a platform-admin sales lead pipeline.", "Public privileged-access request flow feeding the platform-admin access queue."),
        ("Demo seed, platform bootstrap, Postman collection, sales/client handoff documentation.", "Platform bootstrap, Postman collection, and sales/client handoff documentation."),
        ("public demo-request capture", "public access-request capture"),
    ],
}
for p, reps in replacements.items():
    if not Path(p).exists():
        continue
    s = read(p)
    for old, new in reps:
        s = s.replace(old, new)
    if p == "README.md":
        s = re.sub(r"\n### 3\. Create demo data.*?(?=\n### |\n## )", "\n", s, flags=re.S)
        s = s.replace("## Clean first-time setup instead of demo seed", "## Clean first-time setup")
    if p == "docs/CLIENT_HANDOFF.md":
        s = re.sub(r"\n## Demo accounts.*?(?=\n## )", "\n", s, flags=re.S)
    write(p, s)

# Clean Postman examples and remove retired endpoints.
p = "PlaceAI_API.postman_collection.json"
data = json.loads(read(p))


def clean_obj(value):
    if isinstance(value, str):
        return (
            value.replace("student_demo", "student_example")
            .replace("recruiter_demo", "recruiter_example")
            .replace("student@demo.com", "student@example.invalid")
            .replace("recruiter@demo.com", "recruiter@example.invalid")
            .replace("Demo Student", "Example Student")
            .replace("demostudent", "examplestudent")
        )
    if isinstance(value, list):
        out = []
        for item in value:
            blob = json.dumps(item, ensure_ascii=False).lower() if isinstance(item, (dict, list)) else str(item).lower()
            if "demo-requests" in blob or "list demo requests" in blob:
                continue
            out.append(clean_obj(item))
        return out
    if isinstance(value, dict):
        return {k: clean_obj(v) for k, v in value.items()}
    return value


write(p, json.dumps(clean_obj(data), ensure_ascii=False, indent=2) + "\n")

# Migration records removal of the empty legacy table.
migration = Path("alembic/versions/20260910_0006_retire_demo_requests.py")
if not migration.exists():
    migration.write_text(
        '''"""Retire the legacy public sales-lead table.\n\nRevision ID: 20260910_0006\nRevises: 20260909_0005\n"""\nfrom alembic import op\nfrom sqlalchemy import inspect\n\nrevision = "20260910_0006"\ndown_revision = "20260909_0005"\nbranch_labels = None\ndepends_on = None\n\ndef upgrade() -> None:\n    if "demo_requests" in inspect(op.get_bind()).get_table_names():\n        op.drop_table("demo_requests")\n\ndef downgrade() -> None:\n    # Intentionally irreversible: the retired table contained no production records.\n    pass\n''',
        encoding="utf-8",
    )

# Rebuild manifest from source. Exclude one-time transformation tooling and the manifest itself.
files = []
for f in Path(".").rglob("*"):
    if not f.is_file():
        continue
    rel = f.as_posix()
    if rel.startswith("./"):
        rel = rel[2:]
    if rel.startswith(".git/"):
        continue
    if rel in {
        "MANIFEST.sha256",
        ".github/workflows/retire-demo-writer.yml",
        "scripts/retire_legacy_demo.py",
    }:
        continue
    files.append(rel)
manifest = []
for rel in sorted(files):
    manifest.append(f"{hashlib.sha256(Path(rel).read_bytes()).hexdigest()}  {rel}")
write("MANIFEST.sha256", "\n".join(manifest) + "\n")

# Active runtime paths must be free of retired markers.
checks = [
    "app/static/app.js",
    "app/static/access-portal.js",
    "app/models.py",
    "app/schemas.py",
    "app/config.py",
    "app/routers/ai.py",
    "app/routers/platform.py",
    "app/templates/index.html",
]
retired = [
    "demoNotificationsByRole",
    "demo-request-form",
    "demo-requests",
    "DemoRequest",
    "ENABLE_AI_DEMO_FALLBACK",
    "demo-view",
    "Northstar Institute",
    "Aarav Shah",
    "Avanta Labs",
]
for file in checks:
    hits = [marker for marker in retired if marker in read(file)]
    if hits:
        raise SystemExit(f"{file} still contains retired markers: {hits}")

print("Legacy demo/synthetic transformation completed.")
