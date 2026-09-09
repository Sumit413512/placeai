# Deployment preparation status

Baseline: PlaceAI Commercial V3.1.3 Production Security & Persistence Hardening.

## Verified source state

- FastAPI application entrypoint is `app.app:app` for local and Vercel execution.
- Production startup rejects SQLite, weak/equal JWT secrets, wildcard/non-HTTPS CORS, non-HTTPS `BASE_URL`, automatic schema creation and reset-token debugging.
- Vercel/non-local production uses PostgreSQL-backed durable `stored_files`; local development keeps a filesystem fallback.
- Refresh sessions are database-backed, rotated on refresh, revoked on logout and invalidated by `auth_version` after password reset.
- Authentication/demo abuse controls use database-backed rate-limit buckets suitable for multiple serverless instances.
- Uploads validate content signatures/OOXML containers instead of trusting filename extensions; legacy `.doc`/`.xls` uploads are rejected.
- Cross-institution references are validated across attendance, communications, interviews and incident workflows.
- Access tokens are memory-only in the browser; browser persistence relies on the HttpOnly refresh cookie.
- PDF extraction is bounded to 30 pages/50,000 extracted characters and uses maintained `pypdf`.
- Alembic migrations reach head successfully from both a blank database and the prior 3.1.2 schema path.
- Automated regression suite: 12/12 passed.
- Python compile check passed.
- Frontend JavaScript syntax check passed.

## Live infrastructure status

- Supabase production schema is present and aligned with the 3.1.3 session/storage baseline.
- Supabase `anon` and `authenticated` Data API roles have no table grants on the PlaceAI `public` tables; PlaceAI uses the direct PostgreSQL application connection.
- Eight previously missing foreign-key indexes were added.
- GitHub repository `Sumit413512/placeai` is intentionally **public** and is the canonical source repository.
- Vercel production serves PlaceAI at `https://placeai-rxpp.vercel.app`.
- Production `DATABASE_URL` was refreshed on 2026-09-09 and this documentation-only commit intentionally triggers a fresh production deployment so the new runtime secret is loaded.

## Remaining deployment gates

1. Verify the fresh Vercel production deployment loads the updated `DATABASE_URL`.
2. Require `/health` to return HTTP 200 with `database=ok`.
3. Run live login/signup/student/TPO/recruiter smoke checks.
4. Run upload/QR/regression checks against the deployed URL.

Dedicated object storage is recommended for high-volume enterprise operation, but it is no longer a functional durability blocker for the current Vercel pilot because production file bytes are persisted in PostgreSQL.
