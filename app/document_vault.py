"""Explicit institution submissions; private files never imply staff access."""
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from app.models import Organization, UserRole

TYPES = {'marksheet', 'certification', 'transcript', 'photo', 'identity', 'internship_letter', 'offer_letter'}


class DocumentSubmission(BaseModel):
    model_config = ConfigDict(extra='forbid')
    consent: StrictBool
    organization_id: str = Field(min_length=1, max_length=100)


class DocumentMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid')
    semester: int | None = Field(None, ge=1, le=20)
    label: str | None = Field(None, max_length=160)


def staff_can_view(user, student, document):
    return bool(user.role == UserRole.institution_admin and user.organization_id
                and student.organization_id == user.organization_id
                and document.shared_organization_id == user.organization_id and document.shared_at)


def out(document, db):
    org = db.get(Organization, document.shared_organization_id) if document.shared_organization_id else None
    return {'id': document.id, 'document_type': document.document_type, 'filename': document.original_filename,
            'label': document.label, 'semester': document.semester,
            'visibility': 'institution_only' if document.shared_at else 'private',
            'shared_organization_id': document.shared_organization_id,
            'shared_organization_name': org.name if org else None,
            'shared_at': document.shared_at.isoformat() if document.shared_at else None,
            'is_verified': document.is_verified, 'uploaded_at': document.uploaded_at.isoformat() if document.uploaded_at else None}


def validate_type(kind):
    if kind not in TYPES:
        raise HTTPException(422, 'Choose a supported document type.')
