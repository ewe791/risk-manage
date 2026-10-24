"""R2 规则引擎单测：覆盖文档要求的 7 个用例 + 边界case。"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.rule_engine import evaluate, evaluate_rule  # noqa: E402


def test_single_condition_hit():
    cond = {"op": "and", "conditions": [{"field": "refund_count_30d", "op": ">", "value": 3}]}
    assert evaluate(cond, {"refund_count_30d": 4}) is True


def test_single_condition_miss():
    cond = {"op": "and", "conditions": [{"field": "refund_count_30d", "op": ">", "value": 3}]}
    assert evaluate(cond, {"refund_count_30d": 2}) is False


def test_and_all_hit():
    cond = {
        "op": "and",
        "conditions": [
            {"field": "order_amount", "op": ">", "value": 1000},
            {"field": "pay_method", "op": "=", "value": "credit_card"},
            {"field": "device_risk", "op": ">=", "value": 70},
        ],
    }
    assert evaluate(cond, {"order_amount": 4200, "pay_method": "credit_card", "device_risk": 85}) is True
    # and 需要全部命中
    assert evaluate(cond, {"order_amount": 4200, "pay_method": "alipay", "device_risk": 85}) is False


def test_or_any_hit():
    cond = {
        "op": "or",
        "conditions": [
            {"field": "address_in_blacklist", "op": "=", "value": True},
            {"field": "order_amount", "op": ">", "value": 5000},
        ],
    }
    assert evaluate(cond, {"address_in_blacklist": True, "order_amount": 100}) is True
    assert evaluate(cond, {"address_in_blacklist": False, "order_amount": 6000}) is True
    assert evaluate(cond, {"address_in_blacklist": False, "order_amount": 100}) is False


def test_three_level_nesting():
    cond = {
        "op": "and",
        "conditions": [
            {"field": "user_reg_days", "op": "<=", "value": 7},
            {
                "op": "or",
                "conditions": [
                    {"field": "user_blacklist_hit", "op": "=", "value": True},
                    {
                        "op": "and",
                        "conditions": [
                            {"field": "order_amount", "op": ">", "value": 3000},
                            {"field": "device_risk", "op": ">=", "value": 70},
                        ],
                    },
                ],
            },
        ],
    }
    assert evaluate(cond, {"user_reg_days": 3, "user_blacklist_hit": False, "order_amount": 5000, "device_risk": 90}) is True
    assert evaluate(cond, {"user_reg_days": 30, "user_blacklist_hit": True}) is False
    assert evaluate(cond, {"user_reg_days": 2, "user_blacklist_hit": False, "order_amount": 100, "device_risk": 90}) is False


def test_missing_field_not_hit():
    cond = {"op": "and", "conditions": [{"field": "not_exists", "op": ">", "value": 1}]}
    assert evaluate(cond, {"order_amount": 100}) is False
    # or 中缺失分支不影响其它分支
    cond_or = {
        "op": "or",
        "conditions": [
            {"field": "not_exists", "op": ">", "value": 1},
            {"field": "order_amount", "op": ">", "value": 1},
        ],
    }
    assert evaluate(cond_or, {"order_amount": 100}) is True


def test_none_value_not_hit():
    cond = {"op": "and", "conditions": [{"field": "refund_rate", "op": "<", "value": 0.1}]}
    assert evaluate(cond, {"refund_rate": None}) is False
    assert evaluate(cond, {"refund_rate": 0.05}) is True


def test_numeric_string_conversion():
    """Decimal/字符串金额需能被 float() 转换后比较。"""
    cond = {"op": "and", "conditions": [{"field": "order_amount", "op": ">", "value": 5000}]}
    assert evaluate(cond, {"order_amount": "6800.00"}) is True
    assert evaluate(cond, {"order_amount": "abc"}) is False


def test_contains_string_and_list():
    cond_str = {"op": "and", "conditions": [{"field": "pay_method", "op": "contains", "value": "card"}]}
    assert evaluate(cond_str, {"pay_method": "credit_card"}) is True
    assert evaluate(cond_str, {"pay_method": "alipay"}) is False
    cond_list = {"op": "and", "conditions": [{"field": "tags", "op": "contains", "value": "fraud"}]}
    assert evaluate(cond_list, {"tags": ["fraud", "refund"]}) is True


def test_evaluate_rule_returns_score():
    rule = SimpleNamespace(
        score=25,
        condition_json={"op": "and", "conditions": [{"field": "refund_count", "op": ">=", "value": 4}]},
    )
    assert evaluate_rule(rule, {"refund_count": 5}) == (True, 25)
    assert evaluate_rule(rule, {"refund_count": 1}) == (False, 0)


@pytest.mark.parametrize("bad", [None, {}, {"op": "unknown"}, {"op": "and"}])
def test_invalid_condition_no_raise(bad):
    assert evaluate(bad, {"a": 1}) is False
