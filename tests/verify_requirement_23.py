"""针对 2.3 需求补齐项的验证：角色权限、命中次数、案件快照、resolved、黑名单批量导入。"""

from __future__ import annotations

import json
import pathlib
import urllib.error
import urllib.request

# 本机验收需绕过系统代理（否则 127.0.0.1 会被 HTTP_PROXY 劫持）
import os as _os
_os.environ["no_proxy"] = "127.0.0.1,localhost"
_os.environ["NO_PROXY"] = "127.0.0.1,localhost"
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

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



BASE = "http://127.0.0.1:8000"
PASS = FAIL = 0


def call(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with _OPENER.open(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read().decode())


def check(name, ok, detail=""):
    global PASS, FAIL
    PASS += ok
    FAIL += (not ok)
    print(("PASS  " if ok else "FAIL  ") + name + (f"  -> {detail}" if detail else ""))


def login(user, pwd):
    return call("POST", "/api/auth/login", {"username": user, "password": pwd})["data"]["access_token"]


acc = _accounts_from_env()
admin = login(*acc["admin"])
reviewer = login(*acc["reviewer"])
viewer = login(*acc["viewer"])
check("三类角色均可登录", all([admin, reviewer, viewer]))

# ---------- 角色权限 ----------
r = call("POST", "/api/risk/rules", {"rule_code": "R97", "rule_name": "权限测试", "score": 5,
                                    "condition_json": {"op": "and", "conditions": [{"field": "order_amount", "op": ">", "value": 1}]}},
         token=reviewer)
check("审核员不能新增规则（403）", r.get("code") == 403, str(r.get("message"))[:50])

r = call("POST", "/api/risk/rules/status", {"rule_id": "x", "target_status": "disabled"}, token=viewer)
check("查看人不能启停规则（403）", r.get("code") == 403)

r = call("GET", "/api/risk/dashboard", token=viewer)
check("查看人可读看板", r.get("code") == 0)

r = call("POST", "/api/risk/check", {"event_type": "order_pay", "source_id": "ROLE-T", "user_id": "U1001", "order_id": "O2001"}, token=viewer)
check("查看人不能发起风险检查（403）", r.get("code") == 403)

r = call("POST", "/api/risk/check", {"event_type": "order_pay", "source_id": "ROLE-T2", "user_id": "U1001", "order_id": "O2001"}, token=reviewer)
check("审核员可发起风险检查", r.get("code") == 0 and r["data"]["risk_level"] == "high", f"score={r['data']['risk_score']}")

# ---------- 规则命中次数 ----------
r = call("GET", "/api/risk/rules?page_size=50", token=admin)
items = r["data"]["items"]
check("规则列表含 hit_count 字段", all("hit_count" in i for i in items), f"示例 R01 hit_count={[i['hit_count'] for i in items if i['rule_code']=='R01'][0]}")
check("命中次数已累计（R01>0）", any(i["rule_code"] == "R01" and i["hit_count"] > 0 for i in items))

# ---------- 停用后命中统计变化 ----------
r05 = next(i for i in items if i["rule_code"] == "R05")
before = r05["hit_count"]
call("POST", "/api/risk/rules/status", {"rule_id": r05["rule_id"], "target_status": "disabled"}, token=admin)
call("POST", "/api/risk/check", {"event_type": "order_pay", "source_id": "ROLE-T3", "user_id": "U1001", "order_id": "O2001"}, token=admin)
after_items = call("GET", "/api/risk/rules?page_size=50", token=admin)["data"]["items"]
after = next(i for i in after_items if i["rule_code"] == "R05")["hit_count"]
check("停用规则后不再产生新命中", after == before, f"{before} -> {after}")
call("POST", "/api/risk/rules/status", {"rule_id": r05["rule_id"], "target_status": "enabled"}, token=admin)

# ---------- 案件详情含特征快照 + resolved 流转 ----------
cases = call("GET", "/api/risk/cases?page_size=10", token=admin)["data"]["items"]
pending = [c for c in cases if c["case_status"] == "pending"]
check("存在待审案件", bool(pending), f"{len(pending)} 件")
cid = pending[0]["case_id"]
detail = call("GET", f"/api/risk/cases/{cid}", token=admin)["data"]
check("案件详情含特征快照（25 项）", len(detail.get("feature_snapshot") or {}) == 25,
      f"{len(detail.get('feature_snapshot') or {})} 项")

rv = call("POST", "/api/risk/cases/review", {"case_id": cid, "review_result": "approve", "review_remark": "证据链完整，判定风险成立"}, token=reviewer)
check("审核通过", rv.get("code") == 0 and rv["data"]["case_status"] == "approved")

rs = call("POST", "/api/risk/cases/resolve", {"case_id": cid, "resolve_remark": "已冻结账号并追回款项，结案归档"}, token=reviewer)
check("标记处理完成 → resolved", rs.get("code") == 0 and rs["data"]["case_status"] == "resolved", str(rs.get("message")))

logs = call("GET", f"/api/risk/cases/{cid}", token=admin)["data"]["review_logs"]
actions = [l["action_type"] for l in logs]
check("review_logs 含 review + resolve", "review:approve" in actions and "resolve" in actions, str(actions))
check("详情返回 resolved_at", bool(call("GET", f"/api/risk/cases/{cid}", token=admin)["data"].get("resolved_at")))

rs2 = call("POST", "/api/risk/cases/resolve", {"case_id": cid, "resolve_remark": "重复"}, token=admin)
check("重复结案被拒", rs2.get("code") != 0)

# ---------- 黑名单批量导入 ----------
text = "类型,名单值,备注\nip,45.32.11.88,已存在\naddress,ADDR-BATCH-1,批量导入测试\n用户,U-BATCH-9,中文类型别名\nbadtype,X1,非法类型\n"
r = call("POST", "/api/risk/blacklists/import", {"text": text}, token=admin)["data"]
check("批量导入：成功/跳过/失败统计", r["created"] == 2 and r["skipped"] == 1 and r["failed"] == 1,
      f"created={r['created']} skipped={r['skipped']} failed={r['failed']}")

r = call("POST", "/api/risk/blacklists/import", {"items": [{"blacklist_type": "device", "blacklist_value": "DEV-BATCH-2", "remark": "数组导入"}]}, token=admin)["data"]
check("批量导入支持 items 数组", r["created"] == 1)

r = call("POST", "/api/risk/blacklists/import", {"text": "nothing"}, token=admin)
check("空/非法文本被拒", r.get("code") != 0)

# 清理导入数据
for value in ["ADDR-BATCH-1", "U-BATCH-9", "DEV-BATCH-2"]:
    lst = call("GET", f"/api/risk/blacklists?keyword={value}", token=admin)["data"]["items"]
    for item in lst:
        call("POST", "/api/risk/blacklists/delete", {"blacklist_id": item["blacklist_id"]}, token=admin)

print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
