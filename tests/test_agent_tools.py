"""E2 工具调用准确率测试（评测文档模块 E2，22 条用例）。

原则：不依赖真实 LLM。用 MockLLM 直接返回 tool_call / 文本，
断言 orchestrator 的解析 → dispatch → 回填是否正确。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.models  # noqa: E402,F401
from app.agent import orchestrator  # noqa: E402
from app.agent.llm import LLMResponse, ToolCall  # noqa: E402
from app.agent.tools import AgentContext, TOOL_ROLES  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import AgentToolLog, RiskCase, RiskRule  # noqa: E402
from seed.init_seed import seed_blacklist, seed_history, seed_rules  # noqa: E402
from app.services import source_adapter as upstream  # noqa: E402


# --------------------------------------------------------------------------
# Mock LLM
# --------------------------------------------------------------------------
class MockLLM:
    """按队列返回响应；队列耗尽后返回一条纯文本收尾。"""

    def __init__(self, responses: list[LLMResponse], tail: str = "已处理完成。"):
        self.responses = list(responses)
        self.tail = tail
        self.calls = 0

    async def chat(self, messages, tools=None, tool_choice="auto", temperature=None) -> LLMResponse:
        self.calls += 1
        if self.responses:
            return self.responses.pop(0)
        return LLMResponse(content=self.tail)

    async def chat_stream(self, messages, tools=None, tool_choice="auto"):
        resp = await self.chat(messages, tools, tool_choice)
        if resp.content:
            yield "delta", resp.content
        yield "done", resp


def tool_resp(*calls: tuple[str, dict], content: str = "") -> LLMResponse:
    return LLMResponse(
        content=content,
        tool_calls=[
            ToolCall(id=f"call_{i}", name=name, arguments=__import__("json").dumps(args, ensure_ascii=False))
            for i, (name, args) in enumerate(calls)
        ],
    )


def text_resp(content: str) -> LLMResponse:
    return LLMResponse(content=content)


def install(monkeypatch, llm: MockLLM) -> None:
    monkeypatch.setattr(orchestrator, "llm", llm)


def run(db, user_input: str, conversation_id: str | None = None, role: str = "admin") -> dict:
    return asyncio.run(
        orchestrator.run_agent(db, "OP-test", conversation_id, user_input, role=role)
    )


def tool_calls(messages: list[dict]) -> list[tuple[str, dict]]:
    return [(m["name"], m.get("args") or {}) for m in messages if m["role"] == "tool"]


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------
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


@pytest.fixture(autouse=True)
def _mock_llm(monkeypatch):
    """默认不装 mock，各用例自行 install。"""
    return monkeypatch


def rule_id(db, code: str) -> str:
    return db.execute(select(RiskRule).where(RiskRule.rule_code == code)).scalars().one().id


def pending_case(db) -> str:
    case = db.execute(
        select(RiskCase).where(RiskCase.case_status == "pending").limit(1)
    ).scalars().first()
    assert case, "种子数据应至少有一个待审案件"
    return case.id  # ORM 字段是 id，序列化后才叫 case_id


# --------------------------------------------------------------------------
# 用例
# --------------------------------------------------------------------------
def test_E2_1_complete_params(monkeypatch, db):
    install(monkeypatch, MockLLM([tool_resp(("risk_check", {
        "event_type": "order_pay", "user_id": "U1001", "order_id": "O2001"})), text_resp("检查完成")]))
    result = run(db, "查 U1001 订单 O2001 的风险")
    calls = tool_calls(result["messages"])
    assert len(calls) == 1
    name, args = calls[0]
    assert name == "risk_check"
    assert args == {"event_type": "order_pay", "user_id": "U1001", "order_id": "O2001"}
    assert result["type"] == "text"


def test_E2_2_missing_order_id(monkeypatch, db):
    install(monkeypatch, MockLLM([text_resp("请补充订单编号")]))
    result = run(db, "查一下 U1001 的风险")
    assert tool_calls(result["messages"]) == []
    assert result["type"] == "text"


def test_E2_3_missing_event_type(monkeypatch, db):
    install(monkeypatch, MockLLM([text_resp("请问是下单、支付、售后还是物流投诉？")]))
    result = run(db, "查一下 U1001 的订单 O2001")
    assert tool_calls(result["messages"]) == []
    assert result["type"] == "text"


def test_E2_4_missing_user_id(monkeypatch, db):
    install(monkeypatch, MockLLM([text_resp("请提供用户编号")]))
    result = run(db, "查一下订单 O2001 的风险")
    assert tool_calls(result["messages"]) == []


def test_E2_5_invalid_event_type(monkeypatch, db):
    install(monkeypatch, MockLLM([text_resp("仅支持 order_create/order_pay/after_sale_apply/logistics_complaint 四类事件")]))
    result = run(db, "按退款事件查一下 U1001 的 O2001")
    assert tool_calls(result["messages"]) == []
    assert "order_pay" in result["content"]


def test_E2_6_multi_turn_reuse_order_id(monkeypatch, db):
    first = run(
        db,
        "查 U1001 订单 O2001 的风险",
    ) if False else None  # 占位，下面用两轮构造
    rid = rule_id(db, "R05")
    llm = MockLLM([
        tool_resp(("risk_check", {"event_type": "order_pay", "user_id": "U1001", "order_id": "O2001"})),
        text_resp("首轮完成"),
    ])
    install(monkeypatch, llm)
    r1 = run(db, "查 U1001 订单 O2001 的风险")
    cid = r1["conversation_id"]

    llm2 = MockLLM([
        tool_resp(("toggle_rule", {"rule_id": rid, "target_status": "disabled"})),
        tool_resp(("risk_check", {"event_type": "order_pay", "user_id": "U1001", "order_id": "O2001"})),
        text_resp("重查完成"),
    ])
    install(monkeypatch, llm2)
    r2 = run(db, "停用 R05 后重查那个订单", conversation_id=cid)
    calls = tool_calls(r2["messages"])
    assert [c[0] for c in calls] == ["toggle_rule", "risk_check"]
    assert calls[1][1]["order_id"] == "O2001", "第二轮应复用上下文中的订单号"


def test_E2_7_dashboard_vs_profile(monkeypatch, db):
    install(monkeypatch, MockLLM([tool_resp(("get_dashboard", {"days": 7})), text_resp("看板已出")]))
    r_a = run(db, "看板高风险占比")
    assert [c[0] for c in tool_calls(r_a["messages"])] == ["get_dashboard"]

    install(monkeypatch, MockLLM([tool_resp(("get_user_profile", {})), text_resp("画像已出")]))
    r_b = run(db, "U1001 退款几次")
    assert [c[0] for c in tool_calls(r_b["messages"])] == ["get_user_profile"]


def test_E2_8_rules_vs_cases(monkeypatch, db):
    install(monkeypatch, MockLLM([
        tool_resp(("list_rules", {"rule_status": "enabled"})), text_resp("规则如下")]))
    r_a = run(db, "有哪些启用的规则")
    assert tool_calls(r_a["messages"])[0][1]["rule_status"] == "enabled"

    install(monkeypatch, MockLLM([
        tool_resp(("list_cases", {"case_status": "pending"})), text_resp("案件如下")]))
    r_b = run(db, "待审案件")
    assert tool_calls(r_b["messages"])[0][1]["case_status"] == "pending"


def test_E2_9_write_op_confirm_first(monkeypatch, db):
    rid = rule_id(db, "R05")
    install(monkeypatch, MockLLM([
        tool_resp(("list_rules", {"keyword": "R05"})),
        tool_resp(("toggle_rule", {"rule_id": rid, "target_status": "disabled"})),
        text_resp("已停用 R05"),
    ]))
    r = run(db, "把 R05 停用")
    calls = [c[0] for c in tool_calls(r["messages"])]
    assert calls == ["list_rules", "toggle_rule"], f"写操作应先查后改，实际 {calls}"


def test_E2_10_review_missing_remark(monkeypatch, db):
    install(monkeypatch, MockLLM([text_resp("请提供审核备注")]))
    r = run(db, f"通过 {pending_case(db)}")
    assert tool_calls(r["messages"]) == []


def test_E2_11_review_complete(monkeypatch, db):
    case_id = pending_case(db)
    install(monkeypatch, MockLLM([
        tool_resp(("review_case", {
            "case_id": case_id, "review_result": "approved", "review_remark": "资料齐全"})),
        text_resp("已提交审核"),
    ]))
    r = run(db, f"通过 {case_id}，备注：资料齐全")
    calls = tool_calls(r["messages"])
    assert calls[0][0] == "review_case"
    assert calls[0][1] == {
        "case_id": case_id,
        "review_result": "approved",
        "review_remark": "资料齐全",
    }


def test_E2_12_blacklist_add_vs_list(monkeypatch, db):
    install(monkeypatch, MockLLM([
        tool_resp(("manage_blacklist", {
            "action": "add", "blacklist_type": "user", "blacklist_value": "U9999", "remark": "骗赔"})),
        text_resp("已加入"),
    ]))
    r_a = run(db, "加黑名单 user U9999")
    assert tool_calls(r_a["messages"])[0][1]["action"] == "add"

    install(monkeypatch, MockLLM([
        tool_resp(("manage_blacklist", {"action": "list"})), text_resp("名单如下")]))
    r_b = run(db, "看黑名单")
    assert tool_calls(r_b["messages"])[0][1]["action"] == "list"


def test_E2_13_tool_error_backfilled(monkeypatch, db):
    install(monkeypatch, MockLLM([
        tool_resp(("review_case", {
            "case_id": "CASE-NOTEXIST", "review_result": "approved", "review_remark": "测试"})),
        text_resp("该案件不存在，请确认编号"),
    ]))
    r = run(db, "审核 CASE-NOTEXIST")
    tool_msgs = [m for m in r["messages"] if m["role"] == "tool"]
    assert tool_msgs, "异常也必须作为 role=tool 回填"
    assert tool_msgs[0]["ok"] is False
    assert "不存在" in tool_msgs[0]["content"]
    assert r["type"] == "text"


def test_E2_14_max_steps(monkeypatch, db):
    always = MockLLM([tool_resp(("get_dashboard", {"days": 7})) for _ in range(30)])
    install(monkeypatch, always)
    r = run(db, "看板")
    assert r["type"] == "error"
    assert "达到最大工具调用步数" in r["content"]
    assert r["steps"] == 8


def test_E2_15_tool_log_persisted(monkeypatch, db):
    before = db.execute(select(AgentToolLog)).scalars().all()
    before_count = len(before)
    install(monkeypatch, MockLLM([
        tool_resp(("list_rules", {"keyword": "R01"})), text_resp("规则如下")]))
    r = run(db, "查 R01 这条规则")
    db.expire_all()
    rows = db.execute(select(AgentToolLog)).scalars().all()
    assert len(rows) == before_count + 1
    latest = max(rows, key=lambda x: x.created_at)
    assert latest.tool_name == "list_rules"
    assert latest.args_json == {"keyword": "R01"}
    assert isinstance(latest.result_json, dict)
    assert r["type"] == "text"


def test_E2_16_list_rules_keyword(monkeypatch, db):
    install(monkeypatch, MockLLM([
        tool_resp(("list_rules", {"keyword": "黑名单"})), text_resp("命中规则如下")]))
    r = run(db, "查一下和黑名单有关的规则")
    args = tool_calls(r["messages"])[0][1]
    assert args["keyword"] == "黑名单"
    items = [m for m in r["messages"] if m["role"] == "tool"][0]
    assert items["ok"] is True


def test_E2_17_toggle_rule_enable(monkeypatch, db):
    rid = rule_id(db, "R05")
    install(monkeypatch, MockLLM([
        tool_resp(("toggle_rule", {"rule_id": rid, "target_status": "enabled"})), text_resp("已启用")]))
    r = run(db, "恢复启用 R05")
    assert tool_calls(r["messages"])[0][1]["target_status"] == "enabled"
    rule = db.get(RiskRule, rid)
    assert rule.rule_status == "enabled"


def test_E2_18_blacklist_delete(monkeypatch, db):
    from app.models import Blacklist

    item = db.execute(select(Blacklist).limit(1)).scalars().first()
    install(monkeypatch, MockLLM([
        tool_resp(("manage_blacklist", {"action": "delete", "blacklist_id": item.id})),
        text_resp("已删除"),
    ]))
    r = run(db, f"把黑名单 {item.blacklist_value} 删掉")
    assert tool_calls(r["messages"])[0][1]["action"] == "delete"
    assert db.get(Blacklist, item.id) is None


def test_E2_19_get_assessment(monkeypatch, db):
    from app.models import RiskAssessment

    aid = db.execute(select(RiskAssessment).limit(1)).scalars().first().id
    install(monkeypatch, MockLLM([
        tool_resp(("get_assessment", {"assessment_id": aid})), text_resp("详情如下")]))
    r = run(db, f"看下评估 {aid} 的详情")
    assert tool_calls(r["messages"])[0][1]["assessment_id"] == aid
    card = [m for m in r["messages"] if m["role"] == "tool"][0]["card"]
    assert card["type"] == "risk_score"


def test_E2_20_get_dashboard_days(monkeypatch, db):
    install(monkeypatch, MockLLM([
        tool_resp(("get_dashboard", {"days": 14})), text_resp("看板如下")]))
    r = run(db, "最近两周的看板")
    assert tool_calls(r["messages"])[0][1]["days"] == 14
    assert [m for m in r["messages"] if m["role"] == "tool"][0]["ok"] is True


def test_E2_21_viewer_role_tool_filtered(monkeypatch, db):
    """数据查看人（viewer）不应能调用 risk_check：schema 裁剪 + dispatch 拦截。"""
    install(monkeypatch, MockLLM([
        tool_resp(("risk_check", {
            "event_type": "order_pay", "user_id": "U1001", "order_id": "O2001"})),
        text_resp("无权限"),
    ]))
    r = run(db, "查 U1001 订单 O2001 的风险", role="viewer")
    calls = tool_calls(r["messages"])
    assert len(calls) == 1
    assert "无权限" in [m for m in r["messages"] if m["role"] == "tool"][0]["content"]
    assert "risk_check" not in TOOL_ROLES.get("risk_check", set()) - {"admin", "reviewer"}


def test_E2_22_profile_uses_context_subject(monkeypatch, db):
    """画像工具无 user_id 入参，主体用户由会话上下文注入。"""
    llm = MockLLM([
        tool_resp(("risk_check", {
            "event_type": "order_pay", "user_id": "U1002", "order_id": "O2002"})),
        text_resp("检查完成"),
    ])
    install(monkeypatch, llm)
    r1 = run(db, "查 U1002 订单 O2002 的风险")

    install(monkeypatch, MockLLM([tool_resp(("get_user_profile", {})), text_resp("画像如下")]))
    r2 = run(db, "看下这个用户的画像", conversation_id=r1["conversation_id"])
    profile_msg = [m for m in r2["messages"] if m["role"] == "tool"][0]
    assert profile_msg["ok"] is True
    assert "U1002" in profile_msg["content"]
