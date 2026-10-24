"""R2 规则引擎：condition_json 递归求值。

condition_json 结构：
    {"op": "and", "conditions": [
        {"field": "refund_count_30d", "op": ">", "value": 3},
        {"op": "or", "conditions": [
            {"field": "address_in_blacklist", "op": "=", "value": true},
            {"field": "order_amount", "op": ">", "value": 5000}
        ]}
    ]}

求值语义（严格按文档 3 节）：
- and / or 支持无限深度嵌套；空 conditions / 未知 op 一律返回 False（不可求值即不命中）
- 叶子节点字段不存在、或值为 None → 视为不命中（False）
- 数值比较前先 float() 转换，转换失败 → False
- contains：字符串包含 / 列表包含 / dict 的键包含
- 比较运算异常一律吞掉并返回 False，规则引擎永不抛出业务异常
"""

from __future__ import annotations

from typing import Any

LOGIC_OPS = {"and", "or"}
COMPARE_OPS = {">", "<", ">=", "<=", "=", "!=", "contains"}
SUPPORTED_OPS = LOGIC_OPS | COMPARE_OPS

TOKEN = object()  # 字段缺失标记


def _resolve(features: dict, field: str | None) -> Any:
    """取特征值；支持 a.b 形式的浅层路径；缺失返回 TOKEN。"""
    if not field:
        return TOKEN
    if field in features:
        return features[field]
    if "." in field:
        cur: Any = features
        for part in field.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return TOKEN
            cur = cur[part]
        return cur
    return TOKEN


def _to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compare(left: Any, op: str, right: Any) -> bool:
    if left is TOKEN or left is None:
        return False
    if op == "contains":
        if right is None:
            return False
        if isinstance(left, str):
            return str(right) in left
        if isinstance(left, (list, tuple, set)):
            return right in left
        if isinstance(left, dict):
            return right in left
        return False
    if op == "=":
        if isinstance(left, bool) or isinstance(right, bool):
            return left == right
        return left == right
    if op == "!=":
        return left != right
    # 数值比较
    left_num, right_num = _to_number(left), _to_number(right)
    if left_num is None or right_num is None:
        return False
    if op == ">":
        return left_num > right_num
    if op == "<":
        return left_num < right_num
    if op == ">=":
        return left_num >= right_num
    if op == "<=":
        return left_num <= right_num
    return False


def evaluate(condition: dict | None, features: dict) -> bool:
    """递归求值 condition_json（见模块 docstring）。"""
    if not condition or not isinstance(condition, dict):
        return False
    features = features or {}
    op = condition.get("op")

    if op in LOGIC_OPS:
        children = condition.get("conditions") or []
        if not isinstance(children, list) or not children:
            # 空条件视为"无法求值"，不命中：风控场景宁可不报，也不能让空规则恒真误伤
            return False
        if op == "and":
            return all(evaluate(child, features) for child in children)
        return any(evaluate(child, features) for child in children)

    if op in COMPARE_OPS:
        left = _resolve(features, condition.get("field"))
        if left is TOKEN or left is None:
            return False
        try:
            return _compare(left, op, condition.get("value"))
        except Exception:  # noqa: BLE001 —— 规则求值不允许抛异常
            return False

    # 未识别的 op（含老式 {"field","operator","value"}）→ 不命中
    return False


def evaluate_rule(rule, features: dict) -> tuple[bool, int]:
    """返回 (是否命中, 命中分值)；命中分值取规则自身 score。"""
    hit = evaluate(getattr(rule, "condition_json", None), features)
    return hit, int(getattr(rule, "score", 0) or 0) if hit else 0
