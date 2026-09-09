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
- Automated regression suite, Python compile check and frontend JavaScript syntax checks have passed.

## Live infrastructure status on 2026-09-09

- Supabase project `cnpsvfpcxbrygynihlxs` is active and healthy in `ap-southeast-1`.
- Supabase production schema is present and aligned with the 3.1.3 session/storage baseline.
- The canonical production application URL is `https://placeai-rxpp.vercel.app`.
- The production root is publicly reachable and returns HTTP 200.
- PlaceAI is configured for the Supabase transaction pooler on port 6543 with the expected PostgreSQL username shape.
- The production `DATABASE_URL` credential was replaced/reset by the operator on 2026-09-09 after the previous live health probe classified the failure as `DATABASE_AUTHENTICATION_FAILED`.
- This commit intentionally triggers a fresh Vercel production deployment so the new production environment variable is loaded before re-running health and authentication tests.

## Remaining deployment gates

1. Verify the newly deployed `/health` endpoint reports `status=healthy` and `database=ok`.
2. Verify signup and sign-in against the production database.
3. Verify refresh/session persistence and logout.
4. Run core student, institution/TPO and recruiter smoke checks.
5. Verify QR/upload/public production paths required for the pilot.

Dedicated object storage is recommended for high-volume enterprise operation, but it is not a current durability blocker because production file bytes are persisted in PostgreSQL.
