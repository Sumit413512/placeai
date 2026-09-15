# PlaceAI Commercial V3.1.4

PlaceAI is a multi-tenant campus placement operating system for institutions, recruiters and students. It connects student records, controlled recruiter access, campus opportunities, placement drives, eligibility, applications, interviews, offers, attendance, reporting and human-reviewed AI assistance in one role-aware platform.

## Production architecture

The current verified release topology is Vercel-first:

- **Public production application:** `https://www.placeai.in`
- **Release authority:** the `main` branch, Vercel production deployment, and canonical-domain production smoke workflow.
- **Backend API runtime:** Vercel serves the FastAPI API and complete web UI from the same origin.
- **Fallback runtime:** Render may be configured as a recovery target, but it is not the canonical public application.
- **Database:** Supabase PostgreSQL in `ap-southeast-1`.
- **Persistence:** production application/file state is durable and database backed; local development may use SQLite/filesystem fallbacks.
- **Email:** transactional delivery supports Brevo HTTPS API and SMTP transport. Production password recovery fails closed when no delivery transport is configured.

The generated `*.vercel.app` hostname and any Render service URL are operational endpoints, not user-facing canonical URLs.

## Core workspaces

### Platform Admin

- Create and manage institutions.
- Provision institution/TPO administrators.
- Review privileged access requests.
- Inspect production integration readiness and operational telemetry.
- Audit platform-level activity.

### Institution / TPO Admin

- Manage institution-scoped students and recruiters.
- Approve campus jobs and operate placement drives.
- Configure explainable eligibility criteria and multi-stage placement pipelines.
- Schedule interviews, manage attendance, offers, policies, announcements, documents and reports.
- Review recruiter verification evidence and institution activity.

### Recruiter

- Maintain company evidence and verification information.
- Publish authorized opportunities.
- Review actual applicants and move candidates through the hiring pipeline.
- Schedule/interact with interviews and offers subject to institution controls.

### Student

- Maintain placement profile and documents.
- View authorized opportunities and placement drives.
- Check explainable eligibility and submit applications.
- Track application/interview/offer activity.
- Use AI-assisted resume/readiness/mock-interview functions only when the configured provider is available.

## Security model

PlaceAI is designed around backend-enforced role and tenant boundaries. Frontend visibility is not treated as authorization.

Production hardening includes:

- Argon2 password hashing.
- Strong password policy and first-login password rotation for provisioned accounts.
- Cryptographically generated one-time temporary provisioning passwords.
- Database-backed refresh sessions with rotation/revocation.
- Password reset tokens stored as digests and non-enumerating recovery responses.
- Database-backed abuse/rate-limit state.
- Cross-institution reference validation.
- Strict security headers and HTTPS production requirements.
- Bounded/signature-aware upload validation.
- Human-review requirements for AI-assisted decisions.
- No synthetic AI fallback when Gemini is unavailable.
- Per-commit SHA-256 release integrity evidence in CI.
- Tracked-secret scanning, Bandit and dependency auditing in the security workflow.

See `SECURITY.md` for the vulnerability-reporting policy.

## Temporary account provisioning

Institution/TPO and student provisioning no longer requires an administrator to invent a compliant temporary password. PlaceAI generates a strong one-time credential in the browser using `crypto.getRandomValues`, provides Copy/Regenerate controls, and requires the new account to replace it at first sign-in. Approved recruiter requests instead use an idempotent server-side provisioning workflow that emails a one-time password-setup link to the approved work address; the administrator never sees a recruiter credential.

The temporary credential remains present after a failed form submission so validation or unrelated field errors cannot silently turn it into an empty password. Successful account creation closes the provisioning dialog; PlaceAI does not expose the credential again afterward.

## AI / Gemini behavior

Gemini is optional for the core placement system.

Set:

```text
GEMINI_API_KEY=<valid provider key>
```

to enable Gemini-backed features. `/ai/status` exposes only non-secret readiness fields (`configured`, `sdk_available`, `model`).

When Gemini is unconfigured or unavailable:

- PlaceAI does not invent candidate analysis.
- AI buttons/forms are disabled with a clear unavailable state.
- Mock Interview Coach does not start a provider-backed session.
- Core institution, recruiter, student, application, eligibility, interview, offer, attendance, notification and reporting workflows remain available.

## Local development

Create and activate a virtual environment, then install development dependencies:

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

macOS/Linux:

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Copy `.env.example` to `.env` and run:

```bash
uvicorn app.app:app --reload
```

Open `http://localhost:8000`.

## Clean bootstrap

For a new environment, the bootstrap script can create the first platform administrator and an institution/TPO account:

```bash
python scripts/bootstrap.py \
  --platform-email owner@example.com \
  --platform-password 'CHANGE-ME-STRONGLY' \
  --institution 'Your Institution Name' \
  --slug your-institution \
  --admin-email tpo@example.edu \
  --admin-password 'CHANGE-ME-STRONGLY'
```

Never place real credentials in source control, shell history intended for sharing, documentation or public issues.

## Verification

Run locally:

```bash
pytest -q
python scripts/release_check.py
python scripts/secret_hygiene.py
```

The GitHub release gates are:

1. **PlaceAI CI** — Python compilation, JS syntax checks, browser/regression tests, static analysis, release hygiene and integrity evidence.
2. **PlaceAI Security Audit** — tracked-secret hygiene, Bandit and production dependency audit.
3. **PlaceAI Production Smoke** — live Render health, release assets, security headers, auth boundaries, password-reset failure behavior and AI readiness contract.

A release should not be called production-ready until the exact revision is deployed to Render and all three gates are green.

## Database and migrations

Production uses PostgreSQL with reviewed Alembic migrations and `AUTO_CREATE_SCHEMA=false`. The current production Alembic version is `20260911_0008`.

Supabase browser Data API access is not the application authorization layer; PlaceAI connects through the trusted server-side database path.

## Operational notes

The active Render service currently runs one Singapore instance. Recent measurements during release verification were well below its CPU and memory limits and recent log inspection showed no 5xx or 422/502/503 responses in the queried window. The current service is still on Render's free tier; move to a paid production tier before relying on paid-tier availability characteristics or meaningful client traffic.

The GitHub repository is currently public and `main` is currently unprotected. `CODEOWNERS`, a production PR checklist, `SECURITY.md`, CI/security gates and secret scanning are committed as compensating controls, but repository visibility and an enforced GitHub ruleset still require repository-administration changes in GitHub Settings.

See `DEPLOYMENT_PREP_STATUS.md` for the current launch checklist and external owner actions.
