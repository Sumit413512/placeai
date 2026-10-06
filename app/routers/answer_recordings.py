from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app import answer_recording, hr_video
from app.database import get_db
from app.dependencies import get_current_user, require_student
from app.models import AnswerRecordingChunk, User, utcnow
from app.routers.hr_recording import recording_response
import json

router = APIRouter(prefix="/mock-interview", tags=["Spoken answers"])


class Start(BaseModel):
    mime_type: str = Field(pattern="^(audio|video)/(webm|mp4)$")
    consent: bool


class Submit(BaseModel):
    chunks: int = Field(ge=0, le=hr_video.MAX_CHUNKS)


@router.post("/{interview_id}/answers/{question_id}/start")
def start(interview_id: str, question_id: int, body: Start, user: User = Depends(require_student), db: Session = Depends(get_db)):
    return answer_recording.begin(db, user, interview_id, question_id, body.mime_type, body.consent)


@router.put("/{interview_id}/answers/{question_id}/chunks/{sequence}")
async def upload(interview_id: str, question_id: int, sequence: int, request: Request,
                 user: User = Depends(require_student), db: Session = Depends(get_db)):
    await run_in_threadpool(answer_recording.owned, db, user, interview_id, question_id)
    await run_in_threadpool(db.rollback)
    if not 0 <= sequence < hr_video.MAX_CHUNKS:
        raise HTTPException(413, "Invalid recording chunk")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > hr_video.CHUNK_BYTES:
            raise HTTPException(413, "Recording chunk exceeds the allowed size")
        data.extend(chunk)
    def persist():
        root, interview, _, row = answer_recording.owned(db, user, interview_id, question_id, lock=True)
        return answer_recording.upload(db, root, interview, row, sequence, bytes(data))
    return await run_in_threadpool(persist)


@router.post("/{interview_id}/answers/{question_id}/submit")
def submit(interview_id: str, question_id: int, body: Submit,
           user: User = Depends(require_student), db: Session = Depends(get_db)):
    root, _, _, row = answer_recording.owned(db, user, interview_id, question_id, lock=True)
    if not row or root.submission_json and not row.sealed_at:
        raise HTTPException(409, "Recording cannot be submitted")
    if body.chunks == 0 and not row.chunk_count and not row.sealed_at:
        row.status = "submitted"
        row.sealed_at = utcnow()
        row.segments_json = json.dumps([{"question_id": question_id, "start": 0, "end": 0}])
        db.commit()
    else:
        hr_video.seal_recording(db, row, body.chunks)
    return answer_recording.status(row)


@router.get("/{interview_id}/answers/{question_id}/recording")
def recording(interview_id: str, question_id: int, request: Request,
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _, _, _, row = answer_recording.owned(db, user, interview_id, question_id, reviewer=True)
    if not row:
        raise HTTPException(404, "Recording not found")
    return recording_response(db, row, request, chunk_model=AnswerRecordingChunk)
