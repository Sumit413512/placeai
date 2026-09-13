# PlaceAI release readiness — 12 September 2026

Baseline: PlaceAI Commercial V3.1.3 with final production hardening and verified hybrid-production release controls.

## Release architecture

- **User-facing production:** `https://placeai-recovery.onrender.com`
- **Render role:** authoritative public release gateway and public-shell release-smoke target.
- **Backend runtime:** `https://placeai-rxpp.vercel.app` serves the FastAPI backend upstream used by the Render gateway.
- **Vercel release control:** the hardened backend was deliberately deployed, verified directly, and automatic Vercel Git deployment was then refrozen with `deploymentEnabled` set to `false`.
- **Database:** Supabase PostgreSQL project `cnpsvfpcxbrygynihlxs` in `ap-southeast-1`.
- **Schema:** Alembic production head is `20260911_0008`.
- **Transactional email:** live backend health reports the delivery transport operational.
- **AI provider:** live `/ai/status` reports the provider configured and SDK available contract is healthy; the endpoint exposes only the privacy-safe fields `configured`, `sdk_available`, and `model`.

## Verified release controls

- Production startup fails closed for invalid database/JWT/CORS/HTTPS/schema/reset-token-debug configuration.
- Role and tenant authorization are enforced by backend dependencies rather than frontend visibility alone.
- Campus opportunity visibility is centralized and prevents unverified students, draft drives, inactive/expired jobs, and cross-institution records from leaking through hardened job, drive, search, calendar and pipeline surfaces.
- Recruiter mock-interview history is scoped so one employer cannot read another employer's coaching/interview data.
- Institution application feeds are scoped by the student's institution, including public-job applications.
- Refresh sessions are database-backed, rotated and revocable; password changes/reset invalidate older authentication state.
- Password rotation is atomic and serializes concurrent password-change attempts for one account.
- Password recovery uses one-time server-side token state and does not enumerate accounts.
- Provisioned accounts require first-login permanent-password rotation.
- TPO/student/recruiter temporary provisioning passwords are cryptographically generated in-browser, policy compliant, read-only, copyable/regeneratable, and preserved across failed submits.
- The obsolete capture-phase temporary-password clearing behavior has been removed from the account-security layer.
- Frontend/API validation contracts are regression tested.
- File uploads use bounded/signature-aware validation; production file persistence is durable and database backed.
- Security headers include HSTS, CSP, frame denial, nosniff, strict referrer policy and restricted browser permissions.
- Database `DataError`, integrity conflicts and production SQLAlchemy failures return controlled 422/409/503 contracts rather than leaking internal errors.
- AI output is never fabricated when provider readiness is unavailable; core placement workflows remain independent of AI availability.
- CI generates a per-commit SHA-256 integrity artifact.
- Security CI runs tracked-secret hygiene, Bandit and production dependency auditing.
- CODEOWNERS, security policy and a production PR checklist are committed.
- Production smoke now validates both layers independently: the Render public gateway and the frozen Vercel backend.
- Direct Vercel smoke validates backend health, DB/configuration/email readiness, security headers, AI readiness, `/auth/me`, hardened `/jobs`, `/enterprise/drives`, and `/institutions/dashboard` unauthenticated boundaries.

## Infrastructure verification

- **GitHub repository visibility:** private.
- **Vercel hardened deployment:** successful for controlled release commit `0e1a41aaf368825bb08bcdf1d985431430bfeac8`.
- **Vercel automatic deployment freeze:** restored on `main`; subsequent control commits produced no Vercel deployment status, consistent with the freeze.
- **Supabase security advisor:** zero current security lints.
- **Supabase schema:** production `alembic_version` is `20260911_0008`.
- **Direct Vercel health:** `status=healthy`, `database=ok`, `configuration=ok`, `transactional_email=ok`, version `3.1.3`.
- **Direct Vercel AI readiness:** configured successfully with the privacy-safe status contract.
- **Render gateway health:** `status=healthy`, `gateway=ok`, `upstream=healthy`, `database=ok`, `configuration=ok`, `transactional_email=ok`.
- **Recent Render application error-log inspection:** no error-level application logs returned in the fresh query window.
- Supabase performance advisor findings remain informational unused-index notices; indexes are intentionally retained until production workload evidence justifies removal.

## Remaining owner/billing actions for larger commercial rollout

These are infrastructure/governance upgrades, not unresolved PlaceAI application defects:

1. **Protected `main` on a private repository:** the current GitHub plan rejects repository rulesets for this private repository with an explicit requirement to upgrade to GitHub Pro or make the repository public. PlaceAI remains private; do not weaken repository privacy to obtain free rulesets. Upgrade the GitHub plan if protected-branch/ruleset enforcement is required.
2. **Render paid availability:** the active public gateway remains on the free Render tier. Upgrade before relying on paid-production availability characteristics or materially higher institutional traffic. This is a billing action and requires account-owner approval.
3. **Custom production domain:** replace temporary platform URLs with the final PlaceAI domain when available, then update `PUBLIC_APP_URL`, CORS, password-reset links, sitemap and associated provider settings.

## Release decision

**GO for the current PlaceAI launch on the verified hybrid architecture.**

The release is considered valid only while the exact `main` revision has green PlaceAI CI, PlaceAI Security Audit and PlaceAI Production Smoke results, Supabase security remains clean, and the production smoke confirms both the Render gateway and frozen Vercel backend remain healthy. Paid plan upgrades and the final custom domain are separate commercial infrastructure decisions and are not silently changed by release automation.
