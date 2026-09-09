# PlaceAI Commercial V3.1.3 — Production-Hardened Placement Operations

PlaceAI is an AI-assisted, multi-tenant campus placement operating system for institutions, recruiters and students. V3.1.3 retains the complete V3.1 enterprise feature set and adds production-grade session rotation/revocation, durable database-backed file persistence for serverless deployments, cross-tenant reference hardening, request throttling, stronger password policy, upload signature validation and expanded regression coverage.

## V3.1 enterprise capabilities

- **Company Verification Centre:** company identity evidence, CIN/GSTIN format validation, official domain/website, LinkedIn presence, recruiter identity/designation, institution verification, authorization-letter evidence, college relationships, placement history, complaint signals, job consistency and suspicious-domain flags. Results are presented as evidence-based statuses (`Verified`, `Partially Verified`, `Manual Review Required`, `High Risk`) plus confidence, never as a legal certification.
- **Advanced drive pipelines:** configurable ordered stages per drive, including registration, eligibility screening, assessments, technical/HR rounds, offer and joined outcomes.
- **Interview & assessment operations:** scheduling, rescheduling, online/offline mode, venue/meeting link, interviewer, student slot, instructions, attendance, result and structured human evaluation.
- **Real notification centre:** persistent database notifications, unread/read state, priority, category, timestamps, deep-link context, mark-all-read and user preferences.
- **Placement Readiness Score:** evidence-based profile, resume, skills, role alignment, interview readiness, academic eligibility and project evidence components with recommended actions. It is not an employment prediction.
- **Role-aware AI Placement Assistant:** student, recruiter and TPO questions are answered only from data the signed-in user is authorized to access. Gemini remains optional/configurable.
- **Advanced eligibility:** CGPA, school/diploma percentages, backlogs, academic gaps, year, degree/department, skills, certifications, documents, work authorization, placement status and custom rules with explainable eligibility reasons.
- **Placement Policy Engine:** institution-controlled offer limits, placed-student restrictions, salary-improvement rules, internship exceptions and dream-company exceptions.
- **Offer management:** CTC breakdown, joining date, bond terms, internship stipend, PPO status, offer lifecycle and controlled offer-letter PDF upload/download.
- **Student document vault:** controlled student/institution access for placement documents with verification-ready metadata.
- **QR attendance:** placement-drive, assessment, interview, workshop and pre-placement-talk check-in sessions.
- **Interview evaluation:** human-scored technical knowledge, communication, problem solving, role fit, recommendation and notes kept separate from AI scoring.
- **Attention Centre:** actionable queues such as incomplete profiles, missing resumes, eligible non-applicants, missed activity and students without interview activity—without predictive-failure claims.
- **Placement Analytics 2.0:** placement rate, CTC statistics, offers, unique placements, department outcomes, company participation, acceptance/conversion, drive conversion, monthly trend, internship/PPO conversion, unplaced segmentation and recruiter-authorized skill/campus intelligence.
- **Professional UI upgrade:** larger readable typography, neutral enterprise palette, consistent line icons, cleaner sidebar, denser-but-readable tables, responsive states, mature status treatments and professional empty states.
- **Ctrl/Cmd + K command search:** role-scoped navigation across authorized placement records.
- **Announcement Centre:** TPO announcements by audience and priority.
- **Recruiter communication hub:** auditable recruiter/TPO threads with messages and controlled document attachments.
- **Confidential incident reporting:** student reports for suspicious recruiter/job behavior with placement-office resolution workflow.
- **Institution reports:** Placement, Department Placement, Company Participation, Unplaced Student, Offer Register, Internship and Recruiter Activity reports with PDF/XLSX/CSV exports.
- **Custom institution fields:** TPO-configured student data fields without schema changes for each college.
- **Unified placement calendar:** deadlines, drives, interviews, announcements and joining dates.
- **Student profile approval:** institution-controlled approval of sensitive academic/profile changes.

## Existing commercial foundation retained

- Public B2B website and controlled workspace access requests.
- Student, Recruiter, Institution/TPO and Platform Admin workspaces.
- Institution multi-tenancy and cross-campus data isolation.
- Controlled recruiter provisioning and institution linkage.
- Public/campus job posting and campus-job approval.
- Student applications, resume handling, AI resume parsing/matching/skill-gap/mock-interview capabilities.
- Bulk CSV student onboarding/export, tenant audit trail and sales-lead pipeline.
- Argon2 password hashing, JWT access/refresh workflow, HttpOnly refresh cookie, hashed password-reset tokens, security headers and strict script CSP.
- PostgreSQL/Docker production path plus SQLite local development, Alembic migrations, automated tests and release-safety checks.

## Local development

### 1. Create an environment

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

macOS / Linux:

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt
```

### 2. Configure

Copy `.env.example` to `.env`. For local SQLite, the defaults are enough. Generate strong JWT secrets in every shared environment.


### 4. Run

```bash
uvicorn app.app:app --reload
```

Open `http://localhost:8000`.

## Clean first-time setup

Use the bootstrap script to create the first platform administrator and institution administrator:

```bash
python scripts/bootstrap.py \
  --platform-email owner@example.com \
  --platform-password 'CHANGE-ME-STRONGLY' \
  --institution 'Your Institution Name' \
  --slug your-institution \
  --admin-email tpo@example.edu \
  --admin-password 'CHANGE-ME-STRONGLY'
```

The institution administrator can then provision verified recruiters and students from the UI, or import up to 1,000 students per UTF-8 CSV using the built-in template.

## Automated verification

```bash
pytest
python scripts/release_check.py
```

The release checker intentionally fails if a database, `.env`, résumé, virtual environment, cache, log, or Git directory has been packaged.

## Docker + PostgreSQL

Create `.env` from `.env.example`, set at minimum:

- `POSTGRES_PASSWORD`
- `JWT_SECRET_KEY`
- `JWT_REFRESH_SECRET_KEY`
- `BASE_URL`
- `ALLOWED_ORIGINS`

Then:

```bash
docker compose up --build
```

The web container runs `alembic upgrade head` before starting Uvicorn. Production disables automatic schema creation.

## AI configuration

Set `GEMINI_API_KEY` to enable Gemini functionality. If AI is not configured or unavailable, production returns an explicit service-unavailable response. Synthetic candidate analysis is **not** silently substituted.

`Synthetic AI fallback is not supported; configure GEMINI_API_KEY for AI features.

## Password reset email

Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` and `SMTP_FROM`. Password reset responses are non-enumerating and reset tokens are stored only as SHA-256 digests.

## Commercial positioning

Primary initial buyer: college/university placement offices and training institutes that currently run placements through spreadsheets, messages, manually shared résumés and disconnected recruiter workflows.

Recommended sales message:

> Replace fragmented placement operations with one institution-controlled workflow for student readiness, recruiter access, campus drives, applications and outcomes.

Use the production access flow and role workspaces for product walkthroughs.

## Public repository and deployment topology

- **GitHub repository:** `https://github.com/Sumit413512/placeai` — canonical public source.
- **GitHub Pages:** `https://sumit413512.github.io/placeai/` — static public product/technical landing page. GitHub Pages cannot execute the FastAPI backend.
- **Vercel:** production FastAPI application/runtime. The production URL is documented after the Vercel project is imported and verified.
- **Supabase:** managed PostgreSQL persistence. PlaceAI connects through a trusted server-side PostgreSQL connection; browser clients do not access placement tables directly through the Supabase Data API.

## Important production work before a large enterprise rollout

V3.1.3 is suitable for pilots and controlled client deployments after environment-specific security review. Durable serverless file persistence and database-backed abuse throttling are included. For large enterprise/SOC2-scale deployments, add dedicated object storage/CDN if file volume grows materially, centralized immutable audit export, SSO/SAML, MFA, email verification, background queues, malware scanning, observability/APM, tested backup/restore automation and jurisdiction-specific privacy/compliance processes.
