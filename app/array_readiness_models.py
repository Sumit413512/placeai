"""Persist the initial answer, guided practice, and independent follow-up."""
from sqlalchemy import Column, DateTime, ForeignKey, Index, SmallInteger, String

from app.database import Base
from app.models import utcnow


class ArrayReadiness(Base):
    __tablename__ = "array_readiness"
    __table_args__ = (Index("ix_array_readiness_institution", "organization_id", "student_id"),)

    student_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    scope = Column(String(100), primary_key=True)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"))
    assigned_at = Column(DateTime, nullable=False, default=utcnow)
    diagnostic_answer = Column(SmallInteger)
    practice_answer = Column(SmallInteger)
    followup_answer = Column(SmallInteger)
