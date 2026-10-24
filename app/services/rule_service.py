"""规则管理服务：分页查询、新增、更新、启停、删除，含 condition_json 结构校验。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import RiskRule, RuleHit, gen_id
from app.services.rule_engine import SUPPORTED_OPS


class RuleError(ValueError):
    pass


RULE_STATUSES = {"enabled", "disabled"}


def validate_condition(node, depth: int = 0) -> None:
    """递归校验 condition_json：只允许约定 op，叶子必须有 field。"""
    if depth > 20:
        raise RuleError("condition_json 嵌套过深（>20）")
    if not isinstance(node, dict):
        raise RuleError("condition_json 节点必须是对象")
    op = node.get("op")
    if op not in SUPPORTED_OPS:
        raise RuleError(f"不支持的 op: {op!r}，允许 {sorted(SUPPORTED_OPS)}")
    if op in ("and", "or"):
        children = node.get("conditions")
        if not isinstance(children, list) or not children:
            raise RuleError(f"{op} 节点必须包含非空 conditions 数组")
        for child in children:
            validate_condition(child, depth + 1)
        return
    if not node.get("field"):
        raise RuleError(f"op={op} 的叶子节点必须包含 field")


def serialize_rule(rule: RiskRule, hit_count: int | None = None, last_hit_at=None) -> dict:
    return {
        "rule_id": rule.id,
        "rule_code": rule.rule_code,
        "rule_name": rule.rule_name,
        "rule_status": rule.rule_status,
        "priority": rule.priority,
        "score": rule.score,
        "condition_json": rule.condition_json,
        "description": rule.description,
        "updated_at": rule.updated_at,
        # 页面需要展示命中次数（文档 2.3.3 规则管理页）
        "hit_count": int(hit_count or 0),
        "last_hit_at": last_hit_at,
    }


def _hit_stats(db: Session, rule_ids: list[str]) -> dict[str, tuple[int, object]]:
    """本页规则的命中次数/最近命中时间，一条聚合 SQL 取回（避免逐行查询）。"""
    if not rule_ids:
        return {}
    rows = db.execute(
        select(RuleHit.rule_id, func.count(RuleHit.id), func.max(RuleHit.created_at))
        .where(RuleHit.rule_id.in_(rule_ids))
        .group_by(RuleHit.rule_id)
    ).all()
    return {rule_id: (int(cnt or 0), last) for rule_id, cnt, last in rows}


def list_rules(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    rule_status: str | None = None,
    keyword: str | None = None,
) -> dict:
    stmt = select(RiskRule)
    count_stmt = select(func.count(RiskRule.id))
    conds = []
    if rule_status:
        conds.append(RiskRule.rule_status == rule_status)
    if keyword:
        like = f"%{keyword}%"
        conds.append(RiskRule.rule_name.like(like) | RiskRule.rule_code.like(like))
    if conds:
        stmt = stmt.where(*conds)
        count_stmt = count_stmt.where(*conds)
    total = int(db.execute(count_stmt).scalar() or 0)
    rows = db.execute(
        stmt.order_by(RiskRule.priority.asc(), RiskRule.rule_code.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).scalars().all()
    stats = _hit_stats(db, [r.id for r in rows])
    items = [
        serialize_rule(r, *stats.get(r.id, (0, None)))
        for r in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def get_rule(db: Session, rule_id: str) -> RiskRule:
    rule = db.get(RiskRule, rule_id)
    if not rule:
        raise RuleError(f"规则不存在: {rule_id}")
    return rule


def create_rule(db: Session, payload: dict) -> dict:
    code = (payload.get("rule_code") or "").strip()
    name = (payload.get("rule_name") or "").strip()
    if not code or not name:
        raise RuleError("rule_code 与 rule_name 必填")
    exists = db.execute(select(RiskRule).where(RiskRule.rule_code == code)).scalars().first()
    if exists:
        raise RuleError(f"rule_code 已存在: {code}")
    condition = payload.get("condition_json") or {}
    validate_condition(condition)
    status = payload.get("rule_status") or "enabled"
    if status not in RULE_STATUSES:
        raise RuleError(f"rule_status 仅支持 {sorted(RULE_STATUSES)}")
    score = int(payload.get("score") or 0)
    if not 0 <= score <= 100:
        raise RuleError("score 必须在 0-100")
    rule = RiskRule(
        id=gen_id("RULE"),
        rule_code=code,
        rule_name=name,
        rule_status=status,
        priority=int(payload.get("priority") or 100),
        score=score,
        condition_json=condition,
        description=payload.get("description"),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(rule)
    db.commit()
    return serialize_rule(rule)


def update_rule(db: Session, payload: dict) -> dict:
    rule_id = payload.get("rule_id")
    if not rule_id:
        raise RuleError("rule_id 必填")
    rule = get_rule(db, rule_id)
    if payload.get("rule_name"):
        rule.rule_name = payload["rule_name"]
    if payload.get("condition_json") is not None:
        validate_condition(payload["condition_json"])
        rule.condition_json = payload["condition_json"]
    if payload.get("score") is not None:
        score = int(payload["score"])
        if not 0 <= score <= 100:
            raise RuleError("score 必须在 0-100")
        rule.score = score
    if payload.get("priority") is not None:
        rule.priority = int(payload["priority"])
    if payload.get("description") is not None:
        rule.description = payload["description"]
    if payload.get("rule_status") is not None:
        if payload["rule_status"] not in RULE_STATUSES:
            raise RuleError(f"rule_status 仅支持 {sorted(RULE_STATUSES)}")
        rule.rule_status = payload["rule_status"]
    rule.updated_at = datetime.now(timezone.utc)
    db.commit()
    return serialize_rule(rule)


def set_status(db: Session, rule_id: str, target_status: str) -> dict:
    if target_status not in RULE_STATUSES:
        raise RuleError(f"target_status 仅支持 {sorted(RULE_STATUSES)}")
    rule = get_rule(db, rule_id)
    rule.rule_status = target_status
    rule.updated_at = datetime.now(timezone.utc)
    db.commit()
    return serialize_rule(rule)


def delete_rule(db: Session, rule_id: str) -> dict:
    rule = get_rule(db, rule_id)
    # 先清理历史命中，避免外键约束阻断删除
    for hit in db.execute(select(RuleHit).where(RuleHit.rule_id == rule_id)).scalars().all():
        db.delete(hit)
    db.delete(rule)
    db.commit()
    return {"rule_id": rule_id, "deleted": True}


def list_enabled_rules(db: Session) -> list[RiskRule]:
    return list(
        db.execute(
            select(RiskRule)
            .where(RiskRule.rule_status == "enabled")
            .order_by(RiskRule.priority.asc())
        ).scalars().all()
    )
