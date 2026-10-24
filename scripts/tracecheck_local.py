"""本地 tracecheck：按 evals.yaml 的权重评估 traces.jsonl 的轨迹健康度。

用法：
    python scripts/tracecheck_local.py --traces traces/traces.jsonl --evals evals.yaml
输出：
    reports/tracecheck_result.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_EVALS = {
    "evaluators": [
        {"name": "tool_accuracy", "weight": 0.4},
        {"name": "step_efficiency", "weight": 0.3},
        {"name": "failure_modes", "weight": 0.3},
    ],
    "thresholds": {
        "tool_accuracy_pass_rate": 0.90,
        "step_efficiency_pass_rate": 0.90,
        "failure_modes_allowed": 0,
    },
}

ERROR_ACK_WORDS = ("不存在", "失败", "错误", "异常", "无法", "请确认", "请检查", "重试", "未找到")


def load_evals(path: Path) -> dict:
    try:
        import yaml  # type: ignore

        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return {**DEFAULT_EVALS, **(data or {})}
    except Exception:  # noqa: BLE001 —— 无 pyyaml 时用默认配置，行为一致
        return DEFAULT_EVALS


def tool_calls(steps: list[dict]) -> list[dict]:
    return [s for s in steps if s.get("type") == "tool_call"]


def eval_tool_accuracy(trace: dict) -> tuple[bool, str]:
    expected = trace.get("expected_tools") or []
    actual = [s.get("name") for s in tool_calls(trace.get("steps", []))]
    if actual == expected:
        return True, "工具序列与标注一致"
    return False, f"期望 {expected}，实际 {actual}"


def eval_step_efficiency(trace: dict) -> tuple[bool, str]:
    calls = tool_calls(trace.get("steps", []))
    names = [c.get("name") for c in calls]
    # 连续重复调用（同工具同参数）
    for i in range(1, len(calls)):
        prev, cur = calls[i - 1], calls[i]
        if prev.get("name") == cur.get("name") and prev.get("input") == cur.get("input"):
            return False, f"连续重复调用 {cur.get('name')}（参数相同）"
    # 单工具调用次数过多（>2 次视为绕圈）
    for name, count in Counter(names).items():
        if count > 2:
            return False, f"{name} 调用了 {count} 次，存在冗余"
    # 步骤数明显超出预期规模
    expected_len = len(trace.get("expected_tools") or [])
    if len(trace.get("steps", [])) > 2 * expected_len + 6:
        return False, f"步骤数 {len(trace['steps'])} 远超预期（期望工具 {expected_len} 个）"
    return True, "无重复/无冗余步骤"


def eval_failure_modes(trace: dict) -> tuple[list[str], str]:
    steps = trace.get("steps", [])
    calls = tool_calls(steps)
    issues: list[str] = []
    text = " ".join(s.get("output", "") for s in steps if s.get("type") == "llm_call")

    # infinite_loop
    consecutive = 1
    for i in range(1, len(calls)):
        if calls[i].get("name") == calls[i - 1].get("name") and calls[i].get("input") == calls[i - 1].get("input"):
            consecutive += 1
            if consecutive >= 3:
                issues.append("infinite_loop")
                break
        else:
            consecutive = 1
    if len(calls) >= 8 or "达到最大工具调用步数" in text:
        if "infinite_loop" not in issues:
            issues.append("infinite_loop")

    # context_overflow：步骤数超出单轮上下文预算
    if len(steps) > 20:
        issues.append("context_overflow")

    # tool_error_unhandled：工具报错后模型未向用户说明
    failed = [c for c in calls if c.get("ok") is False]
    if failed and not any(word in text for word in ERROR_ACK_WORDS):
        issues.append("tool_error_unhandled")

    return issues, ",".join(issues) if issues else "无失败模式"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--traces", default="traces/traces.jsonl")
    parser.add_argument("--evals", default="evals.yaml")
    parser.add_argument("--out", default="reports/tracecheck_result.json")
    args = parser.parse_args()

    traces_path = ROOT / args.traces
    evals = load_evals(ROOT / args.evals)
    thresholds = evals.get("thresholds", DEFAULT_EVALS["thresholds"])

    traces = [json.loads(line) for line in traces_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    total = len(traces)

    results = []
    ta_pass = se_pass = 0
    fm_counter: Counter = Counter()
    fm_traces: dict[str, list[str]] = {k: [] for k in ("infinite_loop", "context_overflow", "tool_error_unhandled")}

    for trace in traces:
        ok_ta, reason_ta = eval_tool_accuracy(trace)
        ok_se, reason_se = eval_step_efficiency(trace)
        issues, reason_fm = eval_failure_modes(trace)
        ta_pass += ok_ta
        se_pass += ok_se
        for issue in issues:
            fm_counter[issue] += 1
            fm_traces[issue].append(trace["trace_id"])
        results.append({
            "trace_id": trace["trace_id"],
            "user_input": trace.get("user_input"),
            "expected_tools": trace.get("expected_tools"),
            "actual_tools": [c.get("name") for c in tool_calls(trace.get("steps", []))],
            "tool_accuracy": "PASS" if ok_ta else "FAIL",
            "tool_accuracy_reason": reason_ta,
            "step_efficiency": "PASS" if ok_se else "FAIL",
            "step_efficiency_reason": reason_se,
            "failure_modes": issues,
            "failure_reason": reason_fm,
        })

    ta_rate = ta_pass / total if total else 0.0
    se_rate = se_pass / total if total else 0.0
    fm_total = sum(fm_counter.values())
    fm_rate = (total - fm_total) / total if total else 0.0

    weights = {e["name"]: e.get("weight", 0) for e in evals["evaluators"]}
    weighted = (
        weights.get("tool_accuracy", 0.4) * ta_rate
        + weights.get("step_efficiency", 0.3) * se_rate
        + weights.get("failure_modes", 0.3) * fm_rate
    )

    summary = {
        "traces": total,
        "tool_accuracy": {
            "pass": ta_pass,
            "total": total,
            "rate": round(ta_rate, 4),
            "threshold": thresholds.get("tool_accuracy_pass_rate", 0.9),
            "verdict": "PASS" if ta_rate >= thresholds.get("tool_accuracy_pass_rate", 0.9) else "FAIL",
        },
        "step_efficiency": {
            "pass": se_pass,
            "total": total,
            "rate": round(se_rate, 4),
            "threshold": thresholds.get("step_efficiency_pass_rate", 0.9),
            "verdict": "PASS" if se_rate >= thresholds.get("step_efficiency_pass_rate", 0.9) else "FAIL",
        },
        "failure_modes": {
            "counts": dict(fm_counter),
            "total": fm_total,
            "allowed": thresholds.get("failure_modes_allowed", 0),
            "traces": fm_traces,
            "verdict": "PASS" if fm_total <= thresholds.get("failure_modes_allowed", 0) else "FAIL",
        },
        "weighted_score": round(weighted, 4),
        "weights": weights,
    }

    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"traces={total}")
    print(f"tool_accuracy   {ta_pass}/{total} = {ta_rate:.1%}  -> {summary['tool_accuracy']['verdict']}")
    print(f"step_efficiency {se_pass}/{total} = {se_rate:.1%}  -> {summary['step_efficiency']['verdict']}")
    print(f"failure_modes   {dict(fm_counter) or '{}'} (允许 {thresholds.get('failure_modes_allowed', 0)}) -> {summary['failure_modes']['verdict']}")
    print(f"weighted_score={weighted:.3f} -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
