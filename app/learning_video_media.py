"""Bounded narration and deterministic slides encoded with the existing PyAV runtime."""
from __future__ import annotations

import base64
import io
import logging
import math
import os
import re
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
FPS = 8


class NarrationCapacityError(RuntimeError):
    def __init__(self, retry_seconds=3600):
        super().__init__("VIDEO_NARRATION_CAPACITY")
        self.retry_seconds = max(60, min(int(retry_seconds), 86400))


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
        error = json.loads(data).get('error', {})
        details = error.get('details', [])
        message = str(error.get('message', '')).lower()
        if 'requests per day' in message or 'daily quota' in message:
            match = re.search(r'retry in\s+(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?', message)
            seconds = sum(int(value or 0) * scale for value, scale in zip(match.groups(), (3600, 60, 1))) if match else 86400
            response.extensions['video_retry_seconds'] = seconds + 60
            return None
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
    capacity = None
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
                        if response.status_code == 429:
                            delay = quota_delay(response)
                            if delay is None:
                                # The provider may return a plain message rather than RetryInfo.
                                # Fail promptly and keep already generated scene audio in the DB.
                                raise NarrationCapacityError(response.extensions.get('video_retry_seconds', 86400))
                            if attempt < 2:
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
            if isinstance(error, NarrationCapacityError):
                capacity = error
            LOGGER.warning("Video narration unavailable provider=gemini error_type=%s status=%s",
                           type(error).__name__, getattr(getattr(error, "response", None), "status_code", None))
    # Free mode never silently opts the operator into paid speech.
    for key in (ai_provider._openai_keys() if os.getenv("LEARNING_TTS_ALLOW_PAID_FALLBACK") == "true" else []):
        try:
            with httpx.stream("POST", "https://api.openai.com/v1/audio/speech", timeout=100,
                headers={"Authorization": f"Bearer {key}"},
                json={"model": os.getenv("LEARNING_TTS_OPENAI_MODEL", "tts-1"), "voice": "alloy",
                      "input": narration, "response_format": "wav"}) as response:
                return _pcm(_response_bytes(response, MAX_AUDIO_BYTES))
        except Exception as error:
            LOGGER.warning("Video narration unavailable provider=openai error_type=%s status=%s",
                           type(error).__name__, getattr(getattr(error, "response", None), "status_code", None))
    if capacity:
        raise capacity
    raise RuntimeError("VIDEO_NARRATION_UNAVAILABLE")


def _font(size, mono=False):
    import reportlab
    from PIL import ImageFont
    font = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
    # ReportLab does not bundle a mono face on every host; use a known system face
    # where available, without downloading assets at runtime.
    if mono:
        for candidate in (Path("C:/Windows/Fonts/consola.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")):
            if candidate.is_file():
                font = candidate; break
    return ImageFont.truetype(str(font), size)


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


def board_frame(scene, number, total, phase, base=None):
    """Animated board reveal and instructor pointer on the measured narration timeline.

    Scene boundaries follow actual speech duration. Within-scene drawing is a visual
    aid, not a claim of word alignment or a recording of a human instructor.
    """
    from PIL import ImageDraw
    image = (base or slide(scene, number, total)).copy()
    draw = ImageDraw.Draw(image)
    # Keep whole labels readable: reveal complete board rows, never half-cut text.
    y = 72 + len(_lines(scene['title'], _font(30), 870)) * 38 + 14
    rows = [y - 2]
    for point in scene['bullets']:
        y += len(_lines(point, _font(23), 850)) * 30 + 8
        rows.append(y + 3)
    if scene.get('code'):
        y += 6
        for _line in scene['code'].splitlines():
            y += 27; rows.append(y + 3)
    if scene.get('diagram'):
        labels = {node['id']:node['label'] for node in scene['diagram']['nodes']}
        y += 6
        for edge in scene['diagram']['edges']:
            height = max(48, max(len(_lines(labels[edge['source']],_font(18),350)),
                                len(_lines(labels[edge['target']],_font(18),350))) * 23 + 10)
            y += height + 3 + len(_lines(edge.get('label',''),_font(14),850)) * 19 + 8
            rows.append(y + 3)
    step = min(len(rows)-1, int(phase / .65 * len(rows)))
    bottom = min(488, rows[step])
    if step < len(rows)-1:
        draw.rectangle((42, bottom, 920, 488), fill="#f7f9fc")
    # Instructor audio activity and a board pointer follow actual scene duration.
    draw.rounded_rectangle((755, 20, 916, 53), radius=8, fill="#e8efff")
    draw.text((767, 27), "AI tutor", font=_font(16), fill="#1e40af")
    for index in range(5):
        height = 4 + int(abs(math.sin(phase * 95 + index * .8)) * 13)
        x = 852 + index * 10
        draw.line((x, 37-height//2, x, 37+height//2), fill="#2563eb", width=3)
    pointer_y = min(481, bottom-8)
    draw.ellipse((20, pointer_y-4, 28, pointer_y+4), fill="#2563eb")
    draw.line((28, pointer_y, 39, pointer_y), fill="#2563eb", width=2)
    draw.line((44, 499, 44 + int(872 * phase), 499), fill="#2563eb", width=3)
    return image


def render_video(script, narrate=speak):
    """One scene at a time: bounded RAM, one encoding thread and exact scene boundaries."""
    import av
    output = io.BytesIO()
    deadline = time.monotonic() + 900
    timings = []
    # Playback fetches the bounded file as an authenticated blob, so an end-of-file
    # moov atom is safe and avoids FFmpeg's filesystem-only faststart rewrite.
    with av.open(output, "w", format="mp4") as container:
        video = container.add_stream("libx264", rate=FPS)
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
            for tick in range(duration * FPS):
                if time.monotonic() > deadline:
                    raise RuntimeError("VIDEO_RENDER_DEADLINE")
                animated = board_frame(scene, index + 1, len(script["scenes"]), tick / max(1, duration * FPS - 1), image)
                frame = av.VideoFrame.from_image(animated)
                frame.pts, frame.time_base = seconds * FPS + tick, Fraction(1, FPS)
                for packet in video.encode(frame):
                    container.mux(packet)
                if tick % FPS:
                    continue
                offset = tick // FPS
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


def inspect_video(data, content, duration):
    """Decode the actual output before publishing, using the shared media clock.

    This detects broken/truncated media, silent output, missing frames and timeline
    drift. It is not a claim of word-level alignment or independent fact checking.
    """
    import av
    import hashlib
    if not data or len(data) > MAX_VIDEO_BYTES or not 0 < duration <= 480:
        raise ValueError("Video exceeds its validated media bounds")
    timings = content.get("timings", [])
    if len(timings) != len(content.get("scenes", [])) or not timings:
        raise ValueError("Every scene needs a measured audio boundary")
    end = 0
    for timing in timings:
        if timing["start"] != end or timing["end"] <= end:
            raise ValueError("Scene boundaries must be contiguous and increasing")
        end = timing["end"]
    if abs(end - duration) > 1 / FPS:
        raise ValueError("Scene boundaries do not cover the video")
    tracks, audible = {}, False
    for kind in ("video", "audio"):
        with av.open(io.BytesIO(data)) as container:
            streams = [stream for stream in container.streams if stream.type == kind]
            if len(streams) != 1:
                raise ValueError("A lesson needs one video and one audio track")
            stream = streams[0]
            count, previous, finish = 0, -1, 0
            pcm_check = av.AudioResampler(format="s16", layout="mono", rate=RATE) if kind == "audio" else None
            for frame in container.decode(stream):
                if frame.pts is None:
                    raise ValueError("Media timestamps are missing")
                stamp = float(frame.pts * frame.time_base)
                if stamp <= previous or stamp < 0:
                    raise ValueError("Media timestamps must increase")
                if kind == "video":
                    if frame.width != 960 or frame.height != 540 or abs(stamp-count/FPS) > .002:
                        raise ValueError("Video frames do not match the presentation clock")
                    finish = stamp + 1 / FPS
                else:
                    if abs(stamp - finish) > .002:
                        raise ValueError("The audio track contains a timestamp gap")
                    # Inspect native PCM planes; ndarray conversion silently adds
                    # an optional NumPy dependency absent from production.
                    for pcm_frame in pcm_check.resample(frame):
                        audible = audible or any(bytes(pcm_frame.planes[0])[:pcm_frame.samples * 2])
                    finish = stamp + frame.samples / frame.sample_rate
                count += 1
                previous = stamp
            if not count or abs(finish - duration) > .05:
                raise ValueError("A media track is incomplete or out of sync")
            tracks[kind] = {"frames": count, "end_seconds": round(finish, 6)}
    if not audible:
        raise ValueError("Silent lessons cannot be published")
    if abs(tracks["video"]["end_seconds"] - tracks["audio"]["end_seconds"]) > .05:
        raise ValueError("Audio and video timelines have drifted")
    return {"passed": True, "version": 1, "sha256": hashlib.sha256(data).hexdigest(),
            "tracks": tracks, "scene_boundaries": len(timings),
            "timing_scope": "Measured scene boundaries; within-scene timing is estimated"}


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
