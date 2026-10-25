"""Keep deployed detector artifacts complete, pinned and identical on both hosts."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_proctor_assets_are_complete_and_mirrored():
    app = ROOT / "app/static/vendor/proctor-v1"
    public = ROOT / "public/static/vendor/proctor-v1"
    manifest = json.loads((app / "ASSETS.json").read_text())
    assert (app / "ASSETS.json").read_bytes() == (public / "ASSETS.json").read_bytes()
    for name, expected in manifest["files"].items():
        content = (app / name).read_bytes()
        assert len(content) == expected["bytes"], name
        assert hashlib.sha256(content).hexdigest() == expected["sha256"], name
        assert content == (public / name).read_bytes(), name
    model = json.loads((app / "model.json").read_text())
    for group in model["weightsManifest"]:
        for shard in group["paths"]:
            assert shard in manifest["files"], shard


def test_wasm_permission_is_limited_to_the_worker():
    config = json.loads((ROOT / "vercel.json").read_text())
    for entry in config["headers"]:
        for header in entry["headers"]:
            if header["key"].lower() != "content-security-policy":
                continue
            assert "'unsafe-eval'" not in header["value"]
            if "wasm-unsafe-eval" in header["value"]:
                assert entry["source"] == "/static/proctor-worker.js"
                assert "connect-src 'self'" in header["value"]
