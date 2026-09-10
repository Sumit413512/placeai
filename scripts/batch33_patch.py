from __future__ import annotations

from pathlib import Path
import hashlib
import re

path = Path("app/static/app.js")
text = path.read_text(encoding="utf-8")

text = text.replace("    notificationsRead: false,\n", "", 1)

stale_mark = "      else if(a==='mark-notifications-read'){state.notificationsRead=true;updateNotificationBadge();renderNotifications();toast('Notifications marked as read');}\n"
if stale_mark not in text:
    raise SystemExit("legacy notification mark-all handler not found")
text = text.replace(stale_mark, "", 1)

old_jobs = "      const jobs = await api('/students/jobs');\n"
new_jobs = "      const [jobs,apps] = await Promise.all([api('/students/jobs'),api('/students/applications')]); state.appliedJobIds=new Set(apps.map(a=>a.job_id));\n"
if old_jobs not in text:
    raise SystemExit("student opportunities load anchor missing")
text = text.replace(old_jobs, new_jobs, 1)

old_apply = '<button class="row-button primary" data-action="apply-job" data-id="${j.id}">Apply</button>'
new_apply = '${state.appliedJobIds?.has(j.id)?`<button class="row-button" type="button" disabled>Applied</button>`:`<button class="row-button primary" data-action="apply-job" data-id="${j.id}">Apply</button>`}'
if old_apply not in text:
    raise SystemExit("student apply button anchor missing")
text = text.replace(old_apply, new_apply, 1)

pipeline_pattern = re.compile(r"  async function openPipeline\(id\)\{.*?\n  function openEvaluation", re.S)
if not pipeline_pattern.search(text):
    raise SystemExit("openPipeline function anchor missing")
pipeline_replacement = '''  async function openPipeline(id){
    const stages=await api(`/enterprise/drives/${id}/pipeline`);
    const canEdit=state.me?.role==='institution_admin';
    const stageList=stages.length
      ? `<div class="pipeline-stage-list">${stages.map((s,i)=>`<div class="pipeline-stage"><span>${String(i+1).padStart(2,'0')}</span><div><strong>${esc(s.name)}</strong><small>${esc(s.stage_type)}</small></div>${s.is_terminal?'<b>Final</b>':''}</div>`).join('')}</div>`
      : emptyState('PL','No pipeline stages','The placement office has not configured stages for this drive yet.');
    const controls=canEdit
      ? `<form id="pipeline-stage-form" class="form-stack"><input type="hidden" name="drive_id" value="${id}"><div class="form-two"><label>New stage name<input name="name" required></label><label>Stage type<select name="stage_type"><option value="screening">Screening</option><option value="assessment">Assessment</option><option value="interview">Interview</option><option value="offer">Offer</option><option value="custom">Custom</option></select></label></div><button class="button button-secondary button-full">Add stage</button></form>`
      : `<div class="note-box"><strong>Institution-controlled pipeline</strong><p>Pipeline structure is controlled by the institution placement office. Recruiters can review stages and move authorized applicants, but cannot alter the institution-owned stage design.</p></div>`;
    openModal(`<span class="section-kicker">Drive pipeline</span><h2>Screening & interview stages</h2>${stageList}${controls}`);
  }
  function openEvaluation'''
text = pipeline_pattern.sub(pipeline_replacement, text, count=1)

old_recruiter_pipeline = "pageHead('Advanced placement pipelines','Every campus drive can use its own ordered screening and interview stages.')"
new_recruiter_pipeline = "pageHead('Advanced placement pipelines','Review institution-defined screening and interview stages. Structural changes are placement-office controlled.')"
if old_recruiter_pipeline not in text:
    raise SystemExit("recruiter pipeline copy anchor missing")
text = text.replace(old_recruiter_pipeline, new_recruiter_pipeline, 1)

pref_pattern = re.compile(r"  async function openNotificationPreferences\(\)\{.*?\}\n\n  async function downloadAuthorized", re.S)
if not pref_pattern.search(text):
    raise SystemExit("notification preferences function anchor missing")
pref_replacement = '''  async function openNotificationPreferences(){const p=await api('/enterprise/notification-preferences');openModal(`<span class="section-kicker">Notifications</span><h2>Notification preferences</h2><form id="notification-preferences-form" class="form-stack"><label class="toggle-row"><span><strong>In-app notifications</strong><small>Placement events inside PlaceAI</small></span><input type="checkbox" name="in_app" ${p.in_app?'checked':''}></label><div class="note-box"><strong>External delivery</strong><p>External notification channels are not exposed until a production delivery provider is configured for workspace events.</p></div><button class="button button-primary button-full">Save preferences</button></form>`);}

  async function downloadAuthorized'''
text = pref_pattern.sub(pref_replacement, text, count=1)

path.write_text(text, encoding="utf-8")

manifest = Path("MANIFEST.sha256")
rows: list[tuple[str, str]] = []
seen: set[str] = set()
for raw in manifest.read_text(encoding="utf-8").splitlines():
    if not raw.strip():
        continue
    _digest, file_name = raw.split(maxsplit=1)
    file_name = file_name.strip()
    file_path = Path(file_name)
    if not file_path.is_file():
        raise SystemExit(f"Manifest path missing: {file_name}")
    rows.append((file_name, hashlib.sha256(file_path.read_bytes()).hexdigest()))
    seen.add(file_name)
extra = "tests/test_frontend_permission_consistency.py"
if extra not in seen:
    rows.append((extra, hashlib.sha256(Path(extra).read_bytes()).hexdigest()))
manifest.write_text("".join(f"{digest}  {file_name}\n" for file_name, digest in rows), encoding="utf-8")
