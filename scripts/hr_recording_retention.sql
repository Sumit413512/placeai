-- Run after Alembic revision 20261003_0015 on the PlaceAI Supabase project.
-- Only expired recording bytes are removed; exam reports and feedback remain.
CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA pg_catalog;
GRANT USAGE ON SCHEMA cron TO postgres;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA cron TO postgres;

SELECT cron.schedule(
    'placeai-expired-hr-recordings',
    '17 * * * *',
    $job$
    WITH expired AS (
        SELECT id FROM public.hr_recordings
        WHERE expires_at <= timezone('UTC', now()) AND status <> 'expired'
        ORDER BY expires_at LIMIT 100 FOR UPDATE SKIP LOCKED
    ), removed AS (
        DELETE FROM public.hr_video_chunks
        WHERE recording_id IN (SELECT id FROM expired)
    )
    UPDATE public.hr_recordings SET status = 'expired'
    WHERE id IN (SELECT id FROM expired);
    $job$
);
