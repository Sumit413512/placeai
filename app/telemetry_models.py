from __future__ import annotations

from sqlalchemy import Column, DateTime, Index, String

from app.database import Base
from app.models import generate_uuid, utcnow


class EmailDeliveryEvent(Base):
    __tablename__ = "email_delivery_events"
    __table_args__ = (Index("ix_email_delivery_events_purpose_created_at", "purpose", "created_at"),)

    id = Column(String, primary_key=True, default=generate_uuid)
    purpose = Column(String(80), nullable=False, index=True)
    outcome = Column(String(32), nullable=False, index=True)
    reason_code = Column(String(80), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow, index=True)
