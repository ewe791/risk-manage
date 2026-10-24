"""一键导入演示数据：24 条规则 + 3 个用户/9 笔订单（上游快照）+ 黑名单 + 历史评估/案件。

用法（在 risk_agent 目录下）：
    python seed/init_seed.py            # 幂等导入
    python seed/init_seed.py --reset    # 清库重建后再导入
    python seed/init_seed.py --check    # 只做特征/评分自检，不写库

设计：
- 规则与黑名单按业务唯一键 upsert，重复执行不会产生重复数据
- 历史事件用 source_id = SEED-EV-* 标记，重复执行自动跳过
- 最后对 3 个演示订单做一次 dry-run，打印 25 特征完整性与预期评分，
  任何人接手都能一眼确认数据是否可用
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

import app.models  # noqa: F401,E402  注册元数据
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import (  # noqa: E402
    Blacklist,
    FeatureSnapshot,
    ReviewLog,
    RiskAssessment,
    RiskCase,
    RiskEvent,
    RiskRule,
    RuleHit,
    gen_id,
)
from app.services import source_adapter as upstream  # noqa: E402
from app.services.feature_service import FEATURE_NAMES, build_feature_snapshot  # noqa: E402
from app.services.risk_service import map_decision, map_level  # noqa: E402
from app.services.rule_engine import evaluate_rule  # noqa: E402
from app.services.rule_service import validate_condition  # noqa: E402

SEED_DIR = Path(__file__).resolve().parent


def _load(name: str):
    return json.loads((SEED_DIR / name).read_text(encoding="utf-8"))


def seed_rules(db) -> tuple[int, int]:
    rules = _load("rules.json")
    created = updated = 0
    for item in rules:
        validate_condition(item["condition_json"])
        existing = db.execute(
            select(RiskRule).where(RiskRule.rule_code == item["rule_code"])
        ).scalars().first()
        if existing:
            existing.rule_name = item["rule_name"]
            existing.priority = item["priority"]
            existing.score = item["score"]
            existing.condition_json = item["condition_json"]
            existing.description = item.get("description")
            existing.rule_status = item.get("rule_status", "enabled")
            existing.updated_at = datetime.now(timezone.utc)
            updated += 1
        else:
            db.add(
                RiskRule(
                    id=gen_id("RULE"),
                    rule_code=item["rule_code"],
                    rule_name=item["rule_name"],
                    rule_status=item.get("rule_status", "enabled"),
                    priority=item["priority"],
                    score=item["score"],
                    condition_json=item["condition_json"],
                    description=item.get("description"),
                    updated_at=datetime.now(timezone.utc),
                )
            )
            created += 1
    db.commit()
    return created, updated


def seed_blacklist(db) -> int:
    items = _load("demo_blacklist.json")
    created = 0
    for item in items:
        exists = db.execute(
            select(Blacklist).where(
                Blacklist.blacklist_type == item["blacklist_type"],
                Blacklist.blacklist_value == item["blacklist_value"],
            )
        ).scalars().first()
        if exists:
            continue
        db.add(
            Blacklist(
                id=gen_id("BL"),
                blacklist_type=item["blacklist_type"],
                blacklist_value=item["blacklist_value"],
                remark=item.get("remark"),
                status=item.get("status", "active"),
                created_at=datetime.now(timezone.utc),
            )
        )
        created += 1
    db.commit()
    return created


HISTORY = [
    {
        "source_id": "SEED-EV-1",
        "event_type": "after_sale_apply",
        "user_id": "U1001",
        "order_id": "O1997",
        "days_ago": 25,
        "score": 75,
        "hits": [("R01", 25), ("R05", 30), ("R11", 20)],
        "case": {"status": "approved", "result": "approve", "operator": "OP-reviewer", "remark": "确认恶意退款，已追回款项并冻结账号额度"},
    },
    {
        "source_id": "SEED-EV-2",
        "event_type": "order_pay",
        "user_id": "U1001",
        "order_id": "O1999",
        "days_ago": 15,
        "score": 48,
        "hits": [("R02", 18), ("R05", 30)],
        "case": None,
    },
    {
        "source_id": "SEED-EV-3",
        "event_type": "logistics_complaint",
        "user_id": "U1001",
        "order_id": "O2000",
        "days_ago": 7,
        "score": 93,
        "hits": [("R01", 25), ("R02", 18), ("R05", 30), ("R11", 20)],
        "case": {"status": "pending", "result": None, "operator": None, "remark": None},
    },
]


def seed_history(db) -> int:
    """写入历史事件 + 评估 + 命中 + 案件 + 审核日志（幂等）。"""
    now = datetime.now(timezone.utc)
    rule_map = {
        r.rule_code: r for r in db.execute(select(RiskRule)).scalars().all()
    }
    created = 0
    for item in HISTORY:
        exists = db.execute(
            select(RiskEvent).where(RiskEvent.source_id == item["source_id"])
        ).scalars().first()
        if exists:
            continue
        created_at = now - timedelta(days=item["days_ago"])
        event = RiskEvent(
            id=gen_id("RE"),
            event_type=item["event_type"],
            source_id=item["source_id"],
            user_id=item["user_id"],
            order_id=item["order_id"],
            event_payload_json={
                "seeded": True,
                "event_type": item["event_type"],
                "user_id": item["user_id"],
                "order_id": item["order_id"],
            },
            created_at=created_at,
        )
        db.add(event)
        db.flush()

        score = min(100, sum(s for _, s in item["hits"]))
        assessment = RiskAssessment(
            id=gen_id("RA"),
            event_id=event.id,
            risk_score=score,
            risk_level=map_level(score),
            decision=map_decision(score),
            assessment_status="finished",
            created_at=created_at,
        )
        db.add(assessment)
        db.flush()

        for code, hit_score in item["hits"]:
            rule = rule_map.get(code)
            if not rule:
                continue
            db.add(
                RuleHit(
                    id=gen_id("RH"),
                    assessment_id=assessment.id,
                    rule_id=rule.id,
                    hit_score=hit_score,
                    hit_message=f"{rule.rule_name}（命中 {hit_score} 分）：历史评估留痕",
                    created_at=created_at,
                )
            )

        if item["case"]:
            case = RiskCase(
                id=gen_id("CASE"),
                assessment_id=assessment.id,
                user_id=item["user_id"],
                order_id=item["order_id"],
                case_status=item["case"]["status"],
                reviewer_id=item["case"]["operator"],
                review_result=item["case"]["result"],
                created_at=created_at,
                updated_at=created_at + timedelta(hours=5),
            )
            db.add(case)
            db.flush()
            if item["case"].get("operator"):
                db.add(
                    ReviewLog(
                        id=gen_id("RL"),
                        case_id=case.id,
                        operator_id=item["case"]["operator"],
                        action_type=f"review:{item['case']['result']}",
                        action_remark=item["case"]["remark"],
                        created_at=created_at + timedelta(hours=5),
                    )
                )
        created += 1
    db.commit()
    return created


def dry_run_check(db) -> None:
    """对演示订单做一次只读推演，打印 25 特征与预期评分。"""
    upstream.reload()
    print("\n【特征与评分自检】")
    print(f"{'订单':<8}{'用户':<8}{'特征数':<8}{'预期评分':<10}{'等级':<10}{'建议':<14}命中规则")
    rules = db.execute(
        select(RiskRule).where(RiskRule.rule_status == "enabled").order_by(RiskRule.priority)
    ).scalars().all()
    for order_id, user_id in [("O2001", "U1001"), ("O2002", "U1002"), ("O2003", "U1003")]:
        features = build_feature_snapshot(db, user_id, order_id)
        assert len(features) == 25, f"特征数量异常: {len(features)}"
        missing = [n for n in FEATURE_NAMES if n not in features]
        hits = []
        for rule in rules:
            hit, score = evaluate_rule(rule, features)
            if hit:
                hits.append(f"{rule.rule_code}({score})")
        total = min(100, sum(int(h.split("(")[1].rstrip(")")) for h in hits))
        print(
            f"{order_id:<8}{user_id:<8}{len(features):<8}{total:<10}{map_level(total):<10}{map_decision(total):<14}{', '.join(hits) or '-'}"
        )
        if missing:
            print("  缺失特征:", missing)


def main() -> None:
    parser = argparse.ArgumentParser(description="导入电商风控 Agent 演示数据")
    parser.add_argument("--reset", action="store_true", help="删除全部表后重建")
    parser.add_argument("--check", action="store_true", help="只做自检，不写库")
    args = parser.parse_args()

    if args.reset:
        print("正在重建数据库表…")
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        if args.check:
            dry_run_check(db)
            return
        created, updated = seed_rules(db)
        bl = seed_blacklist(db)
        hist = seed_history(db)
        tables = sorted(Base.metadata.tables.keys())
        print(f"建表完成：{len(tables)} 张 -> {', '.join(tables)}")
        print(f"规则：新增 {created} 条，更新 {updated} 条")
        print(f"黑名单：新增 {bl} 条")
        print(f"历史事件/评估/案件：新增 {hist} 组")
        dry_run_check(db)
        print("\n演示入口：")
        print("  1) U1001 + O2001 → 高风险、自动建案、命中 4 条规则")
        print("  2) 停用 R05 后重查同一订单 → 中风险、不再建案")
        print("  3) GET /api/risk/cases 提交审核 → 查看 review_logs")
        print(f"\n金额精度示例：order_amount={Decimal('4200.00')}（Decimal，非 float）")
    finally:
        db.close()


if __name__ == "__main__":
    main()
