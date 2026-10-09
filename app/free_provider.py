"""Opt-in Groq pilot client. No paid/provider fallback or persistent remote files.

Activation requires a server-side key and explicit approval of this processor.
Account retention settings and free-tier status must be verified before rollout.
"""
from __future__ import annotations

import json
import logging
import math
import os

import httpx

BASE = "https://api.groq.com/openai/v1/"
TEXT_MODEL = "openai/gpt-oss-120b"
VISION_MODEL = "qwen/qwen3.8-27b"
AUDIO_MODEL = "whisper-large-v3"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
LOGGER = logging.getLogger(__name__)


def _invalid_transcript(reason):
    # Log a fixed diagnostic category, never the transcript or provider payload.
    LOGGER.warning("Transcription validation failed reason=%s", reason)
    raise ProviderError("FREE_PROVIDER_INVALID_TRANSCRIPT")

LOCAL_ERROR_STATUS = {
    "FREE_PROVIDER_NOT_CONFIGURED": 503,
    "FREE_PROVIDER_NETWORK": 503,
    "FREE_PROVIDER_RESPONSE_TOO_LARGE": 502,
    "FREE_PROVIDER_INVALID_RESPONSE": 502,
    "FREE_PROVIDER_INCOMPLETE_RESPONSE": 504,
    "FREE_PROVIDER_INVALID_TRANSCRIPT": 500,
    "FREE_PROVIDER_INPUT_LIMIT": 422,
}


class ProviderError(RuntimeError):
    def __init__(self, reason: str, code: int | None = None):
        super().__init__(reason)
        self.code = code if code is not None else LOCAL_ERROR_STATUS.get(reason)


def configured():
    return (os.getenv("GROQ_PROCESSING_APPROVED", "false").lower() == "true"
            and bool(os.getenv("GROQ_API_KEY", "").strip()))


def _request(endpoint, *, timeout=45, **kwargs):
    if not configured():
        raise ProviderError("FREE_PROVIDER_NOT_CONFIGURED")
    # Fixed destination, no redirects, no request/response/credential logging.
    # Quota failure is returned immediately for durable recovery, never retried
    # by changing accounts, purchasing credits or silently using a paid API.
    limits = httpx.Timeout(max(5, min(float(timeout), 55)), connect=5, write=15, pool=5)
    try:
        with httpx.Client(timeout=limits, follow_redirects=False) as client:
            with client.stream("POST", BASE + endpoint,
                               headers={"Authorization": "Bearer " + os.environ["GROQ_API_KEY"].strip()}, **kwargs) as response:
                if response.status_code != 200:
                    raise ProviderError("FREE_PROVIDER_REJECTED", response.status_code)
                data = bytearray()
                for chunk in response.iter_bytes():
                    if len(data) + len(chunk) > MAX_RESPONSE_BYTES:
                        raise ProviderError("FREE_PROVIDER_RESPONSE_TOO_LARGE")
                    data.extend(chunk)
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ProviderError("FREE_PROVIDER_INVALID_RESPONSE")
        return value
    except httpx.HTTPError as error:
        raise ProviderError("FREE_PROVIDER_NETWORK") from error
    except (ValueError, UnicodeError) as error:
        raise ProviderError("FREE_PROVIDER_INVALID_RESPONSE") from error


def text(prompt, *, max_output_tokens=3000, timeout=45, schema=None, images=None):
    if not isinstance(prompt, str) or not prompt or len(prompt) > 80000:
        raise ProviderError("FREE_PROVIDER_INPUT_LIMIT")
    if images:
        if len(images) > 3 or any(not isinstance(image, str) or
                                 not image.startswith(("data:image/jpeg;base64,", "data:image/png;base64,"))
                                 or len(image) > 2 * 1024 * 1024 for image in images):
            raise ProviderError("FREE_PROVIDER_INPUT_LIMIT")
        content = [{"type": "text", "text": prompt}] + [
            {"type": "image_url", "image_url": {"url": image}} for image in images]
    else:
        content = prompt
    payload = {"model": VISION_MODEL if images else TEXT_MODEL,
               "messages": [{"role": "user", "content": content}],
               "max_completion_tokens": max(256, min(int(max_output_tokens), 8000)),
               "reasoning_effort": "none" if images else "low", "stream": False}
    if schema is not None:
        payload["response_format"] = {"type": "json_schema", "json_schema": {
            "name": "placeai_result", "strict": True, "schema": schema}}
    response = _request("chat/completions", json=payload, timeout=timeout)
    try:
        choice = response["choices"][0]
        result = choice["message"]["content"]
        if choice.get("finish_reason") != "stop" or not isinstance(result, str) or not result.strip():
            raise ProviderError("FREE_PROVIDER_INCOMPLETE_RESPONSE")
        return result.strip()
    except (KeyError, IndexError, TypeError) as error:
        raise ProviderError("FREE_PROVIDER_INVALID_RESPONSE") from error


def transcribe(data: bytes, mime_type: str):
    if mime_type not in {"audio/webm", "video/webm", "audio/mp4", "video/mp4"} or not 0 < len(data) <= 25 * 1024 * 1024:
        raise ProviderError("FREE_PROVIDER_INPUT_LIMIT")
    suffix = "webm" if mime_type.endswith("webm") else "mp4"
    response = _request("audio/transcriptions", files={"file": ("answer." + suffix, data, mime_type)},
                        data={"model": AUDIO_MODEL, "response_format": "verbose_json", "temperature": "0",
                              "timestamp_granularities[]": ["segment", "word"]}, timeout=55)
    segments = response.get("segments")
    duration = response.get("duration")
    if (not isinstance(response.get("text"), str) or len(response["text"]) > 60000
            or not isinstance(duration, (int, float)) or not 0 < duration <= 610
            or not isinstance(segments, list) or len(segments) > 1000):
        _invalid_transcript("response_shape")
    previous = 0
    for segment in segments:
        if (not isinstance(segment, dict) or not isinstance(segment.get("text"), str)
                or not isinstance(segment.get("start"), (int, float))
            or not isinstance(segment.get("end"), (int, float))
                or not math.isfinite(segment["start"]) or not math.isfinite(segment["end"])
                or not previous <= segment["start"] <= segment["end"]):
            _invalid_transcript("segment_shape_or_bounds")
        previous = segment["start"]
    # Whisper segment windows can extend beyond the media duration. Segments
    # describe confidence metadata; word timestamps remain the scoring evidence
    # and are independently checked against duration below.
    response["segments"] = [
        {**segment, "end": min(segment["end"], duration)}
        for segment in segments if segment["start"] < duration
    ]
    words = response.get("words", [])
    if not isinstance(words, list) or len(words) > 10000 or (response["text"].strip() and not words):
        _invalid_transcript("missing_word_timestamps")
    for word in words:
        if (not isinstance(word, dict) or not isinstance(word.get("word"), str)
                or not isinstance(word.get("start"), (int, float))
                or not isinstance(word.get("end"), (int, float))
                or not 0 <= word["start"] <= word["end"] <= duration):
            _invalid_transcript("word_shape_or_bounds")
    return response
