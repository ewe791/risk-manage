"""案件服务：分页查询、详情、审核（写 review_logs + 更新案件状态）。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import FeatureSnapshot, ReviewLog, RiskAssessment, RiskCase, RiskRule, gen_id

CASE_STATUSES = {"pending", "reviewing", "approved", "rejected", "resolved"}
# 同一结论的多种表述（开发文档用 approve/reject，评测文档用 approved/rejected/resolved）
REVIEW_RESULTS = {
    "approve": "approved",
    "approved": "approved",
    "reject": "rejected",
    "rejected": "rejected",
    "escalate": "reviewing",
    "resolved": "resolved",
}


class CaseError(ValueError):
    pass


def serialize_case(case: RiskCase, assessment: RiskAssessment | None = None) -> dict:
    return {
        "case_id": case.id,
        "assessment_id": case.assessment_id,
        "user_id": case.user_id,
        "order_id": case.order_id,
        "case_status": case.case_status,
        "reviewer_id": case.reviewer_id,
        "review_result": case.review_result,
        "created_at": case.created_at,
        "updated_at": case.updated_at,
        "risk_score": assessment.risk_score if assessment else None,
        "risk_level": assessment.risk_level if assessment else None,
        "decision": assessment.decision if assessment else None,
    }


def list_cases(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    case_status: str | None = None,
    user_id: str | None = None,
) -> dict:
    stmt = select(RiskCase)
    count_stmt = select(func.count(RiskCase.id))
    conds = []
    if case_status:
        conds.append(RiskCase.case_status == case_status)
    if user_id:
        conds.append(RiskCase.user_id == user_id)
    if conds:
        stmt = stmt.where(*conds)
        count_stmt = count_stmt.where(*conds)
    total = int(db.execute(count_stmt).scalar() or 0)
    rows = db.execute(
        stmt.order_by(RiskCase.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    items = [serialize_case(c, db.get(RiskAssessment, c.assessment_id)) for c in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def get_case(db: Session, case_id: str) -> dict:
    case = db.get(RiskCase, case_id)
    if not case:
        raise CaseError(f"案件不存在: {case_id}")
    assessment = db.get(RiskAssessment, case.assessment_id)
    data = serialize_case(case, assessment)
    data["review_logs"] = [
        {
            "log_id": log.id,
            "operator_id": log.operator_id,
            "action_type": log.action_type,
            "action_remark": log.action_remark,
            "created_at": log.created_at,
        }
        for log in sorted(case.review_logs, key=lambda x: x.created_at)
    ]
    # 案件详情页需要展示特征快照（文档 2.3.3）
    snapshot = db.execute(
        select(FeatureSnapshot).where(FeatureSnapshot.assessment_id == case.assessment_id)
    ).scalars().first()
    data["feature_snapshot"] = snapshot.feature_json if snapshot else {}
    data["event_id"] = assessment.event_id if assessment else None
    data["resolved_at"] = next(
        (log["created_at"] for log in reversed(data["review_logs"]) if log["action_type"].startswith("resolve")),
        None,
    )
    rule_hits = []
    for hit in (assessment.rule_hits if assessment else []):
        rule = db.get(RiskRule, hit.rule_id)
        rule_hits.append(
            {
                "rule_code": rule.rule_code if rule else None,
                "rule_name": rule.rule_name if rule else None,
                "hit_score": hit.hit_score,
                "hit_message": hit.hit_message,
            }
        )
    data["rule_hits"] = rule_hits
    return data


def review_case(
    db: Session,
    case_id: str,
    review_result: str,
    review_remark: str | None,
    operator_id: str,
) -> dict:
    if review_result not in REVIEW_RESULTS:
        raise CaseError(f"review_result 仅支持 {sorted(REVIEW_RESULTS)}")
    if not review_remark or not review_remark.strip():
        raise CaseError("review_remark 必填")
    case = db.get(RiskCase, case_id)
    if not case:
        raise CaseError(f"案件不存在: {case_id}")
    if case.case_status in ("approved", "rejected", "resolved"):
        raise CaseError(f"案件已审核完成（{case.case_status}），不可重复提交")
    if REVIEW_RESULTS[review_result] == "resolved" and case.case_status in ("pending", "reviewing"):
        raise CaseError("请先完成审核（approve/reject）后再标记处理完成")

    now = datetime.now(timezone.utc)
    case.case_status = REVIEW_RESULTS[review_result]
    case.review_result = review_result
    case.reviewer_id = operator_id
    case.updated_at = now
    db.add(
        ReviewLog(
            id=gen_id("RL"),
            case_id=case.id,
            operator_id=operator_id,
            action_type=f"review:{review_result}",
            action_remark=review_remark.strip(),
            created_at=now,
        )
    )
    db.commit()

    return {
        "case_id": case.id,
        "case_status": case.case_status,
        "review_result": case.review_result,
        "reviewer_id": case.reviewer_id,
        "review_remark": review_remark.strip(),
        "reviewed_at": now,
    }


def resolve_case(db: Session, case_id: str, resolve_remark: str | None, operator_id: str) -> dict:
    """标记案件处理完成（approved/rejected → resolved），同样写入 review_logs。"""
    if not resolve_remark or not resolve_remark.strip():
        raise CaseError("resolve_remark 必填")
    case = db.get(RiskCase, case_id)
    if not case:
        raise CaseError(f"案件不存在: {case_id}")
    if case.case_status == "resolved":
        raise CaseError("案件已是处理完成状态")
    if case.case_status in ("pending", "reviewing"):
        raise CaseError("请先完成审核（approve/reject）后再标记处理完成")

    now = datetime.now(timezone.utc)
    case.case_status = "resolved"
    case.updated_at = now
    db.add(
        ReviewLog(
            id=gen_id("RL"),
            case_id=case.id,
            operator_id=operator_id,
            action_type="resolve",
            action_remark=resolve_remark.strip(),
            created_at=now,
        )
    )
    db.commit()
    return {
        "case_id": case.id,
        "case_status": case.case_status,
        "resolved_at": now,
        "operator_id": operator_id,
        "resolve_remark": resolve_remark.strip(),
    }


def list_review_logs(db: Session, case_id: str) -> list[dict]:
    rows = db.execute(
        select(ReviewLog).where(ReviewLog.case_id == case_id).order_by(ReviewLog.created_at.asc())
    ).scalars().all()
    return [
        {
            "log_id": r.id,
            "case_id": r.case_id,
            "operator_id": r.operator_id,
            "action_type": r.action_type,
            "action_remark": r.action_remark,
            "created_at": r.created_at,
        }
        for r in rows
    ]
