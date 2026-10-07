from app.routers import ai


def test_public_ai_status_omits_provider_model_details(monkeypatch):
    monkeypatch.setattr(
        ai,
        "ai_status_payload",
        lambda: {"configured": True, "sdk_available": True, "model": "provider-model-name"},
    )

    assert ai.ai_status() == {"configured": True, "sdk_available": True}


def test_public_ai_status_preserves_unavailable_readiness(monkeypatch):
    monkeypatch.setattr(
        ai,
        "ai_status_payload",
        lambda: {"configured": False, "sdk_available": False, "model": "fallback-model-name"},
    )

    assert ai.ai_status() == {"configured": False, "sdk_available": False}
