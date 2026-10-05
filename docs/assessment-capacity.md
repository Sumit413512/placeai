# PlaceAI assessment capacity and rollout

Status: queue code is implemented; production queue is **disabled** until its
private schema, persistent workers, database access and provider quota are verified.
This document does not certify production capacity.

## Implemented

- Submission validates ownership and the complete server-issued question set,
  persists immutable answers, and returns HTTP 202 without calling AI.
- PostgreSQL admission serializes all workers through one control row. Workers
  use short transactions, expiring leases, heartbeat renewal and token fencing.
- A process handles two exams at a time. Across processes, both concurrent jobs
  and job starts per minute are capped. These are **job** limits, not provider
  request limits: reserve quota for all grading requests within each exam.
- Failed jobs back off for 15–300 seconds and stop after eight attempts. Restarting
  or a browser retry does not erase attempts, replace answers or bypass admission.
- All sections remain hidden until the final report is complete. Students poll
  read-only status with jitter and can return through exam history.
- Persistent web/worker instances default to three database connections each,
  zero overflow, ten-second pool wait and TLS. Serverless keeps NullPool. Prepared
  statements are disabled for transaction-pooler compatibility.
- Recording uploads release the read transaction while receiving bytes and run
  synchronous persistence outside the event loop.

## Workload target and remaining requirements

Design target: 5,000 students in exams, including a synchronized finish burst.
Do not advertise this capacity before a representative staging test passes.

| Workload | Planning estimate |
| --- | --- |
| Status reads with 8–12 second jitter | about 500 requests/second while all reports are pending |
| Current 4-second recording chunks | about 1,250 API uploads/second during the HR section |
| Recording bitrate, video plus audio | 272 kbit/second per student; about 1.36 Gbit/second for 5,000 |
| Ten-minute recording at that bitrate | about 20.4 MB per exam; 102 GB for one 5,000-student cohort |
| Application maximum recording size | 28 MiB; about 137 GiB for 5,000 recordings |
| 5,000 completions at 30 seconds per job and 64 concurrent jobs | idealized 39 minutes, excluding retries and quota waits |

The last row is a mathematical estimate, **not measured AI throughput**. Media
processing, question mix, code execution and provider quotas can increase it.

The existing database byte-chunk recording path is **not suitable as the final
5,000-video architecture**. Before admitting that cohort, implement direct private
object-storage uploads with resumability, one-time immutable object paths,
server-verified size/hash/format, owner and institution checks, and verified
30-day object deletion. Keep metadata and assessment jobs in PostgreSQL; workers
retrieve private media. No public bucket or client service-role key is acceptable.
Supabase supports signed-token resumable uploads; do not substitute Supabase Auth
identity policies for PlaceAI's existing custom authentication.

Start-question generation, code-execution capacity and proctoring inference must
also be included in the staging scenario. Submission-only measurements do not
measure those paths. Do not overload the live service to discover its limits.

## Proposed paid validation environment

The initial paid configuration is two Render web instances and two Render worker
instances, each `1c-2g`, plus Supabase Pro with Medium compute and a Render workspace
that permits horizontal scaling. This is a validation baseline, not a guaranteed
5,000-user configuration. Existing Vercel frontend/API routing must be checked;
adding Render instances does not automatically move Vercel API traffic to them.

Indicative recurring base cost: four Render instances at $25/month = $100,
Supabase Pro $25 + Medium $60 minus $10 compute credit = $75, and a Render Pro
workspace around $25/month: **about $200/month**, excluding current Vercel charges,
AI usage, media storage/egress, tax and staging duplicates. Confirm dashboard
pricing and the actual workspace plan before purchase. A peak worker fleet costs
more; 32 workers plus four web instances at this compute size is around $900/month
for Render compute alone. Do not enable this fleet without a spend approval.

## Deployment sequence

1. Require green CI including the real PostgreSQL multi-worker admission test and
   Security Audit. Apply Alembic `20261005_0016` using the migration owner.
2. Keep queue tables private with RLS and revoked anon/authenticated access.
   Configure a server-only backend/worker role with explicitly approved access.
   Repair the existing Render database login and prior private-table permissions
   before deploying a worker. Never mark unapplied migrations as complete.
3. Configure the worker service described in `deploy/render-assessment-worker.yaml`.
   Match database and AI provider configuration with the web service. Do not copy
   secrets into source, job payloads, browser configuration or logs.
4. Start worker with `ENABLE_ASSESSMENT_QUEUE=true`, global concurrency 4 and
   starts/minute 12. Leave the web flag false until the worker is healthy.
5. Enable the web queue flag, perform an isolated real complete assessment,
   verify all-section results and owner/reviewer access, then clean test data.
6. Run staging bursts at 100, 500, 1,000 and 5,000 virtual students, including
   authenticated starts, question navigation, proctor calls, recording upload,
   finish bursts and result reads. Stage synthetic media, never personal data.
7. Require zero lost/overwritten submissions, no cross-tenant media access,
   submission p95 under 2 seconds, acceptable pool waits, no sustained provider
   throttling, worker recovery after kill/redeploy and an agreed report latency.
   Measure real per-exam request/token cost before raising admission settings.

Rollback: retain queue readers and workers while saved jobs drain. Do not disable
the web flag with outstanding non-HR jobs, as legacy history does not show them.
Stop new admission through the deployment's maintenance controls, lower concurrency
or restore the previously verified queue version. Do not drop queued answers.

## Reproducible evidence

`python -m scripts.benchmark_assessment_queue --students 2000 --concurrency 32`
runs synthetic HTTP submissions against an isolated SQLite WAL database. It reports
saved count, premature scores, errors, throughput and latency. It never invokes AI
or connects to production. CI additionally exercises PostgreSQL locking with 32
concurrent claims against a disposable schema.

References, verified October 5, 2026:

- [Render compute plans](https://render.com/docs/compute-plans)
- [Render service scaling](https://render.com/docs/scaling)
- [Render background workers](https://render.com/docs/background-workers)
- [Render compute pricing example](https://render.com/articles/production-rails-hosting-guide)
- [Render workspace plans](https://render.com/docs/new-workspace-plans)
- [Supabase pricing](https://supabase.com/pricing)
- [Supabase database connections](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Supabase private resumable uploads](https://supabase.com/docs/guides/storage/uploads/resumable-uploads)
