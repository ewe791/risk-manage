"""E4 轨迹导出：scripts/export_traces.py

用脚本化的 mock LLM 驱动 orchestrator，把真实工具调用轨迹导出为 traces.jsonl。
expected_tools 为人工标注，覆盖单工具 / 多工具 / 缺参追问 / 写操作确认 / 异常回填。

用法：
    python scripts/export_traces.py [--out traces/traces.jsonl]

说明：轨迹导出使用独立的 eval_traces.db（环境变量 DATABASE_URL 必须在导入 app 前设置），
      避免污染演示库。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 数据库必须在导入 app.database 之前指定
os.environ["DATABASE_URL"] = "sqlite:///./eval_traces.db"

import app.models  # noqa: E402,F401
from app.agent import orchestrator  # noqa: E402
from app.agent.llm import LLMResponse, ToolCall  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import Blacklist, RiskAssessment, RiskCase, RiskRule  # noqa: E402
from app.services import source_adapter as upstream  # noqa: E402
from seed.init_seed import seed_blacklist, seed_history, seed_rules  # noqa: E402
from sqlalchemy import select  # noqa: E402


def _tool(name: str, args: dict) -> tuple:
    return ("tool", name, args)


def _text(content: str) -> tuple:
    return ("text", content)


def first_case(db, status: str):
    return db.execute(select(RiskCase).where(RiskCase.case_status == status).limit(1)).scalars().first()


# --------------------------------------------------------------------------
# 场景定义（expected_tools 为人工标注）
# --------------------------------------------------------------------------
def build_scenarios(db) -> list[dict]:
    r05 = db.execute(select(RiskRule).where(RiskRule.rule_code == "R05")).scalars().one()
    r01 = db.execute(select(RiskRule).where(RiskRule.rule_code == "R01")).scalars().one()
    pending = first_case(db, "pending") or db.execute(select(RiskCase).limit(1)).scalars().first()
    approved = first_case(db, "approved") or db.execute(select(RiskCase).limit(1)).scalars().first()
    assessment = db.execute(select(RiskAssessment).limit(1)).scalars().first()
    bl = db.execute(select(Blacklist).limit(1)).scalars().first()

    return [
        # ---- 单工具（四类事件全覆盖）----
        {"id": "risk_001", "user_input": "查 U1001 订单 O2001 的风险",
         "expected_tools": ["risk_check"],
         "turns": [[_tool("risk_check", {"event_type": "order_pay", "user_id": "U1001", "order_id": "O2001"})]]},
        {"id": "risk_002", "user_input": "下单环节查 U1002 的 O2002",
         "expected_tools": ["risk_check"],
         "turns": [[_tool("risk_check", {"event_type": "order_create", "user_id": "U1002", "order_id": "O2002"})]]},
        {"id": "risk_003", "user_input": "售后申请也查一下 U1001 的 O2000",
         "expected_tools": ["risk_check"],
         "turns": [[_tool("risk_check", {"event_type": "after_sale_apply", "user_id": "U1001", "order_id": "O2000"})]]},
        {"id": "risk_004", "user_input": "物流投诉事件查 U1001 的 O1999",
         "expected_tools": ["risk_check"],
         "turns": [[_tool("risk_check", {"event_type": "logistics_complaint", "user_id": "U1001", "order_id": "O1999"})]]},
        {"id": "risk_005", "user_input": f"看下评估 {assessment.id} 的详情",
         "expected_tools": ["get_assessment"],
         "turns": [[_tool("get_assessment", {"assessment_id": assessment.id})]]},
        {"id": "risk_006", "user_input": "有哪些启用的规则",
         "expected_tools": ["list_rules"],
         "turns": [[_tool("list_rules", {"rule_status": "enabled"})]]},
        {"id": "risk_007", "user_input": "查一下和黑名单有关的规则",
         "expected_tools": ["list_rules"],
         "turns": [[_tool("list_rules", {"keyword": "黑名单"})]]},
        {"id": "risk_008", "user_input": "待审案件有哪些",
         "expected_tools": ["list_cases"],
         "turns": [[_tool("list_cases", {"case_status": "pending"})]]},
        {"id": "risk_009", "user_input": "已驳回的案件列一下",
         "expected_tools": ["list_cases"],
         "turns": [[_tool("list_cases", {"case_status": "rejected"})]]},
        {"id": "risk_010", "user_input": "看板高风险占比多少",
         "expected_tools": ["get_dashboard"],
         "turns": [[_tool("get_dashboard", {"days": 7})]]},
        {"id": "risk_011", "user_input": "最近两周的看板",
         "expected_tools": ["get_dashboard"],
         "turns": [[_tool("get_dashboard", {"days": 14})]]},
        {"id": "risk_012", "user_input": "U1001 退款几次",
         "expected_tools": ["risk_check", "get_user_profile"],
         "turns": [[_tool("risk_check", {"event_type": "order_pay", "user_id": "U1001", "order_id": "O2001"}),
                    _tool("get_user_profile", {})]]},
        {"id": "risk_013", "user_input": "看黑名单",
         "expected_tools": ["manage_blacklist"],
         "turns": [[_tool("manage_blacklist", {"action": "list"})]]},
        {"id": "risk_014", "user_input": "加黑名单 user U9999",
         "expected_tools": ["manage_blacklist"],
         "turns": [[_tool("manage_blacklist", {"action": "add", "blacklist_type": "user",
                                               "blacklist_value": "U9999", "remark": "骗赔惯犯"})]]},
        {"id": "risk_015", "user_input": f"把黑名单 {bl.blacklist_value} 删掉",
         "expected_tools": ["manage_blacklist"],
         "turns": [[_tool("manage_blacklist", {"action": "delete", "blacklist_id": bl.id})]]},

        # ---- 缺参追问（期望零工具调用）----
        {"id": "risk_016", "user_input": "查一下 U1001 的风险",
         "expected_tools": [],
         "turns": [[_text("请问是哪个订单？需要提供 order_id 才能发起检查。")]]},
        {"id": "risk_017", "user_input": "查一下订单 O2001 的风险",
         "expected_tools": [],
         "turns": [[_text("请提供用户编号 user_id。")]]},
        {"id": "risk_018", "user_input": "按退款事件查一下 U1001 的 O2001",
         "expected_tools": [],
         "turns": [[_text("仅支持 order_create/order_pay/after_sale_apply/logistics_complaint 四类事件。")]]},
        {"id": "risk_019", "user_input": f"通过 {pending.id}",
         "expected_tools": [],
         "turns": [[_text("请补充审核备注 review_remark。")]]},

        # ---- 多工具 / 写操作确认 ----
        {"id": "risk_020", "user_input": "把 R05 停用",
         "expected_tools": ["list_rules", "toggle_rule"],
         "turns": [[_tool("list_rules", {"keyword": "R05"}),
                    _tool("toggle_rule", {"rule_id": r05.id, "target_status": "disabled"})]]},
        {"id": "risk_021", "user_input": f"通过 {pending.id}，备注：资料齐全",
         "expected_tools": ["review_case"],
         "turns": [[_tool("review_case", {"case_id": pending.id, "review_result": "approved",
                                          "review_remark": "资料齐全"})]]},
        {"id": "risk_022", "user_input": f"驳回 {approved.id}，备注：证据不足",
         "expected_tools": ["review_case"],
         "turns": [[_tool("review_case", {"case_id": approved.id, "review_result": "rejected",
                                          "review_remark": "证据不足"}),
                    # 该案件已审核完成，工具会报错；合规模型必须向用户如实说明
                    _text("该案件已审核完成（approved），无法重复提交，如需变更请先走人工流程。")]]},
        {"id": "risk_023", "user_input": "审核 CASE-NOTEXIST，备注：测试",
         "expected_tools": ["review_case"],
         "turns": [[_tool("review_case", {"case_id": "CASE-NOTEXIST", "review_result": "approved",
                                          "review_remark": "测试"}),
                    _text("该案件不存在，请确认案件编号后重试。")]]},
        {"id": "risk_024", "user_input": "停用 R05 后重查那个订单（多轮）",
         "expected_tools": ["risk_check", "toggle_rule", "risk_check"],
         "turns": [
             [_tool("risk_check", {"event_type": "order_pay", "user_id": "U1001", "order_id": "O2001"})],
             [_tool("toggle_rule", {"rule_id": r05.id, "target_status": "disabled"}),
              _tool("risk_check", {"event_type": "order_pay", "user_id": "U1001", "order_id": "O2001"})],
         ]},
        {"id": "risk_025", "user_input": "把 R01 停用再恢复",
         "expected_tools": ["list_rules", "toggle_rule", "toggle_rule"],
         "turns": [[_tool("list_rules", {"keyword": "R01"}),
                    _tool("toggle_rule", {"rule_id": r01.id, "target_status": "disabled"}),
                    _tool("toggle_rule", {"rule_id": r01.id, "target_status": "enabled"})]]},
    ]


# --------------------------------------------------------------------------
# Mock LLM
# --------------------------------------------------------------------------
class ScriptedLLM:
    def __init__(self, turns: list[list[tuple]], tail: str = "已按工具结果答复。"):
        self.script = [list(t) for t in turns]
        self.index = 0
        self.tail = tail

    async def chat(self, messages, tools=None, tool_choice="auto", temperature=None) -> LLMResponse:
        while self.index < len(self.script) and not self.script[self.index]:
            self.index += 1
        if self.index >= len(self.script):
            return LLMResponse(content=self.tail)
        item = self.script[self.index].pop(0)
        if item[0] == "text":
            return LLMResponse(content=item[1])
        return LLMResponse(
            content="",
            tool_calls=[
                ToolCall(id="call_0", name=item[1], arguments=json.dumps(item[2], ensure_ascii=False))
            ],
        )


def messages_to_steps(messages: list[dict]) -> list[dict]:
    steps: list[dict] = []
    for msg in messages:
        if msg.get("role") == "tool":
            try:
                output = json.loads(msg.get("content") or "{}")
            except json.JSONDecodeError:
                output = {"raw": msg.get("content")}
            steps.append({
                "type": "tool_call",
                "name": msg.get("name"),
                "input": msg.get("args") or {},
                "output": output if isinstance(output, dict) else {"value": output},
                "ok": bool(msg.get("ok")),
            })
        elif msg.get("role") == "assistant" and msg.get("content"):
            steps.append({"type": "llm_call", "output": msg["content"]})
        elif msg.get("role") == "user":
            steps.append({"type": "user_input", "output": msg.get("content", "")})
    return steps


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="traces/traces.jsonl")
    args = parser.parse_args()

    db_file = ROOT / "eval_traces.db"
    if db_file.exists():
        db_file.unlink()

    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    seed_rules(session)
    seed_blacklist(session)
    seed_history(session)
    upstream.reload()

    scenarios = build_scenarios(session)
    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    traces = []
    for scenario in scenarios:
        conversation_id = None
        messages: list[dict] = []
        for turn in scenario["turns"]:
            orchestrator.llm = ScriptedLLM([turn])
            result = asyncio.run(
                orchestrator.run_agent(session, "OP-eval", conversation_id, scenario["user_input"])
            )
            conversation_id = result["conversation_id"]
            messages.extend(result["messages"])
        traces.append({
            "trace_id": scenario["id"],
            "agent_name": "risk_agent",
            "user_input": scenario["user_input"],
            "expected_tools": scenario["expected_tools"],
            "steps": messages_to_steps(messages),
        })
        print(f"导出 {scenario['id']}: {len(messages)} 条消息")

    with out_path.open("w", encoding="utf-8") as fh:
        for trace in traces:
            fh.write(json.dumps(trace, ensure_ascii=False) + "\n")

    print(f"\n共 {len(traces)} 条 trace -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
