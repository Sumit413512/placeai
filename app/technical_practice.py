"""Archived storage model for migration 0026; no live practice API or user interface."""
from datetime import timedelta
from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from app.database import Base
from app.models import generate_uuid, utcnow
VERSION = 'technical-foundations-1'
DURATION_SECONDS = 24 * 60


class TechnicalPracticeAttempt(Base):
    __tablename__ = 'technical_practice_attempts'
    __table_args__ = (Index('ix_technical_practice_owner', 'user_id', 'created_at'),
                     UniqueConstraint('user_id', 'request_id', name='uq_technical_practice_request'))
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    request_id = Column(String(36), nullable=False)
    version = Column(String(40), nullable=False, default=VERSION)
    questions_json = Column(Text, nullable=False)
    answers_json = Column(Text, nullable=False, default='{}')
    result_json = Column(Text)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    deadline_at = Column(DateTime, nullable=False, default=lambda: utcnow() + timedelta(seconds=DURATION_SECONDS))
