"""端到端验收脚本：逐条核对 REST 契约、演示链路与留痕。

用法（服务已启动）：
    python tests/verify_api.py [--base http://127.0.0.1:8000]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.request

# 本机验收需绕过系统代理（否则 127.0.0.1 会被 HTTP_PROXY 劫持）
import os as _os
_os.environ["no_proxy"] = "127.0.0.1,localhost"
_os.environ["NO_PROXY"] = "127.0.0.1,localhost"
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

BASE = "http://127.0.0.1:8000"
TOKEN = ""

def _accounts_from_env() -> dict:
    """从 .env 的 AUTH_OPERATORS 读取演示账号，避免在脚本里写死口令。"""
    text = pathlib.Path(__file__).resolve().parents[1].joinpath(".env").read_text(encoding="utf-8")
    line = next((l for l in text.splitlines() if l.startswith("AUTH_OPERATORS=")), "")
    accounts = {}
    for item in line.split("=", 1)[-1].split(","):
        parts = item.strip().split(":")
        if len(parts) == 3:
            accounts[parts[2]] = (parts[0], parts[1])
    return accounts



CHECKS: list[tuple[str, bool, str]] = []


def call(method: str, path: str, body: dict | None = None, auth: bool = True) -> dict:
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if auth and TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    try:
        with _OPENER.open(req, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:  # 4xx 也返回 JSON 包体
        return json.loads(exc.read().decode())


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -> ' + detail) if detail else ''}")


def main() -> int:
    global BASE, TOKEN
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=BASE)
    args = parser.parse_args()
    BASE = args.base.rstrip("/")

    # ---------- 认证 ----------
    admin_user, admin_pwd = _accounts_from_env()["admin"]
    login = call("POST", "/api/auth/login", {"username": admin_user, "password": admin_pwd}, auth=False)
    TOKEN = (login.get("data") or {}).get("access_token", "")
    check("POST /api/auth/login", login.get("code") == 0 and bool(TOKEN))

    unauth = call("GET", "/api/risk/dashboard", auth=False)
    check("未带令牌被拒（401 + code!=0）", unauth.get("code") == 401, f"code={unauth.get('code')}")

    # ---------- 链路 1：高风险自动建案 ----------
    r1 = call(
        "POST",
        "/api/risk/check",
        {"event_type": "order_pay", "source_id": "VERIFY-1", "user_id": "U1001", "order_id": "O2001"},
    )
    d1 = r1.get("data") or {}
    check(
        "POST /api/risk/check 高风险建案",
        d1.get("risk_level") == "high" and bool(d1.get("case_id")) and len(d1.get("rule_hits", [])) >= 2,
        f"score={d1.get('risk_score')} level={d1.get('risk_level')} case={d1.get('case_id')} hits={len(d1.get('rule_hits', []))}",
    )
    check("特征快照 25 键", len(d1.get("feature_snapshot", {})) == 25, f"{len(d1.get('feature_snapshot', {}))} keys")

    aid = d1.get("assessment_id")
    det = call("GET", f"/api/risk/assessments/{aid}")
    dd = det.get("data") or {}
    check(
        "GET /api/risk/assessments/{id}",
        det.get("code") == 0 and dd.get("risk_score") == d1.get("risk_score") and len(dd.get("feature_snapshot", {})) == 25,
        f"score={dd.get('risk_score')} hits={len(dd.get('rule_hits', []))}",
    )

    # ---------- 链路 2：停用规则后降级 ----------
    rules = call("GET", "/api/risk/rules?page=1&page_size=50")
    items = (rules.get("data") or {}).get("items", [])
    check("GET /api/risk/rules 分页", rules.get("code") == 0 and len(items) == 24, f"total={(rules.get('data') or {}).get('total')}")
    r05 = next((r for r in items if r["rule_code"] == "R05"), None)
    check("规则含 R01~R24", len([r for r in items if r["rule_code"].startswith("R")]) == 24)

    off = call("POST", "/api/risk/rules/status", {"rule_id": r05["rule_id"], "target_status": "disabled"})
    check("POST /api/risk/rules/status 停用", (off.get("data") or {}).get("rule_status") == "disabled")

    r2 = call(
        "POST",
        "/api/risk/check",
        {"event_type": "order_pay", "source_id": "VERIFY-2", "user_id": "U1001", "order_id": "O2001"},
    )
    d2 = r2.get("data") or {}
    check(
        "停用 R05 后重查降级为 medium 且不建案",
        d2.get("risk_level") == "medium" and d2.get("case_id") is None and d2.get("risk_score", 0) < d1.get("risk_score", 0),
        f"{d1.get('risk_score')} -> {d2.get('risk_score')} level={d2.get('risk_level')} case={d2.get('case_id')}",
    )

    on = call("POST", "/api/risk/rules/status", {"rule_id": r05["rule_id"], "target_status": "enabled"})
    check("恢复 R05 启用", (on.get("data") or {}).get("rule_status") == "enabled")

    # ---------- 规则 CRUD ----------
    new_rule = {
        "rule_code": "R99",
        "rule_name": "验收临时规则",
        "priority": 999,
        "score": 12,
        "condition_json": {"op": "and", "conditions": [{"field": "order_item_count", "op": ">=", "value": 99}]},
        "description": "验收脚本创建，随后删除",
    }
    created = call("POST", "/api/risk/rules", new_rule)
    check("POST /api/risk/rules 新增", created.get("code") == 0, str(created.get("message")))
    nid = (created.get("data") or {}).get("rule_id")
    bad = call("POST", "/api/risk/rules", {**new_rule, "rule_code": "R98", "condition_json": {"op": "bad"}})
    check("非法 condition_json 被拒", bad.get("code") != 0, str(bad.get("message"))[:60])

    upd = call("POST", "/api/risk/rules/update", {"rule_id": nid, "score": 20, "description": "已更新"})
    check("POST /api/risk/rules/update", (upd.get("data") or {}).get("score") == 20)
    dele = call("POST", "/api/risk/rules/delete", {"rule_id": nid})
    check("POST /api/risk/rules/delete", (dele.get("data") or {}).get("deleted") is True)

    # ---------- 链路 3：案件审核留痕 ----------
    cases = call("GET", "/api/risk/cases?page=1&page_size=20&case_status=pending")
    citems = (cases.get("data") or {}).get("items", [])
    check("GET /api/risk/cases 按状态筛选", cases.get("code") == 0 and len(citems) >= 1, f"pending={len(citems)}")
    case_id = citems[0]["case_id"] if citems else None
    detail = call("GET", f"/api/risk/cases/{case_id}")
    check("GET /api/risk/cases/{id}", (detail.get("data") or {}).get("case_id") == case_id)

    rv = call(
        "POST",
        "/api/risk/cases/review",
        {"case_id": case_id, "review_result": "reject", "review_remark": "验收：证据不足，驳回并转人工观察"},
    )
    check(
        "POST /api/risk/cases/review 写 review_logs",
        (rv.get("data") or {}).get("reviewer_id") == "OP-admin",
        f"status={(rv.get('data') or {}).get('case_status')} reviewer={(rv.get('data') or {}).get('reviewer_id')}",
    )
    after = call("GET", f"/api/risk/cases/{case_id}")
    logs = (after.get("data") or {}).get("review_logs", [])
    check("review_logs 可查", len(logs) >= 1, f"logs={len(logs)} last={logs[-1]['action_type'] if logs else ''}")
    dup = call("POST", "/api/risk/cases/review", {"case_id": case_id, "review_result": "reject", "review_remark": "重复提交"})
    check("重复审核被拒", dup.get("code") != 0, str(dup.get("message"))[:40])
    missing_remark = call("POST", "/api/risk/cases/review", {"case_id": case_id, "review_result": "approve", "review_remark": ""})
    check("缺审核备注被拒", missing_remark.get("code") != 0)

    # ---------- 黑名单 ----------
    bl = call("GET", "/api/risk/blacklists?page=1&page_size=20")
    check("GET /api/risk/blacklists", bl.get("code") == 0, f"total={(bl.get('data') or {}).get('total')}")
    added = call(
        "POST",
        "/api/risk/blacklists",
        {"blacklist_type": "ip", "blacklist_value": "10.99.99.99", "remark": "验收临时"},
    )
    check("POST /api/risk/blacklists 新增", added.get("code") == 0, str(added.get("message")))
    blid = (added.get("data") or {}).get("blacklist_id")
    dup_bl = call("POST", "/api/risk/blacklists", {"blacklist_type": "ip", "blacklist_value": "10.99.99.99"})
    check("黑名单重复新增被拒", dup_bl.get("code") != 0)
    dele_bl = call("POST", "/api/risk/blacklists/delete", {"blacklist_id": blid})
    check("POST /api/risk/blacklists/delete", dele_bl.get("code") == 0)

    # ---------- 画像 / 看板 ----------
    prof = call("GET", "/api/risk/users/U1001/profile")
    pd = prof.get("data") or {}
    check(
        "GET /api/risk/users/{id}/profile 契约字段",
        all(k in pd for k in ("order_history", "refund_count", "complaint_count", "address_count", "recent_risk_events", "related_cases")),
        f"orders={len(pd.get('order_history', []))} refund={pd.get('refund_count')} cases={len(pd.get('related_cases', []))}",
    )

    dash = call("GET", "/api/risk/dashboard")
    ds = dash.get("data") or {}
    check(
        "GET /api/risk/dashboard 契约字段",
        all(k in ds for k in ("total_events", "high_risk_ratio", "case_efficiency", "rule_hit_ranking", "blacklist_hit_count")),
        f"events={ds.get('total_events')} high_ratio={ds.get('high_risk_ratio')} ranking={len(ds.get('rule_hit_ranking', []))}",
    )

    # ---------- Agent ----------
    chat = call("POST", "/api/agent/chat", {"message": "看一下风控看板现在的情况"})
    cm = (chat.get("data") or {}).get("messages", [])
    used = [c["function"]["name"] for m in cm if m.get("tool_calls") for c in m["tool_calls"]]
    check("POST /api/agent/chat 触发工具", chat.get("code") == 0 and bool(used), f"tools={used}")

    logs_res = call("GET", "/api/agent/tool-logs?limit=5")
    check("GET /api/agent/tool-logs 留痕", len((logs_res.get("data") or {}).get("items", [])) > 0)

    convs = call("GET", "/api/agent/conversations")
    check("GET /api/agent/conversations", (convs.get("data") or {}).get("backend") in ("redis", "memory"))

    # ---------- 汇总 ----------
    passed = sum(1 for _, ok, _ in CHECKS if ok)
    print(f"\n结果：{passed}/{len(CHECKS)} 通过")
    failed = [c for c in CHECKS if not c[1]]
    if failed:
        print("失败项：", [c[0] for c in failed])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
