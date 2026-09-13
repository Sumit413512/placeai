# PlaceAI Production Operations

Last reviewed: 12 September 2026

## Production path

Authoritative public route: `https://placeai-recovery.onrender.com`

Current request path: Render public gateway -> Vercel FastAPI backend -> Supabase Postgres.

## Health checks

Primary health endpoint: `/_recovery/health`.

A production check is healthy only when the response reports:

- `status=healthy`
- `gateway=ok`
- `upstream=healthy`
- `database=ok`
- `configuration=ok`
- `transactional_email=ok`

AI readiness is checked independently at `/ai/status` and must return boolean `configured` and `sdk_available` fields plus a non-empty model identifier.

The GitHub Actions workflow `.github/workflows/production-smoke.yml` runs on release pushes and on a recurring schedule. A failed scheduled run is an operational incident and should be investigated before making another release.

## Incident response

1. Confirm `/_recovery/health` and `/ai/status`.
2. Check Render request/application logs for 5xx responses and upstream failures.
3. Check Vercel runtime errors for the backend.
4. Check Supabase project health and the database security advisor.
5. If only AI is unavailable, core placement workflows remain operational; investigate OpenAI first and Gemini fallback second.
6. If transactional email is unavailable, treat password recovery as degraded and avoid onboarding users who depend on email recovery until restored.
7. Do not expose API keys, database credentials, reset tokens or request payload secrets while debugging.

## Database backup and recovery

The current Supabase organization is on the Free plan. Supabase recommends that Free projects regularly create off-site logical exports with `supabase db dump`/`pg_dump`. Managed downloadable daily backups are a paid-plan feature.

Before a broad paid institutional rollout, use one of these production recovery strategies:

- Upgrade the Supabase project to a paid plan and verify scheduled backups in Database -> Backups; or
- Maintain encrypted off-site logical database dumps on a documented schedule.

Recommended minimum for production: daily database backup, retention of at least 7 days, and a quarterly restore test. High-value production deployments should consider Point-in-Time Recovery after reviewing its cost and recovery requirements.

A database backup does not automatically restore uploaded binary objects stored outside Postgres. File/object storage must have its own backup/export procedure if used for production documents.

## Recovery test

A backup is not considered verified until a restore has been tested into a non-production environment. The restore test must confirm:

- schema/migrations are present;
- institution, user, application and audit records can be queried;
- authentication/runtime secrets are reconfigured separately and are not expected to be contained in a database dump;
- no production traffic is pointed at the test environment.

## Release controls

Every production release must pass:

- PlaceAI CI;
- PlaceAI Security Audit;
- PlaceAI Production Smoke;
- live AI-provider readiness check when AI functionality changed.

Vercel Git deployments remain frozen except for controlled backend releases. Render recovery gateway auto-deploy remains disabled and is manually deployed after the release branch is synchronized.

## Repository governance target

The production target is a private GitHub repository with `main` protected by a ruleset requiring pull requests and successful CI, Security Audit and Production Smoke checks, with force pushes and branch deletion blocked.

## Domain target

Use a PlaceAI-owned custom HTTPS domain as `PUBLIC_APP_URL` once purchased and connected. Update password-reset/public-link configuration only after the domain's TLS and production routing have been verified.

## Legal surface

Public production pages:

- `/privacy`
- `/terms`
- `/acceptable-use`

These pages are baseline product policies. Institution-specific contracts, data-processing agreements and employment/privacy obligations should be reviewed by qualified counsel before large commercial deployments.
