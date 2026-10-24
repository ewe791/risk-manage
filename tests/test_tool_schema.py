"""E1 工具 Schema 合法性测试（评测文档模块 E1，8 个用例）。

不依赖真实 LLM，直接对 app.agent.tools.TOOLS 的 JSON Schema 做结构断言。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent.tools import TOOLS  # noqa: E402

EXPECT_EVENT_TYPES = {"order_create", "order_pay", "after_sale_apply", "logistics_complaint"}
NO_USER_ID_TOOLS = {
    "get_assessment",
    "list_rules",
    "toggle_rule",
    "list_cases",
    "review_case",
    "get_user_profile",
    "get_dashboard",
    "manage_blacklist",
}


def functions() -> list[dict]:
    return [t["function"] for t in TOOLS]


def by_name(name: str) -> dict:
    return next(f for f in functions() if f["name"] == name)


def E1_1_all_type_function():
    assert TOOLS, "工具清单不能为空"
    for tool in TOOLS:
        assert tool.get("type") == "function", f"{tool.get('function', {}).get('name')} type 不是 function"


def E1_2_has_name_desc_params():
    for fn in functions():
        assert fn.get("name"), "缺少 name"
        assert fn.get("description"), f"{fn['name']} 缺少 description"
        assert isinstance(fn.get("parameters"), dict), f"{fn['name']} 缺少 parameters"


def E1_3_parameters_shape():
    for fn in functions():
        params = fn["parameters"]
        assert params.get("type") == "object", f"{fn['name']} parameters.type 必须是 object"
        assert "properties" in params, f"{fn['name']} 缺少 properties"
        assert "required" in params, f"{fn['name']} 缺少 required"
        assert isinstance(params["required"], list)


def E1_4_user_id_only_in_risk_check():
    for fn in functions():
        props = fn["parameters"].get("properties") or {}
        if fn["name"] == "risk_check":
            assert "user_id" in props, "risk_check 必须允许 user_id"
        elif fn["name"] in NO_USER_ID_TOOLS:
            assert "user_id" not in props, f"{fn['name']} 的 schema 不得出现 user_id"


def E1_5_no_operator_id():
    for fn in functions():
        props = fn["parameters"].get("properties") or {}
        assert "operator_id" not in props, f"{fn['name']} 不得暴露 operator_id"
        assert "operator_id" not in fn["parameters"].get("required", [])


def E1_6_event_type_enum():
    params = by_name("risk_check")["parameters"]
    enum = params["properties"]["event_type"]["enum"]
    assert set(enum) == EXPECT_EVENT_TYPES, f"event_type 枚举不符: {enum}"


def E1_7_toggle_rule_status_enum():
    params = by_name("toggle_rule")["parameters"]
    assert set(params["properties"]["target_status"]["enum"]) == {"enabled", "disabled"}
    assert "rule_id" in params["required"], "toggle_rule 必须要求 rule_id"


def E1_8_review_case_result_enum():
    params = by_name("review_case")["parameters"]
    enum = set(params["properties"]["review_result"]["enum"])
    assert {"approved", "rejected", "resolved"} <= enum, f"review_result 枚举缺项: {enum}"
    assert "case_id" in params["required"]
    assert "review_remark" in params["required"]


@pytest.mark.parametrize(
    "case_id,fn",
    [
        ("E1-1", E1_1_all_type_function),
        ("E1-2", E1_2_has_name_desc_params),
        ("E1-3", E1_3_parameters_shape),
        ("E1-4", E1_4_user_id_only_in_risk_check),
        ("E1-5", E1_5_no_operator_id),
        ("E1-6", E1_6_event_type_enum),
        ("E1-7", E1_7_toggle_rule_status_enum),
        ("E1-8", E1_8_review_case_result_enum),
    ],
)
def test_tool_schema(case_id, fn):
    fn()


def test_tool_inventory():
    """附：9 个工具齐备，且 risk_check 三参数为必填。"""
    names = {f["name"] for f in functions()}
    assert names == {
        "risk_check",
        "get_assessment",
        "list_rules",
        "toggle_rule",
        "list_cases",
        "review_case",
        "get_user_profile",
        "get_dashboard",
        "manage_blacklist",
    }
    required = by_name("risk_check")["parameters"]["required"]
    assert {"event_type", "user_id", "order_id"} <= set(required)
