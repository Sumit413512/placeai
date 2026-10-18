"""Verify packaged offline speech and a synchronized MP4 during the Render build."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.learning_speech import available, synthesize  # noqa: E402

if __name__ == "__main__":
    if not available():
        raise RuntimeError("Packaged offline speech library/data are missing")
    print("Packaged offline speech library and data verified")
    if "--verify" in sys.argv[1:]:
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
