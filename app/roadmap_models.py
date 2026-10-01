from __future__ import annotations

import json

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text

from app.database import Base
from app.models import generate_uuid, utcnow


class StudentFeaturePurchase(Base):
    __tablename__ = "student_feature_purchases"
    __table_args__ = (
        Index(
            "ix_student_feature_purchases_student_feature_status",
            "student_id",
            "feature_code",
            "status",
        ),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    student_id = Column(String, ForeignKey("student_profiles.id"), nullable=False, index=True)
    feature_code = Column(String(80), nullable=False, index=True)
    status = Column(String(40), nullable=False, default="pending", index=True)
    provider = Column(String(40), nullable=True)
    provider_order_id = Column(String(180), nullable=True, unique=True)
    provider_payment_id = Column(String(180), nullable=True, unique=True)
    amount_paise = Column(Integer, nullable=False)
    purchased_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class CareerRoadmap(Base):
    __tablename__ = "career_roadmaps"
    __table_args__ = (
        Index("ix_career_roadmaps_student_created", "student_id", "created_at"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    student_id = Column(String, ForeignKey("student_profiles.id"), nullable=False, index=True)
    title = Column(String(240), nullable=False)
    target_role = Column(String(200), nullable=True)
    target_field = Column(String(200), nullable=True)
    market_region = Column(String(120), nullable=False, default="India")
    input_json = Column(Text, nullable=False, default="{}")
    market_snapshot_json = Column(Text, nullable=False, default="{}")
    roadmap_json = Column(Text, nullable=False, default="{}")
    sources_json = Column(Text, nullable=False, default="[]")
    ai_provider = Column(String(40), nullable=True)
    ai_model = Column(String(120), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    @staticmethod
    def _decode(raw: str | None, fallback):
        try:
            return json.loads(raw or "")
        except (TypeError, json.JSONDecodeError):
            return fallback

    @property
    def request_input(self) -> dict:
        value = self._decode(self.input_json, {})
        return value if isinstance(value, dict) else {}

    @request_input.setter
    def request_input(self, value: dict) -> None:
        self.input_json = json.dumps(value or {}, ensure_ascii=False)

    @property
    def market_snapshot(self) -> dict:
        value = self._decode(self.market_snapshot_json, {})
        return value if isinstance(value, dict) else {}

    @market_snapshot.setter
    def market_snapshot(self, value: dict) -> None:
        self.market_snapshot_json = json.dumps(value or {}, ensure_ascii=False)

    @property
    def roadmap(self) -> dict:
        value = self._decode(self.roadmap_json, {})
        return value if isinstance(value, dict) else {}

    @roadmap.setter
    def roadmap(self, value: dict) -> None:
        self.roadmap_json = json.dumps(value or {}, ensure_ascii=False)

    @property
    def sources(self) -> list[dict]:
        value = self._decode(self.sources_json, [])
        return value if isinstance(value, list) else []

    @sources.setter
    def sources(self, value: list[dict]) -> None:
        self.sources_json = json.dumps(value or [], ensure_ascii=False)
