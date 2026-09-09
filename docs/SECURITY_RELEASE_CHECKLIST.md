# Security Release Checklist

Before any client deployment:

- Use PostgreSQL, not a bundled SQLite database.
- Set unique 32+ character `JWT_SECRET_KEY` and `JWT_REFRESH_SECRET_KEY` values.
- Keep `PUBLIC_RECRUITER_SIGNUP=false`.
- Synthetic AI fallback is not supported.
- Keep `ALLOW_TALENT_POOL_SEARCH=false` unless a documented data-sharing policy exists.
- Restrict `ALLOWED_ORIGINS` to the deployed frontend origin.
- Serve only over HTTPS and verify HSTS at the edge.
- Configure SMTP and verify reset links point to the production base URL.
- Never ship `.env`, databases, résumés, logs, venv folders, caches or Git history.
- Run `pytest` and `python scripts/release_check.py` on the release artifact.
- Review all institution/recruiter accounts and remove unauthorized or test users/data.
- Configure database backups and restore testing.
- Verify production is using database-backed `stored_files` persistence; for high-volume deployments, move binaries to dedicated private object storage with lifecycle controls.
- Keep signature/OOXML validation enabled and add malware scanning/content-disarm policy before accepting arbitrary production uploads at scale.
- Export the built-in tenant audit trail to centralized/immutable logging for enterprise deployments; also add MFA/SSO and observability. Database-backed API/auth rate limiting is already enabled; add edge/WAF controls for volumetric abuse.
- Complete applicable privacy notices, retention policy, DPA/vendor terms and AI-processing disclosure for the target jurisdiction.
