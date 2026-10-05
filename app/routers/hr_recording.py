from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app import hr_video
from app.database import get_db
from app.dependencies import get_current_user, require_student
from app.models import HRVideoChunk, User

router = APIRouter(prefix="/mock-interview", tags=["HR video"])


class RecordingStart(BaseModel):
    mime_type: str = Field(pattern="^video/(webm|mp4)$")
    consent: bool


class RecordingAdvance(BaseModel):
    question_id: int = Field(ge=1, le=50)


class RecordingSubmit(BaseModel):
    chunks: int = Field(ge=1, le=hr_video.MAX_CHUNKS)


@router.post("/{interview_id}/hr/exam-start")
def exam_start(interview_id: str, user: User = Depends(require_student), db: Session = Depends(get_db)):
    row, interview = hr_video.owned_recording(db, user, interview_id, lock=True)
    return hr_video.start_exam(db, row, interview)


@router.post("/{interview_id}/hr/start")
def start(interview_id: str, body: RecordingStart, user: User = Depends(require_student), db: Session = Depends(get_db)):
    row, interview = hr_video.owned_recording(db, user, interview_id, lock=True)
    return hr_video.begin_recording(db, row, interview, body.mime_type, body.consent)


@router.post("/{interview_id}/hr/advance")
def advance(interview_id: str, body: RecordingAdvance, user: User = Depends(require_student), db: Session = Depends(get_db)):
    row, interview = hr_video.owned_recording(db, user, interview_id, lock=True)
    return hr_video.advance_question(db, row, interview, body.question_id)


@router.put("/{interview_id}/hr/chunks/{sequence}")
async def upload(interview_id: str, sequence: int, request: Request, user: User = Depends(require_student), db: Session = Depends(get_db)):
    # Database calls are synchronous. Never block the event loop while hundreds
    # of students stream recordings; release the read transaction before upload.
    await run_in_threadpool(hr_video.owned_recording, db, user, interview_id)
    await run_in_threadpool(db.rollback)
    if not 0 <= sequence < hr_video.MAX_CHUNKS:
        raise HTTPException(413, "Recording chunk exceeds the allowed size")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > hr_video.CHUNK_BYTES:
            raise HTTPException(413, "Recording chunk exceeds the allowed size")
        data.extend(chunk)
    def persist():
        row, interview = hr_video.owned_recording(db, user, interview_id, lock=True)
        return hr_video.save_chunk(db, row, interview, sequence, bytes(data))
    return await run_in_threadpool(persist)


@router.post("/{interview_id}/hr/submit")
def submit(interview_id: str, body: RecordingSubmit, user: User = Depends(require_student), db: Session = Depends(get_db)):
    row, _ = hr_video.owned_recording(db, user, interview_id, lock=True)
    return hr_video.seal_recording(db, row, body.chunks)


@router.get("/{interview_id}/hr/status")
def status(interview_id: str, user: User = Depends(require_student), db: Session = Depends(get_db)):
    row, _ = hr_video.owned_recording(db, user, interview_id)
    return hr_video.recording_status(row)


@router.get("/{interview_id}/hr/recording")
def recording(interview_id: str, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row, _ = hr_video.owned_recording(db, user, interview_id, reviewer=True)
    if row.expires_at <= hr_video.utcnow():
        raise HTTPException(410, "This HR recording has expired")
    if not row.sealed_at:
        raise HTTPException(409, "This HR recording has not been submitted")
    total = row.size_bytes
    if not 0 < total <= hr_video.MAX_BYTES:
        raise HTTPException(409, "The saved HR recording is incomplete")
    range_header = request.headers.get("range")
    start, end = 0, min(total, hr_video.PLAYBACK_BYTES) - 1
    if range_header:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
        if not match or not any(match.groups()):
            raise HTTPException(416, "A single byte range is required", headers={"Content-Range": f"bytes */{total}"})
        first, last = match.groups()
        if first:
            start = int(first)
            end = min(int(last) if last else total - 1, total - 1)
        else:
            start, end = max(0, total - int(last)), total - 1
        if start > end or start >= total:
            raise HTTPException(416, "The requested range is unavailable", headers={"Content-Range": f"bytes */{total}"})
        end = min(end, start + hr_video.PLAYBACK_BYTES - 1)
    # Read only chunks intersecting this bounded response. Full recordings can exceed
    # the serverless response limit, and must never be assembled into one response.
    sizes = db.query(HRVideoChunk.sequence, func.length(HRVideoChunk.data)).filter(
        HRVideoChunk.recording_id == row.id,
    ).order_by(HRVideoChunk.sequence).all()
    if len(sizes) != row.chunk_count or sum(size for _, size in sizes) != total:
        raise HTTPException(409, "The saved HR recording is incomplete")
    data, offset = bytearray(), 0
    for index, (sequence, size) in enumerate(sizes):
        if sequence != index or not 0 < size <= hr_video.CHUNK_BYTES:
            raise HTTPException(409, "The saved HR recording is incomplete")
        if offset <= end and offset + size > start:
            chunk = db.get(HRVideoChunk, (row.id, sequence))
            data.extend(chunk.data[max(0, start-offset):min(size, end-offset+1)])
        offset += size
    headers = {"Cache-Control": "private, no-store", "Content-Disposition": "inline",
               "Accept-Ranges": "bytes", "X-Content-Type-Options": "nosniff"}
    partial = bool(range_header) or end < total - 1
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
    return Response(bytes(data), media_type=row.mime_type, headers=headers, status_code=206 if partial else 200)
