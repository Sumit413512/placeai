# PlaceAI capacity and recovery review • 20 November 2026

## What the deployment showed

The primary health check on www.placeai.in returned healthy, with the database and transactional email available. The Render application at placeai-production.onrender.com served the same release (c30a4299), reported a healthy database and an in-process assessment worker, and reported transactional email unconfigured. Vercel delegates assessment processing to an external worker. These were point-in-time observations. Both application deployments depend on the same Supabase PostgreSQL service. The repository contains an hourly fallback release convergence check. It does not switch customer traffic. The older recovery proxy depends on its upstream. A green health check on one of these applications cannot establish database redundancy or successful password reset on the fallback.

The production request metrics query did not return a complete time series. Runtime logs can contain multiple records per request and cannot establish a peak RPS, p95 or available headroom. Actual sustained production capacity and simultaneous active users remain unmeasured.

## Assessment submission test

Used the production revision's scripts/benchmark_assessment_queue.py with an isolated UTF-8 PostgreSQL 16 database, the full ORM schema and a connection pool equal to the chosen concurrency. Ran 500 unique students, exams and submissions per run. Each student submitted a synthetic question to the FastAPI evaluation handler via TestClient. Login and the AI guard were overridden by the benchmark. Traffic did not pass through the public network, Vercel, production connection pooler, media services or a grading provider.

| Concurrent clients | Time for 500 | Accepted and persisted | Requests/s | Median | p95 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 3.23 s | 500 | 154.61 | 6.09 ms | 7.54 ms |
| 10 | 3.70 s | 500 | 134.97 | 69.32 ms | 97.37 ms |
| 50 | 4.14 s | 500 | 120.67 | 376.29 ms | 538.78 ms |

Every request returned 202 and created a durable job. No final scores or provider calls occurred. At higher concurrency queue admission remained correct but latency increased and throughput fell. Short bursts on one host cannot establish a safe sustained rate. Measure admission and report delivery separately.

## Recovery evidence

Dumped the final synthetic PostgreSQL database to a custom-format archive and restored it into a separate empty database using pg_restore with exit-on-error. Counts and deterministic row-content digests matched for 500 jobs, 500 interviews, 501 users and 500 student profiles. This exercised a small logical restore. It did not test recovery of production credentials, external storage, DNS, OAuth, email or provider integrations.

The operations guide records a Free Supabase plan and describes off-site exports as an operator responsibility. No production backup timestamp, retained recovery point, successful production-sized restore, cross-region replica or automatic promotion was established during this review. Database backups, application rollback and object backups solve distinct failure modes.

## Priority implementation and acceptance checks

1. **Prove recovery before the next institutional launch.** Assign an owner. Verify the current provider backup tier and last successful backup. Configure encrypted off-site database exports or managed backups with monitored freshness and independently recoverable access. Back up private object contents and manifests separately. Restore to a clean nonproduction project, reconcile per-tenant counts, verify representative objects and sign-in, then record actual data loss and elapsed recovery time. For procurement discussions propose a 15-minute recovery point and 2-hour recovery time, subject to cost and actual drills. Daily exports alone cannot meet a 15-minute recovery point.
2. **Make application failover usable.** Configure transactional email on the independent fallback, validate origins and OAuth callbacks, and test controlled traffic switching and reversal on a staging hostname. Exercise sign-in, password reset, tenant isolation and assessment resumption with synthetic accounts. Keep the primary and fallback on compatible schema revisions. Monitor both from outside the hosting providers.
3. **Separate submission from grading capacity.** Keep the existing PostgreSQL job leases, heartbeats and bounded retries. Run two independently restartable workers against a shared admission limit. Kill one during a staging evaluation and confirm the surviving worker eventually completes the job once. Alert on oldest pending job, expired leases, exhausted retries and provider quota. Measure reports completed per minute and end-to-end wait. Concurrent submissions alone say nothing about report delivery.
4. **Relieve recording pressure.** The repository's 5,000-student scenario estimates about 1,250 four-second chunk uploads/s, 1.36 Gbit/s and 102 GB per ten minutes. Status polling could add about 500 reads/s when all reports are pending. They describe different phases. Move recording bytes to private resumable object uploads. Keep authorization and metadata in PostgreSQL, verify object ownership, integrity and retention, and include objects in recovery drills.
5. **Publish a measured capacity envelope.** In a production-equivalent staging deployment with the same region, pool limits and provider quotas, replay a realistic mix of sign-in, dashboards, starts, uploads, synchronized submissions, polling and report reads. Start at 25, 50 and 100 simultaneous users. Hold each stage for 30 minutes before increasing and run a two-hour soak at the highest passing level. Report offered and completed requests/s by minute, p50/p95/p99, 429/5xx, pool waits, oldest job and grading completions/min. Proposed initial gates are p95 below 500 ms for interactive reads, below 1 s for submission acknowledgement, fewer than 0.5% unexpected errors and zero accepted submissions lost. Calibrate separate report-delivery targets against a real provider quota before committing to a college. Repeat with a worker unavailable and during database recovery.

Evidence in the repository includes docs/assessment-capacity.md, docs/PRODUCTION_OPERATIONS.md, scripts/benchmark_assessment_queue.py and .github/workflows/render-fallback-convergence.yml. The separate Render role-entry preview uses disposable SQLite and is unsuitable for a production-equivalent load test.
