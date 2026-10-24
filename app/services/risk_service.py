"""R4 风险检查 + 决策 + 自动建案。

流程严格按文档 5 节：
  1) 写 risk_events
  2) build_feature_snapshot（排除本次事件，反映"历史"）
  3) 遍历启用规则（priority 升序），evaluate_rule 收集命中
  4) total_score = min(100, sum(hit_score))
  5) 等级/建议映射固定：high>=70, medium>=40, else low；
     decision: reject>=90, manual_review>=70, else pass
  6) 写 risk_assessments / feature_snapshots / rule_hits
  7) level==high 或 decision in (manual_review, reject) → 建 risk_cases(pending)
  8) 返回约定结构
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    FeatureSnapshot,
    RiskAssessment,
    RiskCase,
    RiskEvent,
    RiskRule,
    RuleHit,
    gen_id,
)
from app.services.feature_service import (
    FEATURE_NAMES,
    build_feature_snapshot,
    jsonable,
    snapshot_for_json,
)
from app.services.rule_engine import evaluate_rule

EVENT_TYPES = {
    "order_create": "下单",
    "order_pay": "支付",
    "after_sale_apply": "售后申请",
    "logistics_complaint": "物流投诉",
}

LEVEL_HIGH = 70
LEVEL_MEDIUM = 40
DECISION_REJECT = 90
DECISION_MANUAL = 70


class RiskValidationError(ValueError):
    """入参校验失败（由 API 层转 code != 0）。"""


def map_level(total_score: int) -> str:
    """评分 → 风险等级（固定映射，不得自行发挥）。"""
    if total_score >= LEVEL_HIGH:
        return "high"
    if total_score >= LEVEL_MEDIUM:
        return "medium"
    return "low"


def map_decision(total_score: int) -> str:
    """评分 → 处置建议（固定映射）。"""
    if total_score >= DECISION_REJECT:
        return "reject"
    if total_score >= DECISION_MANUAL:
        return "manual_review"
    return "pass"


def _validate(event_type: str, user_id: str) -> None:
    if event_type not in EVENT_TYPES:
        raise RiskValidationError(
            f"event_type 仅支持 {sorted(EVENT_TYPES)}，收到 {event_type!r}"
        )
    if not user_id:
        raise RiskValidationError("user_id 必填")


def _hit_message(rule: RiskRule, features: dict) -> str:
    """生成可读命中说明：规则名 + 关键特征值。"""
    parts: list[str] = []
    cond = rule.condition_json or {}
    stack = [cond]
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        if "conditions" in node:
            stack.extend(node.get("conditions") or [])
        field = node.get("field")
        if field and field in features:
            parts.append(f"{field}={jsonable(features[field])}")
    detail = "，".join(dict.fromkeys(parts)[:6]) if False else "，".join(parts[:4])
    return f"{rule.rule_name}（命中 {rule.score} 分）：{detail}" if detail else f"{rule.rule_name}（命中 {rule.score} 分）"


async def check_risk(
    db: Session,
    event_type: str,
    source_id: str | None,
    user_id: str,
    order_id: str | None,
    operator_id: str,
) -> dict:
    _validate(event_type, user_id)

    # 1) 风险事件落库
    event = RiskEvent(
        id=gen_id("RE"),
        event_type=event_type,
        source_id=source_id,
        user_id=user_id,
        order_id=order_id,
        event_payload_json={
            "event_type": event_type,
            "source_id": source_id,
            "user_id": user_id,
            "order_id": order_id,
            "operator_id": operator_id,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        },
        created_at=datetime.now(timezone.utc),
    )
    db.add(event)
    db.flush()

    # 2) 特征快照（排除本次事件自身的计数影响）
    features = build_feature_snapshot(db, user_id, order_id, exclude_event_id=event.id)

    # 3) 规则求值
    rules = db.execute(
        select(RiskRule)
        .where(RiskRule.rule_status == "enabled")
        .order_by(RiskRule.priority.asc(), RiskRule.rule_code.asc())
    ).scalars().all()

    hits: list[tuple[RiskRule, int, str]] = []
    for rule in rules:
        hit, score = evaluate_rule(rule, features)
        if hit:
            hits.append((rule, score, _hit_message(rule, features)))

    # 4) 汇总与分级
    total_score = min(100, sum(score for _, score, _ in hits))
    risk_level = map_level(total_score)
    decision = map_decision(total_score)

    # 6) 评估 / 快照 / 命中落库
    assessment = RiskAssessment(
        id=gen_id("RA"),
        event_id=event.id,
        risk_score=int(total_score),
        risk_level=risk_level,
        decision=decision,
        assessment_status="finished",
        created_at=datetime.now(timezone.utc),
    )
    db.add(assessment)
    db.flush()

    db.add(
        FeatureSnapshot(
            id=gen_id("FS"),
            assessment_id=assessment.id,
            feature_json=snapshot_for_json(features),
            created_at=datetime.now(timezone.utc),
        )
    )

    rule_hit_payload = []
    for rule, score, message in hits:
        db.add(
            RuleHit(
                id=gen_id("RH"),
                assessment_id=assessment.id,
                rule_id=rule.id,
                hit_score=int(score),
                hit_message=message[:255],
                created_at=datetime.now(timezone.utc),
            )
        )
        rule_hit_payload.append(
            {
                "rule_id": rule.id,
                "rule_code": rule.rule_code,
                "rule_name": rule.rule_name,
                "hit_score": int(score),
                "hit_message": message,
            }
        )

    # 7) 自动建案
    case_id = None
    if risk_level == "high" or decision in ("manual_review", "reject"):
        case = RiskCase(
            id=gen_id("CASE"),
            assessment_id=assessment.id,
            user_id=user_id,
            order_id=order_id,
            case_status="pending",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(case)
        db.flush()
        case_id = case.id

    db.commit()

    # 8) 返回约定结构
    return {
        "assessment_id": assessment.id,
        "event_id": event.id,
        "risk_score": int(total_score),
        "risk_level": risk_level,
        "decision": decision,
        "hit_count": len(rule_hit_payload),
        "rule_hits": rule_hit_payload,
        "feature_snapshot": snapshot_for_json(features),
        "case_id": case_id,
        "user_id": user_id,
        "order_id": order_id,
        "event_type": event_type,
        "event_type_label": EVENT_TYPES[event_type],
    }


def get_assessment_detail(db: Session, assessment_id: str) -> dict | None:
    assessment = db.get(RiskAssessment, assessment_id)
    if not assessment:
        return None
    event = db.get(RiskEvent, assessment.event_id)
    snapshot = db.execute(
        select(FeatureSnapshot).where(FeatureSnapshot.assessment_id == assessment_id)
    ).scalars().first()
    hits = []
    for rh in assessment.rule_hits:
        rule = db.get(RiskRule, rh.rule_id)
        hits.append(
            {
                "rule_id": rh.rule_id,
                "rule_code": rule.rule_code if rule else None,
                "rule_name": rule.rule_name if rule else None,
                "hit_score": rh.hit_score,
                "hit_message": rh.hit_message,
            }
        )
    case = db.execute(
        select(RiskCase).where(RiskCase.assessment_id == assessment_id)
    ).scalars().first()
    return {
        "assessment_id": assessment.id,
        "risk_score": assessment.risk_score,
        "risk_level": assessment.risk_level,
        "decision": assessment.decision,
        "assessment_status": assessment.assessment_status,
        "created_at": assessment.created_at,
        "event": {
            "event_id": event.id if event else None,
            "event_type": event.event_type if event else None,
            "user_id": event.user_id if event else None,
            "order_id": event.order_id if event else None,
            "source_id": event.source_id if event else None,
        },
        "feature_snapshot": (snapshot.feature_json if snapshot else {}),
        "rule_hits": hits,
        "rule_hit_count": len(hits),
        "case_id": case.id if case else None,
        "case_status": case.case_status if case else None,
    }


def feature_coverage(features: dict) -> dict:
    """自检用：25 键是否齐全。"""
    missing = [n for n in FEATURE_NAMES if n not in features]
    return {"total": len(FEATURE_NAMES), "missing": missing, "complete": not missing}


__all__ = [
    "EVENT_TYPES",
    "check_risk",
    "get_assessment_detail",
    "map_level",
    "map_decision",
    "RiskValidationError",
    "Decimal",
]
