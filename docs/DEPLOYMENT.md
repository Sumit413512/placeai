# Deployment Notes

PlaceAI currently uses a Render-first controlled production path. The public application is served from `https://placeai-recovery.onrender.com`; Render serves the UI shell and security assets locally and proxies API traffic to the last known healthy Vercel backend deployment. Automatic Vercel Git deployments are disabled so Vercel build/function quota cannot block a PlaceAI release. The Vercel backend remains a temporary dependency until the dedicated Render full-app service has a synchronized Supabase database credential.

Supabase remains the production PostgreSQL system of record. Uploaded file bytes are persisted through the database-backed `stored_files` layer; local filesystem upload paths are development fallback only.

Production environment for any full-app runtime must include:

- `ENVIRONMENT=production`
- persistent PostgreSQL `DATABASE_URL`
- unique 32+ character access/refresh JWT secrets
- exact HTTPS `ALLOWED_ORIGINS`
- HTTPS `BASE_URL`
- `AUTO_CREATE_SCHEMA=false`
- recruiter self-signup disabled unless explicitly approved
- synthetic AI fallback removed
- reset-token debugging disabled

Apply reviewed migrations before serving traffic:

```bash
alembic upgrade head
```

Release authority is the GitHub `PlaceAI Production Smoke` workflow against the Render public endpoint. The smoke gate verifies gateway/upstream/database/configuration/email health, root and favicon availability, security headers, current client validation assets, unauthenticated auth boundaries, and password-reset error behavior.

The CI workflow generates an immutable SHA-256 manifest for each exact Git commit and uploads it as workflow evidence. A committed hand-maintained manifest is intentionally not used because it can become stale after legitimate source changes.

For a later direct Render cutover, synchronize the dedicated least-privilege Supabase runtime credential in Render, deploy the full FastAPI application, run migrations, execute the same production smoke contract against the direct Render service, and only then retire the gateway. Do not broaden database privileges to work around credential mismatch.

For larger production scale, use a paid always-on runtime, managed PostgreSQL/pooling, dedicated private object storage for large binary volumes, encrypted secret management, automated backups/restore tests, centralized logs/APM, WAF/bot protection and operational alerting.
