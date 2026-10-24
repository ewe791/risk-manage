"""SQLAlchemy 模型：严格按《项目一_风控Agent》1.2 节 schema，不额外扩展字段。

8 张业务表：
  risk_events / risk_assessments / feature_snapshots / risk_rules
  rule_hits / risk_cases / blacklists / review_logs
补充表：
  agent_tool_logs
"""

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from datetime import datetime

from app.models.base import JSONType, TS, utcnow
from app.models.base import Base as _Base


class RiskEvent(_Base):
    __tablename__ = "risk_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    order_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    event_payload_json: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, default=utcnow, index=True)

    assessments: Mapped[list["RiskAssessment"]] = relationship(back_populates="event")


class RiskAssessment(_Base):
    __tablename__ = "risk_assessments"
    __table_args__ = (
        CheckConstraint("risk_score >= 0 AND risk_score <= 100", name="ck_risk_score_range"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("risk_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    assessment_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="finished"
    )
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, default=utcnow, index=True)

    event: Mapped[RiskEvent] = relationship(back_populates="assessments")
    feature_snapshot: Mapped["FeatureSnapshot | None"] = relationship(
        back_populates="assessment", uselist=False, cascade="all, delete-orphan"
    )
    rule_hits: Mapped[list["RuleHit"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )
    cases: Mapped[list["RiskCase"]] = relationship(back_populates="assessment")


class FeatureSnapshot(_Base):
    __tablename__ = "feature_snapshots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("risk_assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    feature_json: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, default=utcnow)

    assessment: Mapped[RiskAssessment] = relationship(back_populates="feature_snapshot")


class RiskRule(_Base):
    __tablename__ = "risk_rules"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    rule_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    rule_name: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="enabled", index=True
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    condition_json: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(TS, nullable=False, default=utcnow)


class RuleHit(_Base):
    __tablename__ = "rule_hits"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("risk_assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_id: Mapped[str] = mapped_column(
        ForeignKey("risk_rules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hit_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hit_message: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, default=utcnow)

    assessment: Mapped[RiskAssessment] = relationship(back_populates="rule_hits")
    rule: Mapped[RiskRule] = relationship()


class RiskCase(_Base):
    __tablename__ = "risk_cases"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("risk_assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    order_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    case_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", index=True
    )
    reviewer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    review_result: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(TS, nullable=False, default=utcnow)

    assessment: Mapped[RiskAssessment] = relationship(back_populates="cases")
    review_logs: Mapped[list["ReviewLog"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )


class Blacklist(_Base):
    __tablename__ = "blacklists"
    __table_args__ = (
        Index("ix_blacklist_type_value", "blacklist_type", "blacklist_value", unique=True),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    blacklist_type: Mapped[str] = mapped_column(String(32), nullable=False)
    blacklist_value: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, default=utcnow)


class ReviewLog(_Base):
    __tablename__ = "review_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("risk_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    operator_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    action_remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, default=utcnow, index=True)

    case: Mapped[RiskCase] = relationship(back_populates="review_logs")


class AgentToolLog(_Base):
    __tablename__ = "agent_tool_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    args_json: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    result_json: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, default=utcnow, index=True)


__all__ = [
    "RiskEvent",
    "RiskAssessment",
    "FeatureSnapshot",
    "RiskRule",
    "RuleHit",
    "RiskCase",
    "Blacklist",
    "ReviewLog",
    "AgentToolLog",
]
