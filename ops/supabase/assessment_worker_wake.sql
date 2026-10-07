-- PlaceAI assessment worker wake bridge for Render Free web service.
--
-- This is Supabase infrastructure, not an application Alembic migration. The
-- Render database role is intentionally restricted and must not manage extensions
-- or pg_cron jobs during app startup.
--
-- The job does NOT keep Render alive continuously. It sends one unauthenticated
-- GET to the public Render /health endpoint only when there is assessment work
-- that is running or becomes due within two minutes. No API key, cookie, user
-- identifier, transcript, recording metadata, or authorization header is stored
-- in pg_net.
--
-- Re-applying this file is safe: the named cron job is replaced atomically from
-- an operator perspective by unscheduling the existing job and scheduling the
-- canonical definition below.

CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;

SELECT cron.unschedule('placeai-assessment-worker-wake')
WHERE EXISTS (
    SELECT 1
    FROM cron.job
    WHERE jobname = 'placeai-assessment-worker-wake'
);

SELECT cron.schedule(
    'placeai-assessment-worker-wake',
    '* * * * *',
    $cron$
    SELECT net.http_get(
        url := 'https://placeai-production.onrender.com/health',
        timeout_milliseconds := 5000
    ) AS request_id
    WHERE EXISTS (
        SELECT 1
        FROM public.assessment_jobs
        WHERE state = 'running'
           OR (
               state IN ('queued', 'retrying')
               AND available_at <= (now() AT TIME ZONE 'utc') + interval '2 minutes'
           )
    );
    $cron$
);

-- Operator verification after applying:
--   SELECT extname, extversion FROM pg_extension WHERE extname = 'pg_net';
--   SELECT jobid, jobname, schedule, active, command
--     FROM cron.job WHERE jobname = 'placeai-assessment-worker-wake';
--   SELECT jobid, status, return_message, start_time, end_time
--     FROM cron.job_run_details
--    WHERE jobid = (SELECT jobid FROM cron.job
--                    WHERE jobname = 'placeai-assessment-worker-wake')
--    ORDER BY start_time DESC LIMIT 5;
-- When the assessment queue is empty, successful runs should report "0 rows".
