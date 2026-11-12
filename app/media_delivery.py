"""Bounded private byte-range responses for generated learning media."""
from __future__ import annotations

import re

from fastapi import HTTPException, Request, Response


def private_media_response(data: bytes, request: Request, *, media_type: str = "video/mp4") -> Response:
    """Serve one in-memory media object with the byte ranges browsers require.

    The lesson is already authorization-checked by its router. This helper only
    handles transport and deliberately keeps generated media private/no-store.
    """
    payload = bytes(data)
    total = len(payload)
    if total <= 0:
        raise HTTPException(404, "Video is unavailable")

    range_header = request.headers.get("range")
    start, end = 0, total - 1
    if range_header:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
        if not match or not any(match.groups()):
            raise HTTPException(416, "A single byte range is required",
                                headers={"Content-Range": f"bytes */{total}"})
        first, last = match.groups()
        if first:
            start = int(first)
            end = min(int(last) if last else total - 1, total - 1)
        else:
            suffix = int(last)
            if suffix <= 0:
                raise HTTPException(416, "The requested range is unavailable",
                                    headers={"Content-Range": f"bytes */{total}"})
            start = max(0, total - suffix)
        if start > end or start >= total:
            raise HTTPException(416, "The requested range is unavailable",
                                headers={"Content-Range": f"bytes */{total}"})

    body = payload[start:end + 1]
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, no-store",
        "Content-Disposition": "inline",
        "Content-Length": str(len(body)),
        "X-Content-Type-Options": "nosniff",
    }
    status_code = 200
    if range_header:
        status_code = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
    return Response(body, status_code=status_code, media_type=media_type, headers=headers)
