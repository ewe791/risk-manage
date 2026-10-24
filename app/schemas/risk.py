"""请求/响应体定义。金额与评分使用字符串或 int，避免 float 精度问题。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

EventType = Literal["order_create", "order_pay", "after_sale_apply", "logistics_complaint"]


class RiskCheckRequest(BaseModel):
    event_type: EventType
    source_id: str | None = Field(default=None, max_length=64)
    user_id: str = Field(min_length=1, max_length=64)
    order_id: str | None = Field(default=None, max_length=64)


class RuleCreateRequest(BaseModel):
    rule_code: str = Field(min_length=2, max_length=32)
    rule_name: str = Field(min_length=1, max_length=128)
    rule_status: Literal["enabled", "disabled"] = "enabled"
    priority: int = Field(default=100, ge=0, le=9999)
    score: int = Field(default=0, ge=0, le=100)
    condition_json: dict
    description: str | None = None


class RuleUpdateRequest(BaseModel):
    rule_id: str
    rule_name: str | None = Field(default=None, max_length=128)
    rule_status: Literal["enabled", "disabled"] | None = None
    priority: int | None = Field(default=None, ge=0, le=9999)
    score: int | None = Field(default=None, ge=0, le=100)
    condition_json: dict | None = None
    description: str | None = None


class RuleStatusRequest(BaseModel):
    rule_id: str
    target_status: Literal["enabled", "disabled"]


class RuleDeleteRequest(BaseModel):
    rule_id: str


class CaseReviewRequest(BaseModel):
    case_id: str
    review_result: Literal["approve", "reject", "escalate", "approved", "rejected", "resolved"]
    review_remark: str = Field(min_length=1, max_length=1000)


class CaseResolveRequest(BaseModel):
    case_id: str
    resolve_remark: str = Field(min_length=1, max_length=1000)


class BlacklistCreateRequest(BaseModel):
    blacklist_type: Literal["user", "address", "ip", "device"]
    blacklist_value: str = Field(min_length=1, max_length=128)
    remark: str | None = Field(default=None, max_length=255)
    status: Literal["active", "inactive"] = "active"


class BlacklistImportItem(BaseModel):
    blacklist_type: Literal["user", "address", "ip", "device"]
    blacklist_value: str = Field(min_length=1, max_length=128)
    remark: str | None = Field(default=None, max_length=255)


class BlacklistImportRequest(BaseModel):
    """二选一：items 结构化数组，或 text 文本（每行 类型,名单值,备注）。"""

    items: list[BlacklistImportItem] | None = None
    text: str | None = Field(default=None, max_length=100000)


class BlacklistDeleteRequest(BaseModel):
    blacklist_id: str


class LoginRequest(BaseModel):
    username: str
    password: str


class ChatMessageInput(BaseModel):
    role: Literal["user", "assistant", "tool", "system"]
    content: str = ""
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    card: dict[str, Any] | None = None


class ChatRequest(BaseModel):
    conversation_id: str | None = Field(default=None, max_length=64)
    message: str = Field(min_length=1, max_length=4000)
