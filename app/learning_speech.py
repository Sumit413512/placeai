"""Offline lesson narration. No external speech requests, keys or student data."""
from __future__ import annotations

import io
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import wave

MODEL_SHA256 = "1899f98e5fb8310154f3c2973f4b8a929ba7245e722b3d3a85680b833d95f10d"
CONFIG_SHA256 = "e262c16d7f192f69d4edd6b4ef8a5915379e67495fcc402f1ab15eeb33da3d36"
VOICE_REVISION = "c10ece1aade47bb51c153c893d14e5bf8e5b7117"
VOICE_NAME = "en_GB-cori-medium"


def model_path():
    return Path(os.getenv("LEARNING_LOCAL_VOICE_PATH") or
                Path(__file__).resolve().parents[1] / ".cache" / "placeai-voice" / (VOICE_NAME + ".onnx"))


def available():
    path = model_path()
    return path.is_file() and Path(str(path) + ".json").is_file()


def enabled():
    return os.getenv("LEARNING_TTS_PROVIDER", "gemini") == "piper"


def signature():
    return "piper-cori-2:" + MODEL_SHA256 if enabled() else "board-voice-v1"


def narration_chunks(text):
    """Bound neural inference activations, including long unpunctuated sentences."""
    for sentence in re.split(r"(?<=[.!?;:])\s+", text.strip()):
        words = sentence.split()
        for start in range(0, len(words), 12):
            yield " ".join(words[start:start + 12])


def synthesize(narration):
    if not isinstance(narration, str) or not narration.strip() or len(narration) > 8000:
        raise ValueError("Invalid lesson narration length")
    if not available():
        raise RuntimeError("LOCAL_SPEECH_NOT_CONFIGURED")
    # A bounded child releases native model memory before video rendering starts.
    # User text is stdin data; it is never a shell command or command-line option.
    result = subprocess.run([sys.executable, "-m", "app.learning_speech"],
        input=narration.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=90, check=False, cwd=str(Path(__file__).resolve().parents[1]))
    if result.returncode or not 44 < len(result.stdout) <= 6 * 1024 * 1024:
        raise RuntimeError("LOCAL_SPEECH_UNAVAILABLE")
    import av
    with av.open(io.BytesIO(result.stdout)) as audio:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=24000)
        pcm = bytearray()
        for frame in audio.decode(audio=0):
            for chunk in resampler.resample(frame):
                pcm.extend(chunk.to_ndarray().tobytes())
                if len(pcm) > 24000 * 2 * 90:
                    raise ValueError("Narration exceeds the scene duration limit")
        for chunk in resampler.resample(None):
            pcm.extend(chunk.to_ndarray().tobytes())
    if not 24000 <= len(pcm) <= 24000 * 2 * 90:
        raise ValueError("Invalid synthesized narration duration")
    return bytes(pcm)


def main():
    import onnxruntime
    from piper import PiperVoice
    from piper.config import PiperConfig
    text = sys.stdin.buffer.read(32001).decode("utf-8")
    if not text.strip() or len(text) > 8000:
        raise ValueError("Invalid narration")
    path = model_path()
    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.enable_cpu_mem_arena = False
    options.enable_mem_pattern = False
    options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_DISABLE_ALL
    voice = PiperVoice(config=PiperConfig.from_dict(json.loads(Path(str(path)+".json").read_text(encoding="utf-8"))),
        session=onnxruntime.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"]))
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        for index, chunk in enumerate(narration_chunks(text)):
            voice.synthesize_wav(chunk, wav, set_wav_format=index == 0)
    if sys.platform == "linux":
        import resource
        peak_mib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        if peak_mib > 240:
            raise RuntimeError("Offline voice exceeds the worker memory budget")
        print(f"Offline voice peak memory: {peak_mib:.1f} MiB", file=sys.stderr)
    sys.stdout.buffer.write(output.getvalue())


if __name__ == "__main__":
    main()
