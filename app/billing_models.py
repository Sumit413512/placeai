from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String

from app.database import Base
from app.models import generate_uuid, utcnow


class StudentSubscription(Base):
    __tablename__ = "student_subscriptions"
    __table_args__ = (
        Index("ix_student_subscriptions_student_status", "student_id", "status"),
        Index("ix_student_subscriptions_expires_at", "expires_at"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    student_id = Column(String, ForeignKey("student_profiles.id"), nullable=False, index=True)
    plan_code = Column(String(80), nullable=False, default="placeai_independent_monthly")
    status = Column(String(40), nullable=False, default="active")
    provider = Column(String(40), nullable=True)
    provider_subscription_id = Column(String(160), nullable=True, unique=True)
    provider_payment_id = Column(String(160), nullable=True)
    amount_paise = Column(Integer, nullable=False, default=29900)
    starts_at = Column(DateTime, nullable=False, default=utcnow)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
