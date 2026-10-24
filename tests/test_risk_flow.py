"""R3/R4 集成测试：25 特征完整性、评分分级、自动建案、停用规则后降级。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.services import source_adapter as upstream  # noqa: E402
from app.services.feature_service import FEATURE_NAMES, build_feature_snapshot  # noqa: E402
from app.services.risk_service import check_risk, map_decision, map_level  # noqa: E402

import app.models  # noqa: F401,E402
from seed.init_seed import seed_blacklist, seed_history, seed_rules  # noqa: E402


@pytest.fixture(scope="module")
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    seed_rules(session)
    seed_blacklist(session)
    seed_history(session)
    upstream.reload()
    yield session
    session.close()


def test_snapshot_has_25_keys(db):
    features = build_feature_snapshot(db, "U1001", "O2001")
    assert len(features) == 25
    assert set(features) == set(FEATURE_NAMES)


def test_level_decision_mapping():
    assert map_level(100) == "high" and map_level(70) == "high"
    assert map_level(69) == "medium" and map_level(40) == "medium"
    assert map_level(39) == "low"
    assert map_decision(90) == "reject" and map_decision(89) == "manual_review"
    assert map_decision(70) == "manual_review" and map_decision(69) == "pass"


def test_high_risk_creates_case(db):
    result = asyncio.run(
        check_risk(db, "order_pay", "SRC-T1", "U1001", "O2001", "OP-test")
    )
    assert result["risk_score"] >= 70
    assert result["risk_level"] == "high"
    assert result["decision"] in ("reject", "manual_review")
    assert result["case_id"], "高风险必须自动建案"
    assert len(result["rule_hits"]) >= 2
    assert len(result["feature_snapshot"]) == 25


def test_disable_rule_drops_score(db):
    from app.models import RiskRule
    from sqlalchemy import select

    rule = db.execute(select(RiskRule).where(RiskRule.rule_code == "R05")).scalars().first()
    rule.rule_status = "disabled"
    db.commit()
    try:
        result = asyncio.run(
            check_risk(db, "order_pay", "SRC-T2", "U1001", "O2001", "OP-test")
        )
        assert result["risk_level"] == "medium"
        assert result["decision"] == "pass"
        assert result["case_id"] is None
    finally:
        rule.rule_status = "enabled"
        db.commit()


def test_normal_user_low_risk(db):
    result = asyncio.run(
        check_risk(db, "order_create", "SRC-T3", "U1003", "O2003", "OP-test")
    )
    assert result["risk_level"] == "low"
    assert result["decision"] == "pass"
    assert result["case_id"] is None
