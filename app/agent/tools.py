"""R6 Agent 工具层：9 个 OpenAI function calling 工具。

约定（文档 7.2）：
- 每个工具一个 Pydantic 入参模型 + 一个 async tool_xxx(db, operator_id, **kwargs)
- 参数 JSON Schema 由 Pydantic 模型生成，保证 schema 与校验规则永不漂移
- 工具内部只调 services 层，不重复业务逻辑
- 异常统一捕获并返回 {"error": "..."}，由 orchestrator 以 role=tool 回填给模型
- 所有工具不暴露 operator_id；user_id 仅出现在 risk_check（其余工具通过会话
  上下文注入主体用户，防止 LLM 自造/越权指定用户）；user_id 也绝不作为身份凭据

注意：除 risk_check 外的工具签名中的 user_id 参数均来自 orchestrator 注入的
会话上下文（AgentContext），不来自 LLM 生成的实参。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.services import (
    blacklist_service,
    case_service,
    dashboard_service,
    profile_service,
    risk_service,
    rule_service,
)

EVENT_TYPES = ["order_create", "order_pay", "after_sale_apply", "logistics_complaint"]


@dataclass
class AgentContext:
    """会话主体上下文：支持"刚才那个订单/用户"的指代解析。"""

    subject_user_id: str | None = None
    last_order_id: str | None = None
    last_assessment_id: str | None = None
    last_case_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "subject_user_id": self.subject_user_id,
            "last_order_id": self.last_order_id,
            "last_assessment_id": self.last_assessment_id,
            "last_case_id": self.last_case_id,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "AgentContext":
        data = data or {}
        return cls(
            subject_user_id=data.get("subject_user_id"),
            last_order_id=data.get("last_order_id"),
            last_assessment_id=data.get("last_assessment_id"),
            last_case_id=data.get("last_case_id"),
        )

    def hint(self) -> str:
        if not self.subject_user_id:
            return "当前会话尚未确定主体用户。"
        parts = [f"当前会话主体用户：{self.subject_user_id}"]
        if self.last_order_id:
            parts.append(f"最近订单：{self.last_order_id}")
        if self.last_assessment_id:
            parts.append(f"最近评估：{self.last_assessment_id}")
        if self.last_case_id:
            parts.append(f"最近案件：{self.last_case_id}")
        return "；".join(parts) + "。用户说\"刚才那个\"时指上述对象。"


# --------------------------------------------------------------------------
# 入参模型（同时用于 JSON Schema 生成与运行时校验）
# --------------------------------------------------------------------------
class RiskCheckArgs(BaseModel):
    event_type: Literal["order_create", "order_pay", "after_sale_apply", "logistics_complaint"] = Field(
        ..., description="风控事件类型：下单/支付/售后申请/物流投诉"
    )
    user_id: str = Field(..., description="被检查的用户 ID，必须由用户明确提供，不得臆造")
    order_id: str = Field(..., description="被检查的订单 ID")
    source_id: str | None = Field(default=None, description="上游来源单号，可选")


class GetAssessmentArgs(BaseModel):
    assessment_id: str = Field(..., description="评估 ID，形如 RA-xxxxxxxx")


class ListRulesArgs(BaseModel):
    rule_status: Literal["enabled", "disabled"] | None = Field(default=None, description="按状态筛选")
    keyword: str | None = Field(default=None, description="按规则名或规则编码模糊搜索")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class ToggleRuleArgs(BaseModel):
    rule_id: str = Field(..., description="规则 ID（由 list_rules 获得，不要猜）")
    target_status: Literal["enabled", "disabled"] = Field(..., description="目标状态：启用或停用")


class ListCasesArgs(BaseModel):
    case_status: Literal["pending", "reviewing", "approved", "rejected"] | None = Field(
        default=None, description="按案件状态筛选"
    )
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class ReviewCaseArgs(BaseModel):
    case_id: str = Field(..., description="案件 ID，形如 CASE-xxxxxxxx")
    review_result: Literal["approve", "reject", "escalate", "approved", "rejected", "resolved"] = Field(
        ...,
        description=(
            "审核结论：approve/approved 通过、reject/rejected 驳回、escalate 升级复核、"
            "resolved 结案归档（两种写法等价，便于不同模型表述）"
        ),
    )
    review_remark: str = Field(..., min_length=1, description="审核备注，必须写明依据")


class GetUserProfileArgs(BaseModel):
    """主体用户由会话上下文决定，不提供 user_id 入参。"""

    pass


class GetDashboardArgs(BaseModel):
    days: int = Field(default=7, ge=1, le=30, description="趋势统计天数")


class ManageBlacklistArgs(BaseModel):
    action: Literal["list", "add", "delete"] = Field(..., description="操作类型")
    blacklist_type: Literal["user", "address", "ip", "device"] | None = Field(
        default=None, description="名单类型"
    )
    blacklist_value: str | None = Field(default=None, description="名单值，如用户ID/地址ID/IP")
    blacklist_id: str | None = Field(default=None, description="删除时使用的记录 ID")
    remark: str | None = Field(default=None, description="新增时的备注")
    keyword: str | None = Field(default=None, description="查询时的模糊匹配值")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


# --------------------------------------------------------------------------
# 工具实现
# --------------------------------------------------------------------------
async def tool_risk_check(
    db: Session, operator_id: str, context: AgentContext | None = None, **kwargs: Any
) -> dict:
    """发起风险检查：写风险事件、计算 25 个特征、跑全部启用规则、输出评分/等级/建议，
    高风险或需人工介入时自动建案。返回 assessment_id、risk_score、risk_level、
    decision、rule_hits、feature_snapshot、case_id。"""
    args = RiskCheckArgs(**kwargs)
    result = await risk_service.check_risk(
        db,
        event_type=args.event_type,
        source_id=args.source_id,
        user_id=args.user_id,
        order_id=args.order_id,
        operator_id=operator_id,
    )
    if context is not None:
        context.subject_user_id = args.user_id
        context.last_order_id = args.order_id
        context.last_assessment_id = result["assessment_id"]
        if result.get("case_id"):
            context.last_case_id = result["case_id"]
    return result


async def tool_get_assessment(
    db: Session, operator_id: str, context: AgentContext | None = None, **kwargs: Any
) -> dict:
    """查询单次评估详情：评分、等级、建议、命中规则明细、25 个特征快照、关联案件。"""
    args = GetAssessmentArgs(**kwargs)
    detail = risk_service.get_assessment_detail(db, args.assessment_id)
    if not detail:
        return {"error": f"评估不存在: {args.assessment_id}"}
    if context is not None:
        event = detail.get("event") or {}
        if event.get("user_id"):
            context.subject_user_id = event["user_id"]
        context.last_assessment_id = detail["assessment_id"]
        context.last_order_id = event.get("order_id") or context.last_order_id
        if detail.get("case_id"):
            context.last_case_id = detail["case_id"]
    return detail


async def tool_list_rules(
    db: Session, operator_id: str, context: AgentContext | None = None, **kwargs: Any
) -> dict:
    """分页查询风控规则，可按启用状态与关键字筛选。返回 rule_id、rule_code、rule_name、
    rule_status、priority、score、condition_json、description。"""
    args = ListRulesArgs(**kwargs)
    data = rule_service.list_rules(
        db, page=args.page, page_size=args.page_size, rule_status=args.rule_status, keyword=args.keyword
    )
    data["enabled_count"] = len(rule_service.list_enabled_rules(db))
    return data


async def tool_toggle_rule(
    db: Session, operator_id: str, context: AgentContext | None = None, **kwargs: Any
) -> dict:
    """启用或停用一条规则。调用前应先用 list_rules 取得 rule_id 并向用户复述规则名。"""
    args = ToggleRuleArgs(**kwargs)
    data = rule_service.set_status(db, args.rule_id, args.target_status)
    return {
        "rule_id": data["rule_id"],
        "rule_code": data["rule_code"],
        "rule_name": data["rule_name"],
        "rule_status": data["rule_status"],
        "message": f"规则 {data['rule_code']} {data['rule_name']} 已{'启用' if data['rule_status'] == 'enabled' else '停用'}",
    }


async def tool_list_cases(
    db: Session, operator_id: str, context: AgentContext | None = None, **kwargs: Any
) -> dict:
    """分页查询风控案件，可按 pending/reviewing/approved/rejected 筛选。返回案件编号、
    状态、关联用户与订单、评分、审核结论。"""
    args = ListCasesArgs(**kwargs)
    return case_service.list_cases(
        db, page=args.page, page_size=args.page_size, case_status=args.case_status
    )


async def tool_review_case(
    db: Session, operator_id: str, context: AgentContext | None = None, **kwargs: Any
) -> dict:
    """提交案件审核结论（approve/reject/escalate），必须提供审核备注；会写入 review_logs
    并把操作员 ID 记录到案件。"""
    args = ReviewCaseArgs(**kwargs)
    data = case_service.review_case(
        db,
        case_id=args.case_id,
        review_result=args.review_result,
        review_remark=args.review_remark,
        operator_id=operator_id,
    )
    if context is not None:
        context.last_case_id = data["case_id"]
    return data


async def tool_get_user_profile(
    db: Session, operator_id: str, context: AgentContext | None = None, **kwargs: Any
) -> dict:
    """查询当前会话主体用户的画像：订单历史、退款/投诉次数、地址数、最近风险事件、
    关联案件。用户 ID 由会话上下文提供，无需入参；若上下文为空会返回提示。"""
    user_id = context.subject_user_id if context else None
    if not user_id:
        return {"error": "当前会话还没有确定主体用户，请先发起一次风险检查（提供 user_id 与 order_id）"}
    return profile_service.get_user_profile(db, user_id)


async def tool_get_dashboard(
    db: Session, operator_id: str, context: AgentContext | None = None, **kwargs: Any
) -> dict:
    """查询风控看板：事件总量、高风险占比、案件处理效率、规则命中排行、
    黑名单命中数与近 N 天趋势。"""
    args = GetDashboardArgs(**kwargs)
    return dashboard_service.get_dashboard(db, days=args.days)


async def tool_manage_blacklist(
    db: Session, operator_id: str, context: AgentContext | None = None, **kwargs: Any
) -> dict:
    """黑名单管理：action=list 查询、action=add 新增（需 blacklist_type 与
    blacklist_value）、action=delete 删除（需 blacklist_id）。"""
    args = ManageBlacklistArgs(**kwargs)
    if args.action == "list":
        return blacklist_service.list_blacklists(
            db,
            page=args.page,
            page_size=args.page_size,
            blacklist_type=args.blacklist_type,
            keyword=args.keyword,
        )
    if args.action == "add":
        if not args.blacklist_type or not args.blacklist_value:
            return {"error": "新增黑名单必须提供 blacklist_type 与 blacklist_value"}
        return blacklist_service.add_blacklist(
            db,
            {
                "blacklist_type": args.blacklist_type,
                "blacklist_value": args.blacklist_value,
                "remark": args.remark,
            },
        )
    if not args.blacklist_id:
        return {"error": "删除黑名单必须提供 blacklist_id（可先 action=list 查询）"}
    return blacklist_service.delete_blacklist(db, args.blacklist_id)


TOOL_IMPLS: dict[str, Callable[..., Awaitable[dict]]] = {
    "risk_check": tool_risk_check,
    "get_assessment": tool_get_assessment,
    "list_rules": tool_list_rules,
    "toggle_rule": tool_toggle_rule,
    "list_cases": tool_list_cases,
    "review_case": tool_review_case,
    "get_user_profile": tool_get_user_profile,
    "get_dashboard": tool_get_dashboard,
    "manage_blacklist": tool_manage_blacklist,
}

TOOL_DESCRIPTIONS = {
    "risk_check": "发起风险检查：写风险事件、计算 25 个特征、跑全部启用规则，返回评分/等级/建议/命中规则/特征快照，高风险会自动建案。",
    "get_assessment": "查询某次评估的详情，包括命中规则明细与 25 个特征快照。",
    "list_rules": "分页查询风控规则，可按状态（enabled/disabled）和关键字筛选。",
    "toggle_rule": "启用或停用指定规则；调用前先 list_rules 获得 rule_id 并复述规则名。",
    "list_cases": "分页查询风控案件，可按状态筛选。",
    "review_case": "提交案件审核结论（approve/reject/escalate），必须附审核备注，写入审核日志。",
    "get_user_profile": "查询当前会话主体用户的画像（订单历史、退款/投诉、地址、风险事件、案件）。",
    "get_dashboard": "查询风控看板统计：事件总量、高风险占比、案件效率、规则命中排行、黑名单命中、趋势。",
    "manage_blacklist": "黑名单查询/新增/删除，action 取 list/add/delete。",
}


def _parameters(model: type[BaseModel]) -> dict:
    """Pydantic → JSON Schema；统一补齐 required 与 type，保证 schema 结构稳定。"""
    schema = model.model_json_schema()
    schema.pop("title", None)
    schema.pop("$defs", None)
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})
    if "required" not in schema:
        schema["required"] = []
    for prop in (schema.get("properties") or {}).values():
        prop.pop("title", None)
    return schema


def build_tool_schemas() -> list[dict]:
    mapping = {
        "risk_check": RiskCheckArgs,
        "get_assessment": GetAssessmentArgs,
        "list_rules": ListRulesArgs,
        "toggle_rule": ToggleRuleArgs,
        "list_cases": ListCasesArgs,
        "review_case": ReviewCaseArgs,
        "get_user_profile": GetUserProfileArgs,
        "get_dashboard": GetDashboardArgs,
        "manage_blacklist": ManageBlacklistArgs,
    }
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": TOOL_DESCRIPTIONS[name],
                "parameters": _parameters(model),
            },
        }
        for name, model in mapping.items()
    ]


TOOLS = build_tool_schemas()

# 角色 → 可调用工具（文档 2.3.2）。admin 恒拥有全部权限。
TOOL_ROLES: dict[str, set[str]] = {
    "risk_check": {"admin", "reviewer"},
    "get_assessment": {"admin", "reviewer", "viewer"},
    "list_rules": {"admin", "reviewer", "viewer"},
    "toggle_rule": {"admin"},
    "list_cases": {"admin", "reviewer", "viewer"},
    "review_case": {"admin", "reviewer"},
    "get_user_profile": {"admin", "reviewer", "viewer"},
    "get_dashboard": {"admin", "reviewer", "viewer"},
    "manage_blacklist": {"admin"},
}


def tools_for_role(role: str) -> list[dict]:
    """按角色裁剪工具清单：schema 里不出现，模型就没有机会调用。"""
    if role == "admin":
        return TOOLS
    return [
        tool
        for tool in TOOLS
        if role in TOOL_ROLES.get(tool["function"]["name"], set())
    ]


async def dispatch(
    name: str,
    db: Session,
    operator_id: str,
    args: dict,
    context: AgentContext | None = None,
    role: str = "admin",
) -> dict:
    """统一分发；异常一律转成 {"error": ...} 供模型判读。

    role 由 API 层从 JWT 取得，与 operator_id 一样不进入 tool schema，
    即使模型强行构造工具名也会在此被拦下。
    """
    impl = TOOL_IMPLS.get(name)
    if not impl:
        return {"error": f"未知工具: {name}"}
    if role != "admin" and role not in TOOL_ROLES.get(name, set()):
        return {"error": f"当前角色（{role}）无权限调用 {name}，请提示用户改用有权限的账号或人工处理"}
    try:
        return await impl(db, operator_id, context=context, **(args or {}))
    except Exception as exc:  # noqa: BLE001 —— 工具异常必须回填给模型
        return {"error": f"{type(exc).__name__}: {exc}"}


def build_card(tool_name: str, result: dict) -> dict | None:
    """把工具结果映射成前端结构化卡片。错误结果不产卡片。"""
    if not isinstance(result, dict) or result.get("error"):
        return None
    if tool_name in ("risk_check", "get_assessment"):
        return {"type": "risk_score", "data": result}
    if tool_name == "list_cases":
        return {"type": "case_list", "data": result}
    if tool_name == "review_case":
        return {"type": "case_review", "data": result}
    if tool_name == "get_dashboard":
        return {"type": "dashboard", "data": result}
    if tool_name == "get_user_profile":
        return {"type": "profile", "data": result}
    if tool_name in ("list_rules", "toggle_rule"):
        return {"type": "rule_list", "data": result}
    if tool_name == "manage_blacklist":
        return {"type": "blacklist", "data": result}
    return None


__all__ = [
    "TOOLS",
    "TOOL_ROLES",
    "AgentContext",
    "build_tool_schemas",
    "tools_for_role",
    "dispatch",
    "build_card",
    "TOOL_IMPLS",
]
