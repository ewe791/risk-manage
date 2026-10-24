"""用户画像服务：聚合订单历史、退款/投诉、地址、最近风险事件与关联案件。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RiskAssessment, RiskCase, RiskEvent
from app.services import source_adapter as upstream
from app.services.feature_service import REFUND_STATUSES, jsonable


def get_user_profile(db: Session, user_id: str, event_limit: int = 10, case_limit: int = 10) -> dict:
    user = upstream.get_user(user_id) or {}
    orders = upstream.list_user_orders(user_id)
    now = datetime.now(timezone.utc)
    orders_30d = upstream.orders_within(orders, 30, now)

    order_history = [
        {
            "order_id": o["order_id"],
            "amount": jsonable(o["amount"]),
            "status": o.get("status"),
            "refund_status": o.get("refund_status"),
            "has_complaint": bool(o.get("has_complaint")),
            "category": o.get("category"),
            "address_id": o.get("address_id"),
            "created_at": (o["created_at_dt"].isoformat() if o.get("created_at_dt") else o.get("created_at")),
        }
        for o in sorted(orders, key=lambda x: x.get("created_at_dt") or now, reverse=True)
    ]

    refund_count_30d = len([o for o in orders_30d if o.get("refund_status") in REFUND_STATUSES])
    complaint_count_30d = len([o for o in orders_30d if o.get("has_complaint")])

    events = db.execute(
        select(RiskEvent)
        .where(RiskEvent.user_id == user_id)
        .order_by(RiskEvent.created_at.desc())
        .limit(event_limit)
    ).scalars().all()
    recent_risk_events = []
    for ev in events:
        assessment = db.execute(
            select(RiskAssessment)
            .where(RiskAssessment.event_id == ev.id)
            .order_by(RiskAssessment.created_at.desc())
        ).scalars().first()
        recent_risk_events.append(
            {
                "event_id": ev.id,
                "event_type": ev.event_type,
                "order_id": ev.order_id,
                "created_at": ev.created_at,
                "assessment_id": assessment.id if assessment else None,
                "risk_score": assessment.risk_score if assessment else None,
                "risk_level": assessment.risk_level if assessment else None,
                "decision": assessment.decision if assessment else None,
            }
        )

    cases = db.execute(
        select(RiskCase)
        .where(RiskCase.user_id == user_id)
        .order_by(RiskCase.created_at.desc())
        .limit(case_limit)
    ).scalars().all()

    return {
        "user_id": user_id,
        "nickname": user.get("nickname"),
        "register_at": user.get("register_at"),
        "reg_days": (now - user["register_at_dt"]).days if user.get("register_at_dt") else None,
        "order_count": len(orders),
        "order_count_30d": len(orders_30d),
        "order_history": order_history,
        "refund_count": refund_count_30d,
        "complaint_count": complaint_count_30d,
        "address_count": len(user.get("addresses", [])),
        "addresses": [
            {
                "address_id": a.get("address_id"),
                "city": a.get("city"),
                "detail": a.get("detail"),
                "shared_user_count": a.get("shared_user_count"),
                "used_at": a["used_at_dt"].isoformat() if a.get("used_at_dt") else a.get("used_at"),
            }
            for a in user.get("addresses", [])
        ],
        "recent_risk_events": recent_risk_events,
        "related_cases": [
            {
                "case_id": c.id,
                "assessment_id": c.assessment_id,
                "order_id": c.order_id,
                "case_status": c.case_status,
                "review_result": c.review_result,
                "created_at": c.created_at,
            }
            for c in cases
        ],
        "window": {"order_count_30d": (now - timedelta(days=30)).isoformat()},
    }
