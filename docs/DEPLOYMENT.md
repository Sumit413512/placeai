# Deployment Notes

For a controlled pilot, deploy PlaceAI behind HTTPS with managed PostgreSQL. Vercel/production persists uploaded file bytes through the database-backed `stored_files` layer; local filesystem upload paths are development fallback only.

Production environment must include:

- `ENVIRONMENT=production`
- persistent PostgreSQL `DATABASE_URL`
- unique 32+ character access/refresh JWT secrets
- exact HTTPS `ALLOWED_ORIGINS`
- HTTPS `BASE_URL`
- `AUTO_CREATE_SCHEMA=false`
- recruiter self-signup disabled unless explicitly approved
- Synthetic AI fallback removed
- reset-token debugging disabled

Apply reviewed migrations before serving traffic:

```bash
alembic upgrade head
```

The included Docker Compose stack is an infrastructure reference for single-server deployment. For larger cloud production, prefer managed PostgreSQL/pooling, dedicated private object storage for large binary volumes, encrypted secret management, automated backups/restore tests, centralized logs/APM, WAF/bot protection and operational alerting.
