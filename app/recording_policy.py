"""Record student approval before changing a recording's external processor."""
import os

from fastapi import HTTPException

from app.models import AuditEvent, StudentProfile

ACTION = "groq_recording_consent_v1"


def groq_selected():
    return os.getenv("HR_AI_PROVIDER", "").lower() == "groq"


def consented(db, interview):
    profile = db.get(StudentProfile, interview.student_id)
    return bool(profile and db.query(AuditEvent).filter_by(actor_user_id=profile.user_id,
        action=ACTION, entity_type="mock_interview", entity_id=interview.id).first())


def require(db, interview):
    if groq_selected() and not consented(db, interview):
        raise HTTPException(409, {"code": "VIDEO_PROCESSOR_CONSENT_REQUIRED",
                                 "message": "Approve the updated recording notice before analysis can resume."})


def record(db, user, interview, processor, consent):
    profile = db.get(StudentProfile, interview.student_id)
    if not profile or profile.user_id != user.id:
        raise HTTPException(404, "Assessment not found")
    if not groq_selected():
        return
    if processor != "groq" or not consent:
        raise HTTPException(409, {"code": "VIDEO_PROCESSOR_CONSENT_REQUIRED",
                                 "message": "Read and approve the updated recording notice before starting."})
    if not consented(db, interview):
        db.add(AuditEvent(actor_user_id=user.id, organization_id=profile.organization_id, action=ACTION,
                         entity_type="mock_interview", entity_id=interview.id,
                         metadata_json='{"processor":"groq","notice_version":1,"scope":"voice_video_frames_coaching"}'))
        db.commit()
