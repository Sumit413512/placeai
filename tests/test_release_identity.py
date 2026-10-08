from __future__ import annotations

import importlib


app_module = importlib.import_module("app.app")


def _clear_release_env(monkeypatch):
    for name in ("VERCEL_GIT_COMMIT_SHA", "RENDER_GIT_COMMIT", "GITHUB_SHA"):
        monkeypatch.delenv(name, raising=False)


def test_release_sha_prefers_vercel_and_normalizes_hex(monkeypatch):
    _clear_release_env(monkeypatch)
    monkeypatch.setenv("VERCEL_GIT_COMMIT_SHA", "A" * 40)
    monkeypatch.setenv("RENDER_GIT_COMMIT", "b" * 40)
    assert app_module._release_sha() == "a" * 40


def test_release_sha_falls_back_to_render(monkeypatch):
    _clear_release_env(monkeypatch)
    monkeypatch.setenv("RENDER_GIT_COMMIT", "b" * 40)
    assert app_module._release_sha() == "b" * 40


def test_release_sha_rejects_non_hex_and_uses_github(monkeypatch):
    _clear_release_env(monkeypatch)
    monkeypatch.setenv("VERCEL_GIT_COMMIT_SHA", "not-a-commit")
    monkeypatch.setenv("RENDER_GIT_COMMIT", "also-not-a-commit")
    monkeypatch.setenv("GITHUB_SHA", "c" * 40)
    assert app_module._release_sha() == "c" * 40


def test_release_sha_is_absent_without_valid_runtime_metadata(monkeypatch):
    _clear_release_env(monkeypatch)
    monkeypatch.setenv("VERCEL_GIT_COMMIT_SHA", "")
    monkeypatch.setenv("GITHUB_SHA", "xyz")
    assert app_module._release_sha() is None
