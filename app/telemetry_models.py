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


class PageViewEvent(Base):
    __tablename__ = "page_view_events"
    __table_args__ = (
        Index("ix_page_view_events_created_path", "created_at", "path"),
        Index("ix_page_view_events_user_created", "user_id", "created_at"),
        Index("ix_page_view_events_visitor_created", "visitor_hash", "created_at"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    visitor_hash = Column(String(64), nullable=False, index=True)
    session_hash = Column(String(64), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    path = Column(String(240), nullable=False, index=True)
    referrer_host = Column(String(200), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow, index=True)
