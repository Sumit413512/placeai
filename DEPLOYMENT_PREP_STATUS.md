# PlaceAI release readiness — 17 September 2026

Baseline: PlaceAI Commercial V3.1.4 with Vercel-first production, canonical custom-domain smoke checks, Supabase persistence, and controlled release promotion.

## Release architecture

- **Canonical public production:** `https://www.placeai.in`
- **Canonical backend/origin:** `https://placeai-rxpp.vercel.app`
- **Vercel role:** serves the FastAPI API and complete web UI used by the custom production domain.
- **Render role:** recovery/fallback only. Render URLs are not canonical user-facing production URLs and must not be advertised as the primary PlaceAI application.
- **Release authority:** the verified `main` source revision plus an explicitly promoted Vercel production deployment. Automatic Vercel Git deployment is intentionally frozen, so a green GitHub smoke run after a source commit validates the currently deployed release but does not by itself prove that the new commit was deployed.
- **Database:** Supabase PostgreSQL project `cnpsvfpcxbrygynihlxs` in `ap-southeast-1`.
- **Schema:** Alembic production head is `20260911_0008`.
- **Transactional email:** the live health contract requires the delivery transport to report `ok`.
- **AI provider:** live `/ai/status` exposes only the privacy-safe readiness fields `configured`, `sdk_available`, and `model`.

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
- TPO/student temporary provisioning passwords are cryptographically generated in-browser, policy compliant, read-only, copyable/regeneratable, and preserved across failed submits.
- Approved recruiter access uses the server-side provisioning workflow rather than exposing recruiter credentials to administrators.
- Frontend/API validation contracts are regression tested.
- File uploads use bounded/signature-aware validation; production file persistence is durable and database backed.
- Security headers include HSTS, CSP, frame denial, nosniff, strict referrer policy and restricted browser permissions.
- Database `DataError`, integrity conflicts and production SQLAlchemy failures return controlled 422/409/503 contracts rather than leaking internal errors.
- AI output is never fabricated when provider readiness is unavailable; core placement workflows remain independent of AI availability.
- CI generates per-commit release-integrity evidence.
- Security CI runs tracked-secret hygiene, Bandit and production dependency auditing.
- CODEOWNERS, security policy and a production PR checklist are committed.
- Canonical production smoke validates `https://www.placeai.in` health, release assets, security headers and authorization boundaries.
- Direct Vercel smoke separately validates `https://placeai-rxpp.vercel.app` health, public shell, security headers, AI readiness and hardened unauthenticated boundaries.

## Infrastructure verification

- **GitHub repository visibility:** public.
- **Canonical domain:** `https://www.placeai.in` is live; HTTPS is enforced and the bare domain redirects to the preferred `www` host.
- **Production security headers:** current public verification confirms the expected headers are present.
- **Latest verified source revision:** `e746913805f0f87d40992f858ead8af6ead72a88` has green PlaceAI CI, PlaceAI Security Audit, PlaceAI Production Smoke, PlaceAI Vercel Production Smoke and PlaceAI Platform Access Production Smoke runs.
- **Vercel automatic deployment freeze:** remains intentional. The Vercel origin must be explicitly updated when a verified source revision is approved for production.
- **Current synchronization status:** source contains the canonical sitemap/favicon fixes and current auth/mobile polish, but the live Vercel origin was still serving the previous controlled release during the 17 September verification. A controlled Vercel promotion is therefore still required before those latest fixes can be considered live.
- **Supabase security advisor:** zero current security findings in the latest review.
- **Supabase performance advisor:** unused-index notices remain informational and are intentionally retained until real workload evidence justifies removal.
- **Supabase schema:** production `alembic_version` is `20260911_0008`.
- **Live health:** the canonical-domain and direct-origin smoke workflows currently pass the required health contract.

## Remaining owner / infrastructure actions

1. **Promote the verified source to Vercel production.** Deploy the verified `main` revision through the authenticated Vercel project, preserving the production environment variables. Do not unfreeze automatic Git deployment merely to force this release.
2. **Post-deployment verification.** Confirm `https://www.placeai.in/sitemap.xml` uses only `www.placeai.in`, `/favicon.ico` is served with the intended SVG MIME type, Request Access role state remains synchronized after login-role switching, `/health` is healthy, `/ai/status` is privacy-safe, and protected routes still reject unauthenticated access.
3. **GitHub ruleset / protected main.** `main` is currently unprotected. Enable an enforced ruleset/branch protection when the repository/account plan permits it; do not weaken repository or security controls merely to obtain a free ruleset.
4. **Paid production availability.** Upgrade hosting/runtime plans before relying on paid-tier availability or materially higher institutional traffic. This is a commercial owner decision, not an application-code defect.

## Release decision

**SOURCE READY; LATEST PRODUCTION PROMOTION PENDING.**

The application source is verified and release gates are green. The latest fixes should be called fully live only after the frozen Vercel production project is explicitly promoted to the verified source revision and the post-deployment checks above pass on the canonical domain.
