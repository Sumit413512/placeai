from pathlib import Path

from app.free_provider import ProviderError


WORKER = Path("app/assessment_worker.py")


def test_local_groq_failures_get_bounded_internal_status_classes():
    assert ProviderError("FREE_PROVIDER_NETWORK").code == 503
    assert ProviderError("FREE_PROVIDER_INVALID_RESPONSE").code == 502
    assert ProviderError("FREE_PROVIDER_INCOMPLETE_RESPONSE").code == 504
    assert ProviderError("FREE_PROVIDER_INVALID_TRANSCRIPT").code == 500
    assert ProviderError("FREE_PROVIDER_INPUT_LIMIT").code == 422
    assert ProviderError("FREE_PROVIDER_REJECTED", 429).code == 429


def test_assessment_worker_preserves_video_provider_busy_code():
    source = WORKER.read_text(encoding="utf-8")
    assert '"VIDEO_PROVIDER_BUSY"' in source
    assert 'detail.get("code") in PROVIDER_ERROR_CODES' in source
    assert 'error_code or "unclassified"' in source
