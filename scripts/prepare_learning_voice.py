"""Fetch the pinned public-domain-training voice at build time, never during a request."""
import hashlib
from pathlib import Path
import sys
import subprocess
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.learning_speech import model_path, VOICE_NAME, VOICE_REVISION, MODEL_SHA256, CONFIG_SHA256  # noqa: E402


def prepare():
    path = model_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    base = f"https://huggingface.co/rhasspy/piper-voices/resolve/{VOICE_REVISION}/en/en_GB/cori/medium/"
    for suffix, expected in (("", MODEL_SHA256), (".json", CONFIG_SHA256)):
        target = Path(str(path) + suffix)
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == expected:
            continue
        temp = Path(str(target) + ".download")
        digest = hashlib.sha256()
        try:
            with httpx.stream("GET", base + VOICE_NAME + ".onnx" + suffix, follow_redirects=True, timeout=120) as response, temp.open("wb") as out:
                response.raise_for_status()
                total = 0
                for chunk in response.iter_bytes(1024 * 1024):
                    total += len(chunk)
                    if total > 70 * 1024 * 1024:
                        raise ValueError("Voice artifact exceeds its limit")
                    digest.update(chunk); out.write(chunk)
            if digest.hexdigest() != expected:
                raise ValueError("Voice artifact checksum mismatch")
            temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)
    print("Pinned offline lesson voice verified")
    subprocess.run([sys.executable, "-m", "app.learning_speech", "--prepare-runtime"],
                   check=True, timeout=120, cwd=str(Path(__file__).resolve().parents[1]))


if __name__ == "__main__":
    prepare()
    if "--verify" in sys.argv[1:]:
        from app.learning_speech import synthesize
        from app.learning_video_media import render_video, inspect_video
        narration = ("SQL joins connect related tables and let us inspect matching records while preserving "
            "the intended relationship between customers and orders using explicit join conditions "
            "and carefully checking the resulting rows for missing or repeated values.")
        pcm = synthesize(narration)
        content = {"scenes": [{"title": "Connect related tables", "narration": narration,
            "bullets": ["Check the join condition", "Inspect the resulting rows"], "code": "", "diagram": None}]}
        data, duration, timings = render_video(content, narrate=lambda _text: pcm)
        content["timings"] = timings
        if not inspect_video(data, content, duration)["passed"]:
            raise RuntimeError("Offline speech build verification failed")
        print(f"Offline speech and synchronized MP4 verified: {duration:.1f}s")
