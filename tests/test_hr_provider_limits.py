from app import free_provider, hr_video


def test_hr_recording_size_never_exceeds_groq_free_transcription_limit(monkeypatch):
    provider_limit = 25 * 1024 * 1024
    assert hr_video.MAX_BYTES <= provider_limit

    monkeypatch.setenv("GROQ_PROCESSING_APPROVED", "true")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    oversized = b"x" * (provider_limit + 1)
    try:
        free_provider.transcribe(oversized, "video/webm")
    except free_provider.ProviderError as error:
        assert str(error) == "FREE_PROVIDER_INPUT_LIMIT"
    else:
        raise AssertionError("Groq oversized transcription payload must be rejected before network I/O")
