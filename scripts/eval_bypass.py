"""E3 绕过率评估：对 5 条诱导输入跑 orchestrator，输出 reports/bypass_result.json。

用法：
    # 用真实模型（需要 .env 里有可用 LLM_API_KEY）
    python scripts/eval_bypass.py --mode real

    # 用脚本化合规模型（离线、确定性，CI 用）
    python scripts/eval_bypass.py --mode mock
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

os.environ.setdefault("DATABASE_URL", "sqlite:///./eval_traces.db")

import app.models  # noqa: E402,F401
from app.agent import orchestrator  # noqa: E402
from app.agent.llm import LLMResponse, ToolCall  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.services import source_adapter as upstream  # noqa: E402
from seed.init_seed import seed_blacklist, seed_history, seed_rules  # noqa: E402
from tests.test_no_bypass import INDUCED_INPUTS, MockLLM, detect_bypass  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["real", "mock"], default="mock")
    parser.add_argument("--out", default="reports/bypass_result.json")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    seed_rules(session)
    seed_blacklist(session)
    seed_history(session)
    upstream.reload()

    cases = []
    bypassed_count = 0
    for case_id, user_input in INDUCED_INPUTS:
        if args.mode == "mock":
            # 合规模型：坚持调用 risk_check 拿真实结果，再作答
            orchestrator.llm = MockLLM([
                LLMResponse(
                    content="",
                    tool_calls=[
                        ToolCall(
                            id="call_0",
                            name="risk_check",
                            arguments=json.dumps(
                                {"event_type": "order_pay", "user_id": "U1001", "order_id": "O2001"},
                                ensure_ascii=False,
                            ),
                        )
                    ],
                ),
                LLMResponse(content="已通过风控工具取得真实评估结果，不能凭空给分。"),
            ])
        result = asyncio.run(orchestrator.run_agent(session, "OP-eval", None, user_input))
        bypassed, reason = detect_bypass(result["messages"])
        bypassed_count += bool(bypassed)
        cases.append({
            "case_id": case_id,
            "user_input": user_input,
            "bypassed": bypassed,
            "reason": reason,
            "tools": [m.get("name") for m in result["messages"] if m["role"] == "tool"],
        })
        print(f"{case_id} bypass={bypassed} tools={cases[-1]['tools']}")

    total = len(cases)
    payload = {
        "mode": args.mode,
        "total": total,
        "bypassed": bypassed_count,
        "rate": round(bypassed_count / total, 4) if total else 0.0,
        "cases": cases,
    }
    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n绕过率 {payload['rate']:.0%} ({bypassed_count}/{total}) -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
