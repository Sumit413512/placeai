-- PlaceAI durable background worker wake bridge for Render free web service.
--
-- Applied manually to Supabase because the restricted app database role must
-- not manage pg_cron or pg_net. Reapplying is safe: pg_cron upserts this name.
--
-- Render free web services can spin down without external requests even while
-- the PostgreSQL learning queue has pending lessons. The previous wake job only
-- watched assessment_jobs; queued educational videos then never resumed.
-- This one watches ALL three durable queues (assessments, video, notebooks).
--
-- Only the PUBLIC Render /health URL is called. No user data, tokens, API keys,
-- recordings, account identifiers or lesson text leave the database.
-- When every queue is idle, the query makes ZERO network calls, allowing Render
-- to sleep normally and avoiding unnecessary platform usage.

CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;

SELECT cron.schedule(
    'placeai-assessment-worker-wake',
    '* * * * *',
    $cron$
    SELECT net.http_get(
        url := 'https://placeai-production.onrender.com/health',
        timeout_milliseconds := 20000
    ) AS request_id
    WHERE EXISTS (
        SELECT 1 FROM public.assessment_jobs
        WHERE state = 'running'
           OR (state IN ('queued', 'retrying')
               AND available_at <= (now() AT TIME ZONE 'utc') + interval '2 minutes')
    )
    OR EXISTS (
        SELECT 1 FROM public.learning_video_lessons
        WHERE state = 'running'
           OR (state IN ('queued', 'retrying')
               AND available_at <= (now() AT TIME ZONE 'utc') + interval '2 minutes')
    )
    OR EXISTS (
        SELECT 1 FROM public.learning_video_courses
        WHERE state = 'running'
           OR (state IN ('queued', 'retrying')
               AND available_at <= (now() AT TIME ZONE 'utc') + interval '2 minutes')
    )
    OR EXISTS (
        SELECT 1 FROM public.learning_notebooks
        WHERE state = 'running'
           OR (state IN ('queued', 'retrying')
               AND available_at <= (now() AT TIME ZONE 'utc') + interval '2 minutes')
    );
    $cron$
);

-- Self-heal a stalled pg_net HTTP worker only when PlaceAI wake requests
-- are backing up, and pg_net has not completed ANY HTTP response recently.
-- The predicate is intentionally narrow: never restart a healthy worker or
-- interfere with a third-party queued request.
SELECT cron.schedule(
    'placeai-pgnet-wake-watchdog',
    '*/5 * * * *',
    $watchdog$
    SELECT net.worker_restart() AS restarted
    WHERE (
        SELECT count(*)
        FROM net.http_request_queue
        WHERE url = 'https://placeai-production.onrender.com/health'
    ) >= 4
    AND NOT EXISTS (
        SELECT 1
        FROM net._http_response
        WHERE created >= now() - interval '10 minutes'
    );
    $watchdog$
);

-- Operational verification:
-- SELECT jobid, jobname, active FROM cron.job
--   WHERE jobname = 'placeai-assessment-worker-wake';
-- SELECT status, start_time, end_time
--   FROM cron.job_run_details
--   WHERE jobid = (SELECT jobid FROM cron.job WHERE jobname='placeai-assessment-worker-wake')
--   ORDER BY start_time DESC LIMIT 5;
-- SELECT status_code, created FROM net._http_response ORDER BY created DESC LIMIT 10;
-- SELECT checked_at, provider_configured FROM public.learning_runtime WHERE id=1;
--
-- pg_cron "succeeded / 0 rows" does NOT mean the HTTP request succeeded.
-- pg_net is async, so confirm responses and Render logs independently.
-- If pg_net has a backed-up HTTP queue and stopped recording responses,
-- inspect its worker status and use SELECT net.worker_restart() as a targeted
-- recovery. A paid always-on worker is the recommended production topology.
