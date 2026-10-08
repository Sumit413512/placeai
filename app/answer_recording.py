"""Question-scoped voice/video answers. Legacy continuous HR recordings stay readable."""
import json
from collections import Counter
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import event, func

from app import hr_video, recording_policy
from app.models import AnswerRecording, AnswerRecordingChunk, MockInterview, utcnow

AUDIO_BYTES = 2 * 1024 * 1024
VIDEO_BYTES = 7 * 1024 * 1024
ASSESSMENT_AUDIO_SECTIONS = frozenset({"resume", "role", "situational"})
POST_HR_VOICE_SECTIONS = ASSESSMENT_AUDIO_SECTIONS  # compatibility alias
SPOKEN_ANSWER_SECONDS_BY_SIZE = {"short": 60, "medium": 90, "long": 120}
SPOKEN_ANSWER_SIZE_ORDER = ("short", "medium", "long")
SPOKEN_COMPLEXITY_MARKERS = (
    "walk through", "step by step", "specific evidence", "evidence of", "trade-off",
    "what did you do", "what would you do", "how would you", "and why",
    "and how", "plan", "verify", "validation", "outcome", "risk",
)
FULL_ASSESSMENT_SECTION_COUNTS = {
    "quantitative": 8,
    "logical": 8,
    "communication": 6,
    "technical": 8,
    "programming": 6,
    "coding": 2,
    "resume": 4,
    "behavioral": 4,
    "role": 2,
    "situational": 2,
}
FULL_ASSESSMENT_QUESTION_COUNT = sum(FULL_ASSESSMENT_SECTION_COUNTS.values())


def is_full_assessment_questions(questions):
    """Identify the standardized 50-item assessment without relying on client state."""
    if not isinstance(questions, list) or len(questions) != FULL_ASSESSMENT_QUESTION_COUNT:
        return False
    counts = Counter(
        str(question.get("section", "")).strip().lower()
        for question in questions
        if isinstance(question, dict)
    )
    return counts == Counter(FULL_ASSESSMENT_SECTION_COUNTS)


def materialize_post_hr_modes(questions):
    """Persist required private-audio modes for a standardized full assessment.

    Practice rounds are deliberately excluded. Resume/Project Defence, Role/JD and
    Situational answers are spoken; Behavioural/HR keeps its continuous video flow.
    Legacy in-flight items that already have an explicit video mode remain unchanged.
    """
    if not is_full_assessment_questions(questions):
        return False
    changed = False
    for question in questions:
        if not isinstance(question, dict):
            continue
        section = str(question.get("section", "")).strip().lower()
        answer_type = str(question.get("answer_type", "text")).strip().lower()
        if section not in ASSESSMENT_AUDIO_SECTIONS or answer_type not in {"text", "audio"}:
            continue
        if question.get("response_mode") not in {"audio", "video"}:
            question["response_mode"] = "audio"
            changed = True
        if question.get("response_mode") == "audio" and question.get("answer_type") != "audio":
            question["answer_type"] = "audio"
            changed = True
        if question.get("narration_enabled") is not True:
            question["narration_enabled"] = True
            changed = True
    return changed


@event.listens_for(MockInterview, "before_insert")
def _persist_full_assessment_spoken_policy(_mapper, _connection, target):
    """Store mandatory assessment-audio metadata before a new assessment reaches the DB."""
    try:
        questions = json.loads(target.questions_json or "[]")
    except (TypeError, ValueError):
        return
    if materialize_post_hr_modes(questions):
        target.questions_json = json.dumps(questions)


def response_mode(question):
    """Return the effective spoken-answer mode without changing legacy HR behavior.

    Standardized Resume/Project, Role/JD and Situational responses are private audio.
    Behavioural/HR keeps its existing continuous camera recording unless an older
    server-issued question already carries an explicit response mode.
    """
    explicit = question.get("response_mode")
    if explicit in {"audio", "video"}:
        return explicit
    section = str(question.get("section", "")).strip().lower()
    answer_type = str(question.get("answer_type", "text")).strip().lower()
    if section in ASSESSMENT_AUDIO_SECTIONS and answer_type in {"text", "audio"}:
        return "audio"
    return None


def _persist_inferred_mode(db, interview, question_id, mode):
    """Persist inferred assessment-audio metadata without releasing the row lock."""
    questions = json.loads(interview.questions_json or "[]")
    changed = False
    for item in questions:
        if item.get("question_id") != question_id:
            continue
        if item.get("response_mode") not in {"audio", "video"}:
            item["response_mode"] = mode
            item["narration_enabled"] = True
            changed = True
        if mode == "audio" and item.get("answer_type") != "audio":
            item["answer_type"] = "audio"
            changed = True
        break
    if changed:
        interview.questions_json = json.dumps(questions)
        db.flush()


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


def _legacy_answer_size(question):
    """Recover the #172 timing policy for stored rows that predate timing metadata."""
    section = str(question.get("section", "")).strip().lower()
    difficulty = str(question.get("difficulty", "medium")).strip().lower()
    question_text = str(question.get("question", "")).strip().lower()
    rank = {"easy": 0, "medium": 1, "hard": 2}.get(difficulty, 1)
    if section in {"resume", "situational"}:
        rank = max(rank, 1)
    marker_hits = sum(marker in question_text for marker in SPOKEN_COMPLEXITY_MARKERS)
    if question_text.count("?") >= 2 or marker_hits >= 2:
        rank = min(2, rank + 1)
    requested = str(question.get("expected_answer_size", "")).strip().lower()
    if requested in SPOKEN_ANSWER_SECONDS_BY_SIZE:
        rank = max(rank, SPOKEN_ANSWER_SIZE_ORDER.index(requested))
    return SPOKEN_ANSWER_SIZE_ORDER[rank]


def _answer_time_seconds(question):
    """Use server-issued timing, recovering the same bounded policy for legacy rows."""
    try:
        requested = int(question.get("answer_time_seconds"))
    except (TypeError, ValueError):
        requested = SPOKEN_ANSWER_SECONDS_BY_SIZE[_legacy_answer_size(question)]
    return max(45, min(requested, hr_video.QUESTION_SECONDS))


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
                          deadline_at=min(now + timedelta(seconds=_answer_time_seconds(question)),
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
