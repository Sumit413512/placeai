"""Question-scoped voice/video answers. Legacy continuous HR recordings stay readable."""
import json
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func

from app import hr_video, recording_policy
from app.models import AnswerRecording, AnswerRecordingChunk, utcnow

AUDIO_BYTES = 2 * 1024 * 1024
VIDEO_BYTES = 7 * 1024 * 1024
POST_HR_VOICE_SECTIONS = frozenset({"role", "situational"})


def response_mode(question):
    """Return the effective spoken-answer mode without changing legacy HR behavior.

    The final Role/JD and Situational sections are spoken answers even while the
    broader separate-question recording rollout remains disabled. Resume stays text
    and Behavioural/HR keeps its existing continuous camera recording unless the
    server explicitly issued a response_mode.
    """
    explicit = question.get("response_mode")
    if explicit in {"audio", "video"}:
        return explicit
    section = str(question.get("section", "")).strip().lower()
    answer_type = str(question.get("answer_type", "text")).strip().lower()
    if section in POST_HR_VOICE_SECTIONS and answer_type == "text":
        return "audio"
    return None


def _persist_inferred_mode(db, interview, question_id, mode):
    """Persist inferred post-HR audio metadata before media is accepted.

    Evaluation and recovery read the immutable issued question set from the database.
    Persisting the inferred mode once keeps retries, queue processing and saved-result
    recovery consistent with what the student actually recorded.
    """
    questions = json.loads(interview.questions_json or "[]")
    changed = False
    for item in questions:
        if item.get("question_id") != question_id:
            continue
        if item.get("response_mode") not in {"audio", "video"}:
            item["response_mode"] = mode
            item["narration_enabled"] = True
            changed = True
        break
    if changed:
        interview.questions_json = json.dumps(questions)
        db.commit()


def owned(db, user, interview_id, question_id, *, lock=False, reviewer=False):
    root, interview = hr_video.owned_recording(db, user, interview_id, lock=lock, reviewer=reviewer)
    question = next((q for q in json.loads(interview.questions_json) if q.get("question_id") == question_id), None)
    mode = response_mode(question) if question else None
    if not question or mode not in {"audio", "video"}:
        raise HTTPException(404, "Spoken-answer question not found")
    question = {**question, "response_mode": mode}
    query = db.query(AnswerRecording).filter_by(interview_id=interview_id, question_id=question_id)
    row = (query.populate_existing().with_for_update() if lock else query).first()
    return root, interview, question, row


def begin(db, user, interview_id, question_id, mime_type, consent):
    root, interview, question, row = owned(db, user, interview_id, question_id, lock=True)
    recording_policy.require(db, interview)
    mode = question["response_mode"]
    permitted = {"audio/webm", "audio/mp4"} if mode == "audio" else hr_video.MIME_TYPES
    if not consent or mime_type not in permitted:
        raise HTTPException(422, "Consent and a supported recording format are required")
    if root.submission_json or interview.overall_score is not None or root.expires_at <= utcnow():
        raise HTTPException(409, "This assessment has ended")
    if row:
        if row.mime_type != mime_type:
            raise HTTPException(409, "The recording format cannot change")
        return status(row)
    if not root.exam_started_at or utcnow() >= root.exam_started_at + timedelta(minutes=hr_video.EXAM_MINUTES):
        raise HTTPException(409, "Start the assessment before recording")
    active = db.query(AnswerRecording).filter_by(interview_id=interview_id, sealed_at=None).first()
    if active:
        raise HTTPException(409, "Submit the current recording before opening another")
    _persist_inferred_mode(db, interview, question_id, mode)
    now = utcnow()
    row = AnswerRecording(interview_id=interview_id, question_id=question_id, mime_type=mime_type,
                          exam_started_at=root.exam_started_at, started_at=now, consent_at=now,
                          deadline_at=min(now + timedelta(seconds=hr_video.QUESTION_SECONDS),
                                          root.exam_started_at + timedelta(minutes=hr_video.EXAM_MINUTES)),
                          expires_at=root.expires_at,
                          segments_json=json.dumps([{"question_id": question_id, "start": 0, "end": None}]))
    db.add(row)
    db.commit()
    return status(row)


def status(row):
    value = hr_video.recording_status(row)
    value["question_id"] = row.question_id
    value["max_bytes"] = AUDIO_BYTES if row.mime_type.startswith("audio/") else VIDEO_BYTES
    return value


def upload(db, root, interview, row, sequence, data):
    if not row or root.submission_json:
        raise HTTPException(409, "Recording upload is closed")
    # The root lock serializes all uploads for this exam, enforcing its total cap.
    total = db.query(func.coalesce(func.sum(AnswerRecording.size_bytes), 0)).filter_by(interview_id=interview.id).scalar()
    exists = db.get(AnswerRecordingChunk, (row.id, sequence))
    limit = AUDIO_BYTES if row.mime_type.startswith("audio/") else VIDEO_BYTES
    if not exists and (total + len(data) > hr_video.MAX_BYTES or row.size_bytes + len(data) > limit):
        raise HTTPException(413, "The recording reached its size limit")
    return hr_video.save_chunk(db, row, interview, sequence, data, chunk_model=AnswerRecordingChunk)


def sealed_answers(db, interview, issued, submitted):
    """Reject text substituted for a required recording; allow honest timed-out answers."""
    rows = db.query(AnswerRecording).filter_by(interview_id=interview.id).all()
    by_id = {row.question_id: row for row in rows}
    for question in issued:
        if response_mode(question) not in {"audio", "video"}:
            continue
        answer = submitted[question["question_id"]].answer
        row = by_id.get(question["question_id"])
        if row and not row.sealed_at:
            raise HTTPException(409, "Submit every captured answer before submitting the exam")
        if not answer.startswith("[No response submitted") and (not row or not row.sealed_at):
            raise HTTPException(409, "The spoken answer has not finished uploading")
    return by_id


def analyze(db, interview, issued, submitted):
    rows = sealed_answers(db, interview, issued, submitted)
    answers = {}
    for question in issued:
        mode = response_mode(question)
        row = rows.get(question["question_id"])
        if mode not in {"audio", "video"} or not row or not row.sealed_at or not row.chunk_count:
            continue
        # Commit each validated answer independently. A later failure never forces
        # previous answers to be re-uploaded or re-analyzed on the next attempt.
        result = hr_video.analyze_recording(db, row, interview, chunk_model=AnswerRecordingChunk,
                                           questions=[{**question, "response_mode": mode}], audio_only=mode == "audio")
        answers[question["question_id"]] = {**result["answers"][0],
            "size_bytes": row.size_bytes, "mime_type": row.mime_type,
            "recording_url": f"/mock-interview/{interview.id}/answers/{question['question_id']}/recording"}
    return answers
