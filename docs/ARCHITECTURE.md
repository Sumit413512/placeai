# Architecture

## Application layers

Browser UI → FastAPI REST API → SQLAlchemy → PostgreSQL/SQLite.

AI requests are explicitly routed through the Gemini adapter. Local development may store files on the configured upload volume. Vercel/production persists uploaded file bytes in PostgreSQL through `StoredFile` and `dbfile:<id>` references so serverless filesystem ephemerality does not lose user documents. Dedicated private object storage remains the recommended scale-out path for large binary volumes.

## Tenancy

`Organization` is the institution tenant. Institution administrators and students are scoped using `organization_id`. Campus jobs explicitly target an institution and require institution approval before they become active. Placement drives are always scoped to one institution and one approved job.

Recruiters are independent users. Candidate access defaults to applicants in jobs owned by that recruiter. `ALLOW_TALENT_POOL_SEARCH=true` intentionally broadens this and should only be enabled under an institution-approved data-sharing policy.

## Roles

- `student`: owns profile, résumé, applications and mock-interview history.
- `recruiter`: owns recruiter profile and job/application pipeline.
- `institution_admin`: controls tenant student records, recruiter provisioning, campus-job approval and drives.
- `platform_admin`: creates institution tenants and institution administrators.

## Job lifecycle

Public recruiter job → approved immediately for authenticated users.

Campus recruiter job → target institution → `pending` → TPO `approved`/`rejected` → approved job → placement drive → eligibility filtering → student applications → recruiter pipeline → institutional outcomes.

## Authentication

Access JWT: short-lived bearer token.

Refresh JWT: rotated and set as an HttpOnly `SameSite=Lax` cookie for browser sessions. Each refresh `jti` is persisted in `refresh_sessions`; successful refresh revokes the consumed session before issuing the next token, logout revokes the active refresh session, and `auth_version` invalidates older credentials after password reset.

Browser access JWTs are memory-only and are re-established after reload through the HttpOnly refresh cookie.

Password reset token: random one-time token delivered to the user; only its SHA-256 digest is stored in the database.

## V3.0 enterprise workflow layer

V3.0 adds a dedicated enterprise router/service layer while retaining the original role routers. The enterprise layer owns company verification evidence, drive stages, interviews/evaluations, notifications/preferences, readiness scoring, advanced eligibility, placement policies, offers, student documents, attendance, analytics, search, announcements, communication threads, incidents, reports, custom fields, calendar aggregation and profile approvals.

All enterprise reads and writes are still authorized through the same `User`/role/organization model. Recruiter access is constrained by application/job ownership; institution access remains tenant-scoped; student records are limited to the signed-in student unless an explicit institution workflow grants access.

### Controlled document storage

Local development stores uploads under the configured upload root. Production/Vercel stores file bytes in the database-backed `stored_files` table and keeps only opaque `dbfile:<id>` references on domain records. Downloads are served only through authenticated endpoints after authorization checks. Content is validated against its declared type before persistence. For high-volume multi-instance deployments, dedicated private object storage with short-lived signed/authorized downloads is recommended as a scale optimization, not as a durability prerequisite for the current pilot.
