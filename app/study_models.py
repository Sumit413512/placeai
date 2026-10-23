"""Private study plans and self-reported reading, separate from assessment scores."""
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from app.database import Base
from app.models import generate_uuid, utcnow


class StudyPlan(Base):
    __tablename__ = 'study_plans'
    __table_args__ = (Index('ix_study_plan_owner', 'user_id', 'created_at'),)
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    title = Column(String(180), nullable=False)
    # Provenance only: deleting a source roadmap must not erase a student's plan.
    roadmap_id = Column(String)
    daily_minutes = Column(Integer, nullable=False, default=45)
    target_date = Column(Date)
    timezone = Column(String(64), nullable=False, default='Asia/Kolkata')
    paused = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class StudyGoal(Base):
    __tablename__ = 'study_goals'
    __table_args__ = (UniqueConstraint('plan_id', 'kind', 'resource_id', name='uq_study_goal_resource'),)
    id = Column(String, primary_key=True, default=generate_uuid)
    plan_id = Column(String, ForeignKey('study_plans.id', ondelete='CASCADE'), nullable=False, index=True)
    kind = Column(String(20), nullable=False)
    resource_id = Column(String(100), nullable=False)
    title = Column(String(240), nullable=False)
    target = Column(Integer, nullable=False)
    manual_completed = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class NotebookProgress(Base):
    __tablename__ = 'learning_notebook_progress'
    notebook_id = Column(String, ForeignKey('learning_notebooks.id', ondelete='CASCADE'), primary_key=True)
    section_key = Column(String(24), primary_key=True)
    completed = Column(Boolean, nullable=False, default=False)
    completed_at = Column(DateTime)
    last_read_at = Column(DateTime, nullable=False, default=utcnow)
    source = Column(String(12), nullable=False, default='web')
    last_event_id = Column(String(36))


class StudyDaily(Base):
    __tablename__ = 'study_daily_activity'
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    day = Column(Date, primary_key=True)
    notes_seconds = Column(Integer, nullable=False, default=0)
    video_seconds = Column(Integer, nullable=False, default=0)
    sections_completed = Column(Integer, nullable=False, default=0)
    last_pulse_at = Column(DateTime)
