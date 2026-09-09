from pathlib import Path
import hashlib
import json
import re
import subprocess


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


# 1) Remove the development demo seeder entirely.
Path("scripts/seed_demo.py").unlink(missing_ok=True)

# 2) Replace demo-specific sales instructions with a production walkthrough guide.
Path("docs/SALES_DEMO.md").unlink(missing_ok=True)
walkthrough = Path("docs/PRODUCT_WALKTHROUGH.md")
walkthrough.write_text(
    """# PlaceAI Product Walkthrough\n\n"
    "Use a real provisioned pilot tenant or a dedicated non-production test tenant. Do not seed fictional people, companies, placement outcomes, scores or notifications into a client-facing environment.\n\n"
    "## Institution / TPO workspace\n\n"
    "Show the authenticated institution workspace using records owned by that tenant: student administration, recruiter provisioning, campus-job approval, drive eligibility, applications, attendance, reports and audit history. If a dataset is empty, leave the empty state visible rather than manufacturing activity.\n\n"
    "## Student workspace\n\n"
    "Use an authorized test student created for the walkthrough. Show profile completion, opportunities, placement drives, applications, resume handling and interview preparation. Remove the test account and its generated data after the walkthrough.\n\n"
    "## Recruiter workspace\n\n"
    "Use an authorized test recruiter attached to the pilot institution. Show job creation, applicant access boundaries, pipeline stages, interviews, offers and company verification. Never populate fictional candidate identities or scores for presentation purposes.\n\n"
    "## Platform administration\n\n"
    "Show institution provisioning and privileged access requests only with approved operator credentials. Platform Admin access is never public self-service.\n\n"
    "## Close\n\n"
    "Agree the next production step: pilot scope, owner, data-import method, access roles, security review and measurable rollout criteria.\n"
    """,
    encoding="utf-8",
)

# 3) Remove demo/fallback language from README and sales playbook.
p = "README.md"
text = read(p)
text = text.replace("- Public B2B website and product-demo lead capture.\n", "- Public B2B website with controlled role-based access requests.\n")
text = text.replace("- Bulk CSV student onboarding/export, tenant audit trail and sales-lead pipeline.\n", "- Bulk CSV student onboarding/export, tenant audit trail and privileged-access review pipeline.\n")
text = text.replace("Generate strong JWT secrets even in a shared demo environment.", "Generate strong JWT secrets for every shared development or test environment.")
text = re.sub(r"\n### 3\. Create demo data\n.*?(?=\n### 4\. Run)", "", text, count=1, flags=re.S)
text = text.replace("### 4. Run", "### 3. Run")
text = text.replace("## Clean first-time setup instead of demo seed", "## First-time setup")
text = text.replace("\n`ENABLE_AI_DEMO_FALLBACK=true` is intended only for controlled local demos.\n", "\n")
text = text.replace("See `docs/SALES_DEMO.md` for the walkthrough sequence.", "See `docs/PRODUCT_WALKTHROUGH.md` for the production-safe walkthrough sequence.")
write(p, text)

p = "docs/SALES_PLAYBOOK.md"
text = read(p).replace("## Demo close", "## Walkthrough close").replace("Do not end a demo with", "Do not end a walkthrough with")
write(p, text)

# 4) Remove the synthetic AI fallback configuration and implementation.
p = ".env.example"
text = read(p).replace("ENABLE_AI_DEMO_FALLBACK=false\n", "")
write(p, text)

p = "app/config.py"
text = read(p).replace('        self.enable_ai_demo_fallback = os.getenv("ENABLE_AI_DEMO_FALLBACK", "false").lower() == "true"\n', "")
write(p, text)

p = "app/routers/ai.py"
text = read(p)
old_start = 'def call_gemini(client, prompt: str) -> str:\n    """Call Gemini. Synthetic fallback is available only when explicitly enabled for demos."""\n'
if old_start not in text:
    raise SystemExit("AI fallback function signature not found")
start = text.index(old_start)
end = text.index("\n\ndef extract_json_from_response", start)
new_call = '''def call_gemini(client, prompt: str) -> str:
    """Call Gemini and fail explicitly when the configured AI service is unavailable."""
    try:
        if client is None:
            raise RuntimeError("AI service is not configured")
        response = client.models.generate_content(model=settings.gemini_model, contents=prompt)
        if not getattr(response, "text", None):
            raise RuntimeError("AI service returned an empty response")
        return response.text
    except Exception as exc:
        api_key = os.getenv("GEMINI_API_KEY", settings.gemini_api_key).strip()
        if not api_key or api_key.startswith("your-") or api_key == "your-gemini-api-key-here":
            detail = "Gemini is not configured. Add GEMINI_API_KEY to the environment, restart the service, and try again."
        elif genai is None:
            detail = "Google GenAI SDK is not installed. Install the production requirements and redeploy."
        else:
            detail = f"Gemini request failed using {settings.gemini_model}. Verify model access, quota, billing/rate limits, and provider availability."
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail) from exc
'''
text = text[:start] + new_call + text[end:]
write(p, text)

# 5) Remove fictional metrics/companies from the static GitHub Pages landing page.
p = "index.html"
html = read(p)
preview_start = html.find('    <div class="product-preview" aria-label="PlaceAI placement command centre preview">')
if preview_start == -1:
    raise SystemExit("GitHub Pages product preview not found")
preview_end = html.find("\n    </div>\n  </section>", preview_start)
if preview_end == -1:
    raise SystemExit("GitHub Pages preview end not found")
preview_end += len("\n    </div>")
replacement = '''    <div class="product-preview" aria-label="PlaceAI production workspace model">
      <div class="window"><div class="window-bar"><span class="dots"><i></i><i></i><i></i></span><span>Authenticated placement workspace</span><b>PRODUCTION DATA</b></div><div class="preview-body"><div class="preview-main"><div class="preview-title"><small>Role-scoped access</small><strong>Real records only</strong></div><div class="metric-grid"><div class="metric"><small>Students</small><strong>Live</strong><span>tenant records</span></div><div class="metric"><small>Drives</small><strong>Live</strong><span>institution activity</span></div><div class="metric"><small>Offers</small><strong>Live</strong><span>recorded outcomes</span></div><div class="metric"><small>Analytics</small><strong>Live</strong><span>computed from stored data</span></div></div><div class="preview-card"><header><strong>No sample placement activity</strong><span>Empty production datasets remain empty until authorized users create records.</span></header></div></div></div></div>
    </div>'''
html = html[:preview_start] + replacement + html[preview_end:]
html = html.replace("<li>Product walkthrough requests</li>", "<li>Privileged access requests</li>")
html = html.replace("<span>Demo request pipeline</span>", "<span>Access request pipeline</span>")
write(p, html)

# 6) Retire stale demo wording in source-facing docs where it describes current behavior.
for path in ["docs/CLIENT_HANDOFF.md", "docs/FEATURE_MATRIX.md", "docs/ARCHITECTURE.md"]:
    pth = Path(path)
    if not pth.exists():
        continue
    text = pth.read_text(encoding="utf-8")
    text = text.replace("demo request", "access request").replace("Demo request", "Access request")
    text = text.replace("demo-request", "access-request").replace("Demo tenant", "Test tenant")
    pth.write_text(text, encoding="utf-8")

# 7) Remove temporary cleanup files before the final commit.
Path("scripts/retire_remaining_demo.py").unlink(missing_ok=True)
Path(".github/workflows/run-remaining-cleanup.yml").unlink(missing_ok=True)

# 8) Rebuild MANIFEST from the complete tracked release tree, fixing prior omissions.
tracked = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
paths = []
for path in tracked:
    if path == "MANIFEST.sha256":
        continue
    if Path(path).is_file():
        paths.append(path)
if walkthrough.is_file() and str(walkthrough) not in paths:
    paths.append(str(walkthrough))
paths = sorted(dict.fromkeys(paths))
manifest_lines = []
for path in paths:
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    manifest_lines.append(f"{digest}  {path}")
Path("MANIFEST.sha256").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

# 9) Assert current production/source surfaces do not retain demo or simulated mechanisms.
production_paths = [
    ".env.example",
    "README.md",
    "app/config.py",
    "app/routers/ai.py",
    "app/static/app.js",
    "app/static/access-portal.js",
    "app/templates/index.html",
    "index.html",
    "docs/PRODUCT_WALKTHROUGH.md",
    "docs/SALES_PLAYBOOK.md",
]
joined = "\n".join(Path(x).read_text(encoding="utf-8") for x in production_paths if Path(x).exists())
banned = [
    "ENABLE_AI_DEMO_FALLBACK",
    "enable_ai_demo_fallback",
    "seed_demo.py",
    "SALES_DEMO.md",
    "Demo request pipeline",
    "product-demo lead capture",
    "Northstar Institute",
    "Acme Technologies",
    "Aarav Shah",
    "Riya Mehta",
    "Vihaan Kumar",
    "Nisha Singh",
    "Avanta Labs",
    "Nexora Systems",
    "Quantforge",
]
leftovers = [x for x in banned if x in joined]
if leftovers:
    raise SystemExit(f"remaining current-source demo markers: {leftovers}")
