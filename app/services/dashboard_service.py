"""看板服务：总量、高风险占比、案件处理效率、规则命中排行、黑名单命中数、近 7 天趋势。"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import FeatureSnapshot, RiskAssessment, RiskCase, RiskEvent, RiskRule, RuleHit


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def get_dashboard(db: Session, days: int = 7) -> dict:
    now = datetime.now(timezone.utc)

    total_events = int(db.execute(select(func.count(RiskEvent.id))).scalar() or 0)
    total_assessments = int(db.execute(select(func.count(RiskAssessment.id))).scalar() or 0)
    high_count = int(
        db.execute(
            select(func.count(RiskAssessment.id)).where(RiskAssessment.risk_level == "high")
        ).scalar()
        or 0
    )

    # 规则命中排行（Top 10）
    rows = db.execute(
        select(RuleHit.rule_id, func.count(RuleHit.id), func.sum(RuleHit.hit_score))
        .group_by(RuleHit.rule_id)
        .order_by(func.count(RuleHit.id).desc())
        .limit(10)
    ).all()
    ranking = []
    for rule_id, hit_count, score_sum in rows:
        rule = db.get(RiskRule, rule_id)
        ranking.append(
            {
                "rule_id": rule_id,
                "rule_code": rule.rule_code if rule else "已删除",
                "rule_name": rule.rule_name if rule else "已删除规则",
                "hit_count": int(hit_count),
                "hit_score_sum": int(score_sum or 0),
            }
        )

    # 黑名单命中数：扫描特征快照（单条 SQL，Python 侧聚合避免 N+1）
    bl_hits = 0
    for (feature_json,) in db.execute(select(FeatureSnapshot.feature_json)).all():
        if not isinstance(feature_json, dict):
            continue
        if feature_json.get("user_blacklist_hit") is True or feature_json.get("address_in_blacklist") is True:
            bl_hits += 1

    # 案件效率
    cases = db.execute(select(RiskCase)).scalars().all()
    pending = len([c for c in cases if c.case_status in ("pending", "reviewing")])
    reviewed = [c for c in cases if c.case_status in ("approved", "rejected")]
    handle_hours = []
    for c in reviewed:
        if c.created_at and c.updated_at:
            delta = c.updated_at - c.created_at
            handle_hours.append(delta.total_seconds() / 3600)
    avg_handle = round(sum(handle_hours) / len(handle_hours), 2) if handle_hours else 0.0

    # 近 N 天趋势
    since = now - timedelta(days=days - 1)
    event_rows = db.execute(
        select(RiskEvent.created_at, RiskAssessment.risk_level)
        .join(RiskAssessment, RiskAssessment.event_id == RiskEvent.id, isouter=True)
        .where(RiskEvent.created_at >= since.replace(hour=0, minute=0, second=0, microsecond=0))
    ).all()
    buckets: Counter = Counter()
    high_buckets: Counter = Counter()
    for created_at, level in event_rows:
        if not created_at:
            continue
        key = created_at.astimezone(timezone.utc).strftime("%m-%d")
        buckets[key] += 1
        if level == "high":
            high_buckets[key] += 1
    trend = [
        {
            "date": (since + timedelta(days=i)).strftime("%m-%d"),
            "events": buckets.get((since + timedelta(days=i)).strftime("%m-%d"), 0),
            "high_risk": high_buckets.get((since + timedelta(days=i)).strftime("%m-%d"), 0),
        }
        for i in range(days)
    ]

    return {
        "total_events": total_events,
        "high_risk_ratio": _ratio(high_count, total_assessments),
        "case_efficiency": {
            "total_cases": len(cases),
            "pending_cases": pending,
            "reviewed_cases": len(reviewed),
            "review_rate": _ratio(len(reviewed), len(cases)),
            "avg_handle_hours": avg_handle,
        },
        "rule_hit_ranking": ranking,
        "blacklist_hit_count": bl_hits,
        "trend": trend,
    }
