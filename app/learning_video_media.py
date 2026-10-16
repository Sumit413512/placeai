"""Bounded narration and deterministic slides encoded with the existing PyAV runtime."""
from __future__ import annotations

import base64
import io
import logging
import math
import os
import time
import wave
from fractions import Fraction
from pathlib import Path

import httpx

from app import ai_provider

LOGGER = logging.getLogger("placeai.learning.video.media")
RATE = 24000
MAX_VIDEO_BYTES = 3 * 1024 * 1024
MAX_AUDIO_BYTES = 6 * 1024 * 1024


def _response_bytes(response, limit):
    response.raise_for_status()
    data = bytearray()
    for chunk in response.iter_bytes():
        data.extend(chunk)
        if len(data) > limit:
            raise ValueError("Narration response exceeds the lesson limit")
    return bytes(data)


def _pcm(data):
    with wave.open(io.BytesIO(data), "rb") as audio:
        if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, RATE):
            raise ValueError("Narration must be mono 24kHz PCM16 WAV")
        frames = audio.readframes(RATE * 91)
    if not RATE <= len(frames) <= RATE * 2 * 90:
        raise ValueError("Narration duration is outside the scene limit")
    return frames


def quota_delay(response):
    """Respect a bounded provider retry hint; daily/zero quotas need account action."""
    import json
    try:
        data = bytearray()
        for chunk in response.iter_bytes():
            data.extend(chunk)
            if len(data) > 65536:
                return None
        details = json.loads(data).get('error', {}).get('details', [])
        for detail in details:
            for violation in detail.get('violations', []):
                if 'perday' in str(violation.get('quotaId','')).lower() or str(violation.get('quotaValue')) == '0':
                    return None
        hints = [detail.get('retryDelay') for detail in details if detail.get('retryDelay')]
        delay = float(str(hints[0]).removesuffix('s')) if hints else float(response.headers.get('retry-after', 30))
        return max(1, min(delay + 1, 60))
    except (ValueError, TypeError, KeyError):
        return 30


def speak(narration):
    """Only the approved lesson transcript is sent to speech providers, never identity data."""
    key = ai_provider._gemini_key()
    if key:
        try:
            import json
            for attempt in range(3):
                try:
                    with httpx.stream("POST", "https://generativelanguage.googleapis.com/v1beta/interactions",
                        headers={"x-goog-api-key": key}, timeout=60,
                        json={"model": os.getenv("LEARNING_TTS_GEMINI_MODEL", "gemini-3.8-flash-lite-tts"),
                              "input": [{"type": "user_input", "content": [{"type": "text", "text": narration,
                                  "annotations": [{"type": "speech_metadata", "style": "Clear, calm educational narration"}]}]}],
                              "response_format": {"type": "audio"}, "store": False,
                              "generation_config": {"speech_config": [{"voice": "Kore"}]}}) as response:
                        if response.status_code == 429 and attempt < 2:
                            delay = quota_delay(response)
                            if delay is not None:
                                LOGGER.info("Video narration waiting for provider quota retry_seconds=%s", delay)
                                time.sleep(delay)
                                continue
                        if response.status_code in {500, 502, 503, 504} and attempt < 2:
                            time.sleep(2 ** attempt)
                            continue
                        payload = json.loads(_response_bytes(response, MAX_AUDIO_BYTES * 2))
                        break
                except httpx.TransportError:
                    if attempt == 2:
                        raise
                    time.sleep(2 ** attempt)
            for step in reversed(payload.get("steps", [])):
                if step.get("type") == "model_output":
                    for item in reversed(step.get("content", [])):
                        if item.get("type") == "audio" and item.get("data"):
                            return _pcm(base64.b64decode(item["data"], validate=True))
            raise ValueError("Narration provider returned no audio")
        except Exception as error:
            LOGGER.warning("Video narration unavailable provider=gemini error_type=%s status=%s",
                           type(error).__name__, getattr(getattr(error, "response", None), "status_code", None))
    for key in ai_provider._openai_keys():
        try:
            with httpx.stream("POST", "https://api.openai.com/v1/audio/speech", timeout=100,
                headers={"Authorization": f"Bearer {key}"},
                json={"model": os.getenv("LEARNING_TTS_OPENAI_MODEL", "tts-1"), "voice": "alloy",
                      "input": narration, "response_format": "wav"}) as response:
                return _pcm(_response_bytes(response, MAX_AUDIO_BYTES))
        except Exception as error:
            LOGGER.warning("Video narration unavailable provider=openai error_type=%s status=%s",
                           type(error).__name__, getattr(getattr(error, "response", None), "status_code", None))
    raise RuntimeError("VIDEO_NARRATION_UNAVAILABLE")


def _font(size, mono=False):
    import reportlab
    from PIL import ImageFont
    return ImageFont.truetype(str(Path(reportlab.__file__).parent / "fonts" /
                                  "Vera.ttf"), size)


def _lines(text, font, width):
    lines = []
    for paragraph in text.splitlines() or [""]:
        line = ""
        for word in paragraph.split():
            candidate = (line + " " + word).strip()
            if font.getlength(candidate) > width:
                if not line:
                    raise ValueError("Unbreakable slide text exceeds its column")
                lines.append(line)
                line = word
                if font.getlength(line) > width:
                    raise ValueError("Unbreakable slide text exceeds its column")
            else:
                line = candidate
        lines.append(line)
    return lines


def slide(scene, number, total):
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (960, 540), "#f7f9fc")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 12, 540), fill="#2563eb")
    draw.text((44, 24), "PlaceAI  /  Learning Hub", font=_font(18), fill="#475569")
    y = 72
    for line in _lines(scene["title"], _font(30), 870):
        draw.text((44, y), line, font=_font(30), fill="#172554"); y += 38
    y += 14
    for point in scene["bullets"]:
        for line in _lines(point, _font(23), 850):
            draw.text((52, y), line, font=_font(23), fill="#1e293b"); y += 30
        y += 8
    if scene.get("code"):
        y += 6
        for line in scene["code"].splitlines():
            draw.text((52, y), line, font=_font(19, True), fill="#1e40af"); y += 27
    if scene.get("diagram"):
        diagram = scene["diagram"]
        labels = {node["id"]: node["label"] for node in diagram["nodes"]}
        y += 6
        for edge in diagram["edges"]:
            left = _lines(labels[edge['source']], _font(18), 350)
            right = _lines(labels[edge['target']], _font(18), 350)
            height = max(48, max(len(left), len(right)) * 23 + 10)
            for x, lines in ((52, left), (540, right)):
                draw.rounded_rectangle((x, y, x + 365, y + height), radius=6,
                                       fill="#eff6ff", outline="#93c5fd", width=1)
                for offset, line in enumerate(lines):
                    draw.text((x + 8, y + 5 + offset * 23), line, font=_font(18), fill="#1e40af")
            middle = y + height // 2
            draw.line((425, middle, 530, middle), fill="#2563eb", width=2)
            draw.polygon(((530, middle), (520, middle-5), (520, middle+5)), fill="#2563eb")
            y += height + 3
            if edge.get("label"):
                for line in _lines(edge["label"], _font(14), 850):
                    draw.text((65, y), line, font=_font(14), fill="#475569"); y += 19
            y += 8
    if y > 488:
        raise ValueError("Slide content exceeds its safe area; shorten the scene")
    draw.line((44, 505, 916, 505), fill="#cbd5e1", width=1)
    draw.text((44, 515), "AI-generated lesson • Examples are illustrative", font=_font(14), fill="#475569")
    draw.text((840, 515), f"{number} / {total}", font=_font(14), fill="#475569")
    return image


def render_video(script, narrate=speak):
    """One scene at a time: bounded RAM, one encoding thread and exact scene boundaries."""
    import av
    output = io.BytesIO()
    deadline = time.monotonic() + 600
    timings = []
    # Playback fetches the bounded file as an authenticated blob, so an end-of-file
    # moov atom is safe and avoids FFmpeg's filesystem-only faststart rewrite.
    with av.open(output, "w", format="mp4") as container:
        video = container.add_stream("libx264", rate=1)
        video.width, video.height, video.pix_fmt = 960, 540, "yuv420p"
        video.codec_context.thread_count = 1
        video.options = {"preset": "ultrafast", "crf": "28", "tune": "stillimage"}
        audio = container.add_stream("aac", rate=RATE)
        audio.layout, audio.bit_rate = "mono", 48000
        resampler = av.AudioResampler(format="fltp", layout="mono", rate=RATE)
        seconds, samples = 0, 0
        for index, scene in enumerate(script["scenes"]):
            if time.monotonic() > deadline:
                raise RuntimeError("VIDEO_RENDER_DEADLINE")
            image = slide(scene, index + 1, len(script["scenes"]))
            pcm = narrate(scene["narration"])
            duration = math.ceil(len(pcm) / (RATE * 2))
            if duration < 1 or duration > 90 or seconds + duration > 480:
                raise ValueError("Lesson duration exceeds the rendering limit")
            pcm = pcm.ljust(duration * RATE * 2, b"\0")
            timings.append({"start": seconds, "end": seconds + duration})
            for offset in range(duration):
                frame = av.VideoFrame.from_image(image)
                frame.pts, frame.time_base = seconds + offset, Fraction(1, 1)
                for packet in video.encode(frame):
                    container.mux(packet)
                start = offset * RATE * 2
                for pos in range(start, start + RATE * 2, 2048):
                    chunk = pcm[pos:min(pos + 2048, start + RATE * 2)]
                    frame_audio = av.AudioFrame(format="s16", layout="mono", samples=len(chunk) // 2)
                    frame_audio.sample_rate, frame_audio.pts = RATE, samples
                    frame_audio.time_base = Fraction(1, RATE)
                    frame_audio.planes[0].update(chunk)
                    samples += len(chunk) // 2
                    for converted in resampler.resample(frame_audio):
                        for packet in audio.encode(converted):
                            container.mux(packet)
            seconds += duration
            if output.tell() > MAX_VIDEO_BYTES:
                raise ValueError("Lesson file exceeds its storage limit")
        for converted in resampler.resample(None):
            for packet in audio.encode(converted):
                container.mux(packet)
        for stream in (video, audio):
            for packet in stream.encode(None):
                container.mux(packet)
    data = output.getvalue()
    if len(data) > MAX_VIDEO_BYTES:
        raise ValueError("Lesson file exceeds its storage limit")
    return data, seconds, timings


def captions(content):
    """Readable automatic cues, estimated within measured per-scene audio boundaries."""
    def stamp(seconds):
        value = int(seconds * 1000)
        return f"{value // 3600000:02}:{value // 60000 % 60:02}:{value // 1000 % 60:02}.{value % 1000:03}"
    rows = ["WEBVTT", ""]
    for scene, timing in zip(content["scenes"], content["timings"]):
        # Native captions render plain text; neutralise VTT markup/control delimiters.
        import html
        chunks, current = [], ""
        for word in scene["narration"].split():
            if current and len(current) + len(word) + 1 > 80:
                chunks.append(current); current = ""
            current = (current + " " + word).strip()
        if current:
            chunks.append(current)
        weight = sum(len(chunk) for chunk in chunks) or 1
        elapsed = 0
        for chunk in chunks:
            start = timing["start"] + (timing["end"] - timing["start"]) * elapsed / weight
            elapsed += len(chunk)
            end = timing["start"] + (timing["end"] - timing["start"]) * elapsed / weight
            rows.extend([f"{stamp(start)} --> {stamp(end)}", html.escape(chunk), ""])
    return "\n".join(rows)
