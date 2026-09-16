# PlaceAI V3.1.4 — Vercel Deployment Notes

PlaceAI runs as a FastAPI application on Vercel using `app.app:app`. Production is intentionally fail-closed: an invalid persistence/security configuration causes startup failure instead of silently running an unsafe ephemeral deployment.

## Canonical production endpoints

- **User-facing production:** `https://www.placeai.in`
- **Direct Vercel origin:** `https://placeai-rxpp.vercel.app`
- **Render:** optional recovery/fallback only; Render URLs are not canonical public PlaceAI URLs.

The custom domain and direct Vercel origin must be verified separately after each controlled production promotion.

## Required production environment variables

- `ENVIRONMENT=production`
- `DATABASE_URL=<persistent PostgreSQL connection string>`
- `JWT_SECRET_KEY=<32+ character strong random secret>`
- `JWT_REFRESH_SECRET_KEY=<different 32+ character strong random secret>`
- `BASE_URL=https://www.placeai.in`
- `ALLOWED_ORIGINS=https://www.placeai.in`
- `AUTO_CREATE_SCHEMA=false`
- `PUBLIC_RECRUITER_SIGNUP=false`
- `ALLOW_TALENT_POOL_SEARCH=false` unless contractually approved
- Synthetic AI fallback is not supported
- `DEV_SHOW_RESET_TOKEN=false`
- `GEMINI_API_KEY=<optional>`
- `GEMINI_MODEL=<configured production model>`
- `GOOGLE_CLIENT_ID=<optional if Google login is enabled>`
- SMTP/Brevo delivery variables if production password-reset email is enabled

The application refuses production SQLite and requires an HTTPS base URL/origins plus distinct strong JWT secrets.

## Durable file storage

Vercel Functions have ephemeral local filesystems. PlaceAI therefore does **not** use `/tmp` as the authoritative store in production. When `VERCEL` is present or `ENVIRONMENT=production`, uploaded resumes, offer letters, authorization evidence, student documents and communication attachments are saved in the PostgreSQL `stored_files` table and referenced as `dbfile:<id>`. Downloads remain behind application authorization and send `Cache-Control: private, no-store` plus `X-Content-Type-Options: nosniff`.

Local development may still use the configured filesystem upload path. For high-volume institutional deployments, migrate binaries to dedicated private object storage with signed/authorized access and lifecycle controls to keep PostgreSQL lean.

## Database connection behavior

For non-SQLite databases on Vercel, SQLAlchemy uses serverless-safe connection behavior. Use the Supabase/provider pooler endpoint when appropriate and keep connection limits aligned with the selected database plan.

Run migrations before production traffic:

```bash
alembic upgrade head
```

Production keeps `AUTO_CREATE_SCHEMA=false`; schema changes are migration-controlled.

## Vercel entrypoint

The FastAPI entrypoint is:

```text
app.app:app
```

Deployment configuration must include the application templates/static files and exclude non-runtime development/test material where appropriate.

## Controlled release policy

Automatic Vercel Git deployment is intentionally frozen for production control. This has an important operational consequence:

- Merging a verified commit to `main` does **not** automatically update the Vercel production runtime.
- A green canonical-domain or direct-origin smoke workflow proves the currently deployed runtime is healthy; it does not, by itself, prove that the latest source commit was promoted.
- Production promotion must therefore be an explicit authenticated Vercel action using the verified source revision.
- `.github/workflows/export-vercel-bundle.yml` can generate a deterministic source bundle for controlled deployment workflows. Do not deploy obsolete historical `bundle*` representations.
- Do not unfreeze automatic Git deployment merely to force a release unless the release policy itself is deliberately changed and reviewed.

## Required post-deployment checks

After promoting a verified source revision to Vercel production, verify all of the following before calling the revision live:

1. `https://www.placeai.in/health` returns the required healthy database/configuration/transactional-email contract.
2. `https://placeai-rxpp.vercel.app/health` returns the same healthy contract.
3. `https://www.placeai.in/sitemap.xml` contains canonical `www.placeai.in` URLs only.
4. `https://www.placeai.in/favicon.ico` is served with the intended SVG MIME type.
5. Login role switching keeps Request Access role state synchronized.
6. `/ai/status` exposes only privacy-safe readiness fields.
7. Hardened protected routes reject unauthenticated requests as expected.
8. PlaceAI CI, Security Audit, Production Smoke, Vercel Production Smoke and Platform Access Production Smoke are green for the release state.

## Current release synchronization note

As of 17 September 2026, the verified source revision contains additional canonical SEO/favicon and auth/mobile polish that has passed CI/security checks. Because Vercel automatic Git deployment remains frozen, the direct production origin still requires an explicit controlled promotion before those latest source changes can be considered live.
