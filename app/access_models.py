from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, String, Text

from app.database import Base
from app.models import generate_uuid, utcnow


class AccessRequest(Base):
    """A real production access request for controlled PlaceAI account provisioning."""

    __tablename__ = "access_requests"

    id = Column(String, primary_key=True, default=generate_uuid)
    requested_role = Column(String(40), nullable=False, index=True)
    full_name = Column(String(200), nullable=False)
    work_email = Column(String(320), nullable=False, index=True)
    organization_name = Column(String(250), nullable=True)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    phone = Column(String(40), nullable=True)
    message = Column(Text, nullable=True)
    status = Column(String(40), nullable=False, default="new", index=True)
    reviewed_by_user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    review_note = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
