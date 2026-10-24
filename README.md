# 电商风险控制系统 2.3 —— 风控 Agent

按《项目一_风控Agent》开发文档（R1–R7）实现的可运行工程：Python 3.12 + FastAPI +
SQLAlchemy 2.0 + Alembic，手写 Function Calling 循环（**未使用 LangChain**），
前端 Vue3 + Vite + TypeScript + Element Plus + Pinia。

LLM 走 OpenAI 兼容接口：`https://api.deepseek.com/v1`，模型 `deepseek-flash`
（即文档中的 DeepSeek-V4.1-Flash，该网关注册名为 `deepseek-flash`）。

> 项目位置：`E:\Desktop\项目一`（`.venv` 与 `frontend/node_modules` 已随项目迁入，可直接运行）

---

## 1. 快速开始

```bash
cd "E:/Desktop/项目一"

# 1) 依赖（.venv 已就绪，可跳过；全新环境再执行）
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt          # Linux/macOS: .venv/bin/pip

# 2) 配置（.env 已随项目提供，密钥不硬编码）
cp .env.example .env

# 3) 建表 + 导入演示数据（24 条规则 / 3 个用户 / 9 笔订单 / 5 条黑名单 / 3 组历史案件）
.venv/Scripts/python seed/init_seed.py --reset

# 4) 启动（前端已构建，单端口 8000）
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

打开 <http://127.0.0.1:8000> → 登录页默认填充管理员账号：

| 账号 | 密码 | 角色 | 权限 |
|---|---|---|---|
| admin | Admin@12345 | 风控管理员 | 全部（规则/黑名单维护仅此角色） |
| reviewer | Reviewer@12345 | 风控审核员 | 查风险、审案件、结案 |
| viewer | Viewer@12345 | 数据查看人 | 只读：画像、历史记录、命中统计 |

> 账号来自 `.env` 的 `AUTH_OPERATORS=user:pass:role,...`，轮换口令只需改这一行；
> 前端登录页提供三个账号的一键填充。写接口做了角色校验，越权返回 `code=403`。

前端开发模式：`cd frontend && npm install && npm run dev`（5173 端口，`/api` 代理到 8000）。

接口文档：<http://127.0.0.1:8000/docs>

---

## 2. 目录结构

```
E:\Desktop\项目一\
├── app/
│   ├── main.py                 # FastAPI 入口 + 统一响应/异常处理 + 静态托管
│   ├── config.py               # pydantic-settings，全部配置来自 .env
│   ├── database.py             # 引擎/会话（PG 生产，SQLite 本地降级）
│   ├── security.py             # PBKDF2 口令 + JWT(HS256, 24h)；操作员来自环境变量
│   ├── deps.py                 # JWT 依赖、统一响应封装、BizError
│   ├── models/                 # 8 张业务表 + agent_tool_logs
│   ├── schemas/                # Pydantic 入参模型
│   ├── api/                    # auth / risk / agent 三组路由
│   ├── services/
│   │   ├── rule_engine.py      # R2 条件递归求值
│   │   ├── feature_service.py  # R3 25 个特征 + 批量快照
│   │   ├── risk_service.py     # R4 检查→决策→自动建案
│   │   ├── rule_service.py     # R5 规则 CRUD
│   │   ├── case_service.py     # R5 案件查询/审核留痕
│   │   ├── blacklist_service.py
│   │   ├── profile_service.py
│   │   ├── dashboard_service.py
│   │   └── source_adapter.py   # 上游订单/用户服务适配（本地读 seed JSON）
│   └── agent/
│       ├── prompt.py           # 7.1 System Prompt 原文
│       ├── llm.py              # OpenAI 兼容客户端（含流式）
│       ├── tools.py            # 9 个工具：Pydantic 入参 + JSON Schema + dispatch
│       ├── orchestrator.py     # 手写 FC 循环（MAX_STEPS=8）+ 工具日志
│       └── store.py            # 会话存储（Redis 优先，进程内降级）
├── migrations/                 # Alembic，0001_init 建 9 张表（PG 用 JSONB）
├── seed/                       # rules.json / demo_users.json / demo_orders.json /
│                               # demo_blacklist.json / init_seed.py
├── tests/                      # 单测 + 端到端验收脚本
└── frontend/                   # Vue3 工作台与管理页
```

---

## 3. 关键实现说明

### 3.1 数据表（严格 8 张 + 1 张日志表，未扩展任何字段）

`risk_events` / `risk_assessments` / `feature_snapshots` / `risk_rules` / `rule_hits` /
`risk_cases` / `blacklists` / `review_logs` + `agent_tool_logs`。

- 主键统一 `String(32)` 业务可读 ID：`RE-`/`RA-`/`FS-`/`RH-`/`CASE-`/`RL-`/`TL-`。
- JSON 列在 PostgreSQL 上是 **JSONB**，SQLite 上自动降级为 JSON（`JSON().with_variant`），
  模型层与迁移层共用同一表达式。
- 金额/评分：`Numeric→Decimal`、`Integer`，无 float 参与计算。

因为不允许新增「用户表/订单表」，订单与用户属性由 `source_adapter` 提供（生产替换为订单/用户
服务 RPC，签名不变）；30 天订单数、退款率等行为类特征来自上游快照，风控事件数、案件数来自
本库真实表。这样既不违反 schema 约束，又保证特征真实可算。

### 3.2 规则引擎（R2）

`evaluate(condition, features)` 支持无限嵌套 `and`/`or` 与 `>` `<` `>=` `<=` `=` `!=` `contains`；
字段缺失或 `None` → 不命中；数值比较先 `float()`，转换失败返回 False；空条件/未知 op 一律 False
（风控场景宁可不报，也不让空规则恒真）。7 个必测用例 + 边界用例见 `tests/test_rule_engine.py`。

### 3.3 特征（R3）

25 个特征名固定，逐个实现为 `calc_xxx(db, user_id, order_id)`；`build_feature_snapshot()` 先构造
`FeatureContext` 批量预取（上游快照 1 次 IO + risk_events / risk_cases / blacklists 共 3 条 SQL），
之后 25 个函数全部读内存——**一次快照恒为 3 条 SQL，无 N+1**。

### 3.4 决策映射（R4，固定不自行发挥）

```
risk_level = high(>=70) / medium(>=40) / low
decision   = reject(>=90) / manual_review(>=70) / pass
total_score = min(100, Σ hit_score)
建案条件：level==high 或 decision ∈ {manual_review, reject}
```
特征计算会排除本次刚写入的事件，保证「历史特征」语义稳定，重复检查不会自我放大。

### 3.5 Agent（R6）

- 9 个工具：`risk_check` `get_assessment` `list_rules` `toggle_rule` `list_cases`
  `review_case` `get_user_profile` `get_dashboard` `manage_blacklist`。
- 工具参数 JSON Schema 由 Pydantic 模型生成，schema 与运行时校验永不漂移。
- **`operator_id` 不出现在任何工具 schema**，只由 API 层从 JWT 注入 dispatch；
  **`user_id` 只出现在 `risk_check`**，`get_user_profile` 的主体用户由会话上下文注入，
  从机制上杜绝 LLM 自造/越权指定用户。
- 每次工具调用写 `agent_tool_logs`（入参 + 结果），前端「工具调用折叠块」与
  `GET /api/agent/tool-logs` 均可查。
- 多轮指代：最近 20 条消息 + 会话上下文（主体用户/最近订单/评估/案件），
  以运行时上下文 system 消息注入，不改动 7.1 原文 Prompt。
- 流式版本 `POST /api/agent/chat/stream` 输出 `conversation / tool_start / tool_finish /
  message_delta / done` 事件。

### 3.6 会话存储

`REDIS_URL` 可配；未配置或连不上时自动降级为进程内缓存（带 TTL 与 LRU 清理），
不影响演示与单测。左侧会话列表、历史消息读取走同一接口。

---

## 4. REST 接口

统一响应 `{"code":0,"message":"ok","data":{...}}`，业务错误 HTTP 200 + `code!=0`，
鉴权失败 HTTP 401。所有写接口的 `operator_id` 取自 JWT。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/login` | 换取 JWT（24h） |
| GET | `/api/auth/me` | 当前操作员 |
| POST | `/api/risk/check` | 风险检查（评分/等级/建议/命中/快照/案件） |
| GET | `/api/risk/assessments/{id}` | 评估详情（含 25 特征快照、命中明细） |
| GET | `/api/risk/rules` | 规则分页（含 hit_count 命中次数） |
| POST | `/api/risk/rules` | 新增规则 |
| POST | `/api/risk/rules/update` | 更新规则 |
| POST | `/api/risk/rules/status` | 启停规则 |
| POST | `/api/risk/rules/delete` | 删除规则 |
| GET | `/api/risk/cases` | 案件分页（case_status/user_id） |
| GET | `/api/risk/cases/{id}` | 案件详情（风险结果 + 命中 + 25 项特征快照 + review_logs） |
| POST | `/api/risk/cases/review` | 审核案件（写 review_logs） |
| POST | `/api/risk/cases/resolve` | 标记处理完成（approved/rejected → resolved） |
| GET | `/api/risk/blacklists` | 黑名单分页 |
| POST | `/api/risk/blacklists` | 新增黑名单 |
| POST | `/api/risk/blacklists/import` | 批量导入（items 数组或「类型,值,备注」文本） |
| POST | `/api/risk/blacklists/delete` | 删除黑名单 |
| GET | `/api/risk/users/{user_id}/profile` | 用户画像 |
| GET | `/api/risk/dashboard` | 看板统计 |
| POST | `/api/agent/chat` | Agent 对话（非流式） |
| POST | `/api/agent/chat/stream` | Agent 对话（SSE） |
| GET | `/api/agent/conversations` | 会话列表 |
| GET | `/api/agent/conversations/{id}/messages` | 会话消息 |
| GET | `/api/agent/tool-logs` | 工具调用日志 |

---

## 5. 演示链路（验收必跑）

演示数据用相对时间（`T-1d@15`）生成，任何日期执行 seed 都能复现同样结果，
且下单时段固定为工作日 15:00，避免周末/凌晨规则污染评分。

**链路 0：表单式风险检查（风险检查页）**

「风险检查」页选事件类型（下单/支付/售后/物流投诉）→ 填 U1001 / O2001 → 发起检查，
右侧立即返回评分环、命中规则、特征快照折叠表，方便不写自然语言时快速核单。

**链路 1：高风险自动建案**

工作台输入：`支付环节做一次风控检查：用户 U1001，订单 O2001`

→ 93 分 / high / reject，命中 4 条：R01 高频退款(25) + R02 高退款率(18) +
R05 地址黑名单(30) + R11 高风险设备(20)，自动建案 `CASE-xxxxxxxx`。

**链路 2：停用规则 → 重查 → 看差异**

输入：`R05 这条规则先停掉，然后把刚才那个订单重新查一遍，告诉我分数变化`
（模型会先 `list_rules` 复述 R05 并等确认）→ 回复 `确认停用 R05，并重查刚才那个订单`

→ R05 停用后同一订单 63 分 / medium / pass，不建案；模型给出前后对比表。

**链路 3：案件审核留痕**

案件审核页（或让 Agent 调 `review_case`）提交结论 + 备注 → `risk_cases` 状态更新，
`review_logs` 写入 `operator_id / action_type / action_remark / created_at`。

> 重跑演示前执行 `.venv/Scripts/python seed/init_seed.py --reset` 可回到干净状态
> （R05 恢复启用、清空测试评估）。

---

## 6. 自检与测试

```bash
# 规则引擎 7 用例 + 流程集成（19 项）
.venv/Scripts/python -m pytest

# 端到端接口验收（需服务已启动，29 项断言）
.venv/Scripts/python tests/verify_api.py

# 2.3 需求补齐项验收（角色权限/命中次数/案件快照/结案/批量导入，19 项断言）
.venv/Scripts/python tests/verify_requirement_23.py

# 前端 UI 冒烟 + 截图（本机 Edge 无头，覆盖全部页面）
cd frontend && node scripts/ui_smoke.mjs

# 评测体系（E1/E2/E3/E4/E5，一键跑完并出报告）
python scripts/run_eval.py
```

seed 时会打印三个演示订单的特征数与预期评分：

| 订单 | 用户 | 特征数 | 评分 | 等级 | 建议 | 命中 |
|---|---|---|---|---|---|---|
| O2001 | U1001 | 25 | 93 | high | reject | R01 R02 R05 R11 |
| O2002 | U1002 | 25 | 68 | medium | pass | R11 R16 R18 R19 |
| O2003 | U1003 | 25 | 0 | low | pass | — |

---

## 7. 验收清单（对照 2.3.11）

| 2.3.11 验收项 | 实现位置 | 状态 |
|---|---|---|
| 四类业务事件均可发起检查 | `/api/risk/check` 的 `event_type` 枚举 + 风险检查页四个事件按钮 | ✅ |
| 返回评分、等级、处理建议、命中规则、特征快照 | `risk_service.check_risk` → `RiskScoreCard` | ✅ |
| 高风险自动创建案件 | `check_risk` 第 7 步（level==high 或 decision∈{manual_review,reject}） | ✅ |
| 案件页完成审核并查看审核日志 | `POST /cases/review` + `review_logs` 抽屉展示 | ✅ |
| 新增/编辑/启停用规则并看到命中统计变化 | 规则页（含命中次数列）+ 停用后重查验证 | ✅ |
| 维护黑名单并在检查中生效 | R04/R05 规则 + 批量导入 | ✅ |
| 查看用户画像与运营看板 | 画像页 / 看板页 | ✅ |
| 完整演示链路 | 见第 5 章三条链路 | ✅ |
| 事件进入后可回查命中、建案、审核、结果 | `GET /assessments/{id}`、`GET /cases/{id}`、`tool-logs` | ✅ |

补充落实项：

- [x] 三类角色（admin / reviewer / viewer）与写接口 RBAC，越权返回 403；Agent 工具按角色收敛
- [x] 案件状态五态：pending / reviewing / approved / rejected / resolved（含结案留痕）
- [x] 规则列表展示命中次数 `hit_count`（一次聚合 SQL，无 N+1）
- [x] 案件详情含 25 项特征快照与处理结论
- [x] 黑名单批量导入（JSON 数组或「类型,值,备注」文本/CSV，返回新增/跳过/失败明细）
- [x] 8 张表 + `agent_tool_logs` 建表成功（`alembic upgrade head` 与 `create_all` 均可用）
- [x] 规则引擎单测 7 用例全过（另含 Decimal/字符串/contains/异常条件等边界）
- [x] 25 个特征全部实现，`build_feature_snapshot` 1 次返回 25 键，无 N+1
- [x] `risk_check` 返回评分/等级/建议/命中/快照，high 自动建案
- [x] 19 个 REST 接口按契约返回，写操作留痕（operator_id 来自 JWT）
- [x] Agent 对话可完成「查风险 → 停规则 → 重查 → 看差异」（真实 LLM 已实测）
- [x] 工具调用日志在前端折叠块与 DB 中可查
- [x] 三条演示链路（表单检查 / 对话查风险停规则重查 / 案件审核留痕）可跑通
- [x] 禁止事项 0 违反：无 LangChain/LlamaIndex/Drools；LLM 不决定权限、不自造 user_id（
      `user_id` 仅出现于 `risk_check`）；无空实现/TODO 占位；表字段未扩展；密钥全部走 .env

---

## 8. 评测体系（E1–E5）

按《项目一_风控Agent_评测》实现三层评测：**不使用 LLM-judge，全部为确定性断言**。

| 模块 | 文件 | 内容 | 结果 |
|---|---|---|---|
| E1 Schema 合法性 | `tests/test_tool_schema.py` | 8 个用例：type/name/desc/parameters 结构、user_id 仅 risk_check、operator_id 不出现、三个枚举 | 9/9 ✅ |
| E2 工具调用准确率 | `tests/test_agent_tools.py` | 22 个用例：mock LLM 驱动 orchestrator，覆盖缺参追问、多轮指代、写操作先确认、异常回填、MAX_STEPS 熔断、日志落库、角色裁剪 | 100%（22/22）✅ |
| E3 不可绕过 | `tests/test_no_bypass.py` | 5 条诱导输入 + 确定性检测器（断言式结论正则 + 否定语境豁免） | 绕过率 0%（真实模型实测）✅ |
| E4 轨迹健康度 | `scripts/export_traces.py` + `scripts/tracecheck_local.py` + `evals.yaml` | 25 条带 `expected_tools` 标注的 trace，评估 tool_accuracy / step_efficiency / failure_modes | 100% / 100% / 0 次，加权 1.0 ✅ |
| E5 报告 | `scripts/gen_report.py` → `reports/eval_risk_agent.md` | 读 junit xml + tracecheck + 绕过结果，生成六段式报告 | 已生成 ✅ |

一键跑完整评测：

```bash
python scripts/run_eval.py             # 离线模式（mock LLM，确定性）
python scripts/run_eval.py --real-llm  # 追加真实模型的绕过率实测
EVAL_REAL_LLM=1 python -m pytest -q    # 真实模型跑 E3
```

产物：`traces/traces.jsonl`（25 条）、`reports/tracecheck_result.json`、
`reports/bypass_result.json`、`reports/junit.xml`、`reports/eval_risk_agent.md`。

> tracecheck 说明：环境无官方 `tracecheck` / `agentrubric` 包，按文档 `evals.yaml`
> 的指标定义与权重（0.4 / 0.3 / 0.3）实现了等价评估器 `scripts/tracecheck_local.py`。

---

## 9. 配置项（.env）

| 键 | 说明 |
|---|---|
| `DATABASE_URL` | 默认 `sqlite:///./risk_agent.db`；生产示例见 `.env.example` 中 PostgreSQL 行 |
| `REDIS_URL` | 留空则使用进程内会话缓存 |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | OpenAI 兼容网关、密钥、模型名 |
| `JWT_SECRET` / `ACCESS_TOKEN_EXPIRE_HOURS` | JWT 签名与有效期 |
| `AUTH_OPERATORS` | `user:pass:role` 逗号分隔，登录账号来源 |
| `UPSTREAM_DATA_DIR` | 上游订单/用户快照目录（默认 `./seed`） |

生产部署提醒：更新 `JWT_SECRET`、改用 PostgreSQL、启动 Redis、把 `source_adapter`
替换为真实订单/用户服务调用。
