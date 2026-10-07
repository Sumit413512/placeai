from pathlib import Path


WAKE_SQL = Path("ops/supabase/assessment_worker_wake.sql")


def test_worker_wake_is_conditional_secret_free_and_idempotent():
    source = WAKE_SQL.read_text(encoding="utf-8")

    assert "CREATE EXTENSION IF NOT EXISTS pg_net" in source
    assert "cron.unschedule('placeai-assessment-worker-wake')" in source
    assert "cron.schedule(" in source
    assert "'placeai-assessment-worker-wake'" in source
    assert "https://placeai-production.onrender.com/health" in source
    assert "state = 'running'" in source
    assert "state IN ('queued', 'retrying')" in source
    assert "interval '2 minutes'" in source
    assert "Authorization" not in source
    assert "api_key" not in source.lower()
    assert "bearer " not in source.lower()
