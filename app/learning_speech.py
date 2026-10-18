"""Bounded offline eSpeak NG narration; no network requests or API quotas."""
from __future__ import annotations

import io
import os
from pathlib import Path
import re
import subprocess
import sys
import wave


def available():
    try:
        from espeakng_loader import get_library_path, get_data_path
        return Path(get_library_path()).is_file() and Path(get_data_path()).is_dir()
    except (ImportError, RuntimeError):
        return False


def enabled():
    # The old provider value is accepted during the rolling deployment only.
    return os.getenv("LEARNING_TTS_PROVIDER", "gemini") in {"espeak", "piper"}


def signature():
    return "espeak-ng-0.2.4:en:165:v1" if enabled() else "board-voice-v1"


def linux_peak_mib():
    # VmHWM measures this executable, excluding a launcher's pre-exec usage.
    status = Path("/proc/self/status").read_text(encoding="ascii")
    measured = re.search(r"^VmHWM:\s+(\d+)\s+kB$", status, re.MULTILINE)
    if not measured:
        raise RuntimeError("LOCAL_SPEECH_MEMORY_UNAVAILABLE")
    return int(measured.group(1)) / 1024


def synthesize(narration):
    if not isinstance(narration, str) or not narration.strip() or len(narration) > 8000 or "\0" in narration:
        raise ValueError("Invalid lesson narration length")
    if not available():
        raise RuntimeError("LOCAL_SPEECH_NOT_CONFIGURED")
    result = subprocess.run([sys.executable, "-m", "app.learning_speech"],
        input=narration.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=30, check=False, cwd=str(Path(__file__).resolve().parents[1]))
    if result.returncode or not 44 < len(result.stdout) <= 6 * 1024 * 1024:
        raise RuntimeError("LOCAL_SPEECH_UNAVAILABLE")
    import av
    with av.open(io.BytesIO(result.stdout)) as audio:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=24000)
        pcm = bytearray()
        for frame in audio.decode(audio=0):
            for chunk in resampler.resample(frame):
                pcm.extend(bytes(chunk.planes[0])[:chunk.samples * 2])
                if len(pcm) > 24000 * 2 * 90:
                    raise ValueError("Narration exceeds the scene duration limit")
        for chunk in resampler.resample(None):
            pcm.extend(bytes(chunk.planes[0])[:chunk.samples * 2])
    if not 24000 <= len(pcm) <= 24000 * 2 * 90:
        raise ValueError("Invalid synthesized narration duration")
    return bytes(pcm)


def main():
    import ctypes as ct
    from espeakng_loader import get_library_path, get_data_path
    text = sys.stdin.buffer.read(32001).decode("utf-8")
    if not text.strip() or len(text) > 8000 or "\0" in text:
        raise ValueError("Invalid narration")
    lib = ct.CDLL(get_library_path())
    lib.espeak_Initialize.argtypes = [ct.c_int, ct.c_int, ct.c_char_p, ct.c_int]
    lib.espeak_Initialize.restype = ct.c_int
    rate = lib.espeak_Initialize(2, 60, os.fsencode(Path(get_data_path()).parent), 0x8000)
    if not 8000 <= rate <= 48000:
        raise RuntimeError("Offline voice initialization failed")
    callback_type = ct.CFUNCTYPE(ct.c_int, ct.POINTER(ct.c_short), ct.c_int, ct.c_void_p)
    pcm = bytearray()
    overflow = False

    @callback_type
    def receive(samples, count, _events):
        nonlocal overflow
        if count < 0 or count > rate or len(pcm) + count * 2 > rate * 2 * 90:
            overflow = True
            return 1
        if samples and count:
            pcm.extend(ct.string_at(samples, count * 2))
        return 0

    lib.espeak_SetSynthCallback.argtypes = [callback_type]
    lib.espeak_SetSynthCallback(receive)
    lib.espeak_SetVoiceByName.argtypes = [ct.c_char_p]
    lib.espeak_SetParameter.argtypes = [ct.c_int, ct.c_int, ct.c_int]
    lib.espeak_Synth.argtypes = [ct.c_void_p, ct.c_size_t, ct.c_uint, ct.c_int,
                               ct.c_uint, ct.c_uint, ct.c_void_p, ct.c_void_p]
    if lib.espeak_SetVoiceByName(b"en") != 0 or lib.espeak_SetParameter(1, 165, 0) != 0:
        raise RuntimeError("Offline voice configuration failed")
    encoded = text.encode("utf-8") + b"\0"
    result = lib.espeak_Synth(encoded, len(encoded), 0, 1, 0, 1, None, None)
    lib.espeak_Terminate()
    if result != 0 or overflow or not pcm:
        raise ValueError("Offline narration could not finish within its bounds")
    if sys.platform == "linux" and linux_peak_mib() > 240:
        raise RuntimeError("Offline speech exceeds the worker memory budget")
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    sys.stdout.buffer.write(output.getvalue())


if __name__ == "__main__":
    main()
