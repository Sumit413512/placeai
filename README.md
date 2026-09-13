# PlaceAI Commercial V3.1.4

PlaceAI is a multi-tenant campus placement operating system for institutions, recruiters and students. It connects student records, controlled recruiter access, campus opportunities, placement drives, eligibility, applications, interviews, offers, attendance, reporting and human-reviewed AI assistance in one role-aware platform.

## Production architecture

The production topology is Vercel-primary with a Render fallback:

- **Public product site:** `https://placeai-rxpp.vercel.app/`
- **Authenticated production workspace:** `https://placeai-rxpp.vercel.app/workspace`
- **Backend API runtime:** the same Vercel production origin, served by the FastAPI application.
- **Fallback gateway:** `https://placeai-recovery.onrender.com` remains available as a secondary recovery path; it is not the release authority.
- **Database:** Supabase PostgreSQL in `ap-southeast-1`.
- **Persistence:** production application/file state is durable and database-backed; local development may use SQLite/filesystem fallbacks.
- **Email:** transactional delivery supports Brevo HTTPS API and SMTP. Production password recovery fails closed when no delivery transport is configured.
- **AI:** the live readiness contract is exposed by `/ai/status`; production smoke requires the provider to be configured and its SDK ready.

The public product site and the authenticated workspace deliberately share one origin. This keeps cookies, password recovery and API calls same-origin and removes an unnecessary proxy hop from the primary user path.

## Core workspaces

### Platform Admin

- Create and manage institutions.
- Provision institution/TPO administrators and approved recruiter accounts.
- Review privileged access requests.
- Inspect integration readiness and operational state.
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
- Use AI-assisted resume, readiness and mock-interview functions subject to provider readiness and human review.

## Security model

PlaceAI is designed around backend-enforced role and tenant boundaries. Frontend visibility is never treated as authorization.

Production hardening includes:

- Argon2 password hashing and strong password policy.
- First-login password rotation for provisioned accounts.
- Cryptographically generated one-time temporary provisioning passwords.
- Database-backed refresh sessions with rotation/revocation.
- Password-reset tokens stored as digests and non-enumerating recovery responses.
- Database-backed abuse/rate-limit state.
- Cross-institution reference validation.
- Strict HTTPS/security headers and no wildcard production CORS.
- Bounded/signature-aware upload validation.
- Human-review requirements for AI-assisted decisions.
- No fabricated AI fallback when a provider is unavailable.
- Per-commit release integrity evidence in CI.
- Tracked-secret scanning, Bandit and dependency auditing.

The GitHub repository is private. `CODEOWNERS`, the production PR checklist, `SECURITY.md`, CI/security gates and secret scanning remain part of the release controls.

## Account provisioning

Institution/TPO, student and recruiter provisioning does not require an administrator to invent a compliant temporary password. PlaceAI generates a strong one-time credential using `crypto.getRandomValues`, supports Copy/Regenerate where appropriate, and requires the account holder to establish a permanent password.

Recruiter access requests can be reviewed and provisioned through the Platform Admin workflow. The approved recruiter receives a one-time password setup link at the approved work email. Permanent passwords are not selected by the administrator.

## AI behavior

`/ai/status` exposes only non-secret readiness fields: `configured`, `sdk_available` and `model`. Production smoke requires `configured=true` and `sdk_available=true` before the release is accepted.

AI-assisted output is decision support only. PlaceAI does not invent candidate analysis when a provider is unavailable, and core institution/recruiter/student workflows remain server-authorized independently of model output.

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

Never place real credentials in source control, shared shell history, documentation or public issues.

## Verification and release gates

Run locally:

```bash
pytest -q
python scripts/release_check.py
python scripts/secret_hygiene.py
```

The GitHub release gates are:

1. **PlaceAI CI** — Python compilation, JavaScript syntax checks, browser/regression tests, static analysis, release hygiene and integrity evidence.
2. **PlaceAI Security Audit** — tracked-secret hygiene, Bandit and production dependency audit.
3. **PlaceAI Production Smoke** — exact Vercel production version, public site, same-origin `/workspace`, release assets, legal pages, AI readiness, authorization boundaries and password-reset failure behavior. Render fallback availability is recorded but is non-blocking.

A release is production-ready only after the exact revision is deployed to Vercel and the live production smoke gate passes.

## Database and migrations

Production uses PostgreSQL with reviewed Alembic migrations and `AUTO_CREATE_SCHEMA=false`. The current production Alembic version is `20260911_0008`.

Supabase browser Data API access is not the application authorization layer; PlaceAI connects through the trusted server-side database path.

## Operational notes

The Render recovery service remains in Singapore on its existing free plan and should be treated only as a fallback while its private-repository Git integration is not authorized for new deployments. Do not make the repository public to restore that integration; reconnect Render to the private repository instead if the fallback must be updated.

For commercial institutional traffic, review provider plan/SLA requirements, custom domain/DNS, monitoring and branch-protection policy before promising contractual availability. These commercial infrastructure choices may incur charges and are intentionally not changed automatically.

See `DEPLOYMENT_PREP_STATUS.md` and `docs/PRODUCTION_OPERATIONS.md` for operational procedures.
