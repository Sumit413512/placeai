# PlaceAI V3.1.3 — Vercel Deployment Notes

PlaceAI runs as a FastAPI application on Vercel using `app.app:app`. Production is intentionally fail-closed: an invalid persistence/security configuration causes startup failure instead of silently running an unsafe ephemeral deployment.

## Required production environment variables

- `ENVIRONMENT=production`
- `DATABASE_URL=<persistent PostgreSQL connection string>`
- `JWT_SECRET_KEY=<32+ character strong random secret>`
- `JWT_REFRESH_SECRET_KEY=<different 32+ character strong random secret>`
- `BASE_URL=https://<production-domain>`
- `ALLOWED_ORIGINS=https://<production-domain>`
- `AUTO_CREATE_SCHEMA=false`
- `PUBLIC_RECRUITER_SIGNUP=false`
- `ALLOW_TALENT_POOL_SEARCH=false` unless contractually approved
- `ENABLE_AI_DEMO_FALLBACK=false`
- `DEV_SHOW_RESET_TOKEN=false`
- `GEMINI_API_KEY=<optional>`
- `GEMINI_MODEL=gemini-3.8-flash`
- `GOOGLE_CLIENT_ID=<optional if Google login is enabled>`
- SMTP variables if production password-reset email is enabled

The application refuses production SQLite and requires an HTTPS base URL/origins plus distinct strong JWT secrets.

## Durable file storage

Vercel Functions have ephemeral local filesystems. PlaceAI 3.1.3 therefore does **not** use `/tmp` as the authoritative store in production. When `VERCEL` is present or `ENVIRONMENT=production`, uploaded resumes, offer letters, authorization evidence, student documents and communication attachments are saved in the PostgreSQL `stored_files` table and referenced as `dbfile:<id>`. Downloads remain behind application authorization and send `Cache-Control: private, no-store` plus `X-Content-Type-Options: nosniff`.

Local development may still use the configured filesystem upload path. For high-volume institutional deployments, migrate binaries to dedicated private object storage with signed/authorized access and lifecycle controls to keep PostgreSQL lean.

## Database connection behavior

For non-SQLite databases on Vercel, SQLAlchemy uses serverless-safe connection behavior. Use the Supabase/provider pooler endpoint when appropriate and keep connection limits aligned with the selected database plan.

Run migrations before production traffic:

```bash
alembic upgrade head
```

Production keeps `AUTO_CREATE_SCHEMA=false`; schema changes are migration-controlled.

## Vercel entrypoint

`pyproject.toml` contains both:

```toml
[tool.fastapi]
entrypoint = "app.app:app"

[tool.vercel]
entrypoint = "app.app:app"
```

`vercel.json` configures the FastAPI function duration and excludes tests/docs/migrations from the deployed function bundle where appropriate.

## Current account state

As of 2026-09-08, Vercel has identified `Sumit413512/placeai` as an importable FastAPI repository. The repository is intentionally public. Once `main` contains the verified 3.1.3 source tree, import/link that exact repository and use it as the production deployment source. Do not deploy from the obsolete `bundle*` representation.
