"""R6 Orchestrator：手写 Function Calling 循环（不使用 LangChain）。

约束（文档 7.3）：
- operator_id 由 API 层从 JWT 注入并传给 dispatch，不进入 tool schema，LLM 无法指定
- 工具异常作为 role=tool 内容回填，由模型决定重试或告知用户
- 每次工具调用写 agent_tool_logs
- 多轮指代依赖最近 20 条消息 + 会话上下文（主体用户/订单/评估/案件）
- MAX_STEPS 默认 8，超限返回 type=error
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from sqlalchemy.orm import Session

from app.agent.llm import LLMResponse, llm
from app.agent.prompt import SYSTEM_PROMPT
from app.agent.store import store
from app.agent.tools import AgentContext, build_card, dispatch, tools_for_role
from app.config import settings
from app.models import AgentToolLog, gen_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


ROLE_LABEL = {"admin": "风控管理员", "reviewer": "风控审核员", "viewer": "数据查看人（只读）"}


def _llm_messages(data: dict, context: AgentContext, role: str = "admin") -> list[dict]:
    """system + 运行时上下文（含角色）+ 最近 N 条历史。"""
    history = store.llm_history(data, settings.AGENT_HISTORY_LIMIT)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "system",
            "content": (
                f"[运行时上下文] {context.hint()} 当前操作员角色：{role}"
                f"（{ROLE_LABEL.get(role, role)}），仅可调用 schema 中出现的工具。"
            ),
        },
        *[m for m in history if m["role"] != "system"],
    ]


def _save_tool_log(
    db: Session, conversation_id: str, tool_name: str, args: dict, result: dict
) -> None:
    try:
        db.add(
            AgentToolLog(
                id=gen_id("TL"),
                conversation_id=conversation_id,
                tool_name=tool_name,
                args_json=args or {},
                result_json=json.loads(json.dumps(result, ensure_ascii=False, default=str)),
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
    except Exception:  # noqa: BLE001 —— 日志失败不影响主流程
        db.rollback()


def _tool_entry(call_id: str, name: str, args: dict, result: dict) -> dict:
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "name": name,
        "content": json.dumps(result, ensure_ascii=False, default=str),
        "args": args,
        "ok": not (isinstance(result, dict) and result.get("error")),
        "card": build_card(name, result),
        "ts": _now(),
    }


async def run_agent(
    db: Session,
    operator_id: str,
    conversation_id: str | None,
    user_input: str,
    role: str = "admin",
) -> dict:
    """单轮对话入口：返回 {conversation_id, type, content, messages, context}。"""
    cid = conversation_id or store.new_id()
    data = (
        await store.load(cid)
        if conversation_id
        else {
            "conversation_id": cid,
            "messages": [],
            "context": {},
            "updated_at": _now(),
        }
    )
    context = AgentContext.from_dict(data.get("context"))

    ui_messages: list[dict] = []
    user_msg = {"role": "user", "content": user_input, "ts": _now()}
    data.setdefault("messages", [])
    data["messages"].append(user_msg)
    ui_messages.append(user_msg)

    for step in range(settings.AGENT_MAX_STEPS):
        try:
            resp: LLMResponse = await llm.chat(
                _llm_messages(data, context, role), tools=tools_for_role(role)
            )
        except Exception as exc:  # noqa: BLE001
            error_msg = {
                "role": "assistant",
                "content": f"模型调用失败：{exc}。请稍后重试，或检查 LLM 配置。",
                "ts": _now(),
                "type": "error",
            }
            data["messages"].append(error_msg)
            data["context"] = context.to_dict()
            await store.save(cid, data)
            ui_messages.append(error_msg)
            return {
                "conversation_id": cid,
                "type": "error",
                "content": error_msg["content"],
                "messages": ui_messages,
                "context": context.to_dict(),
                "steps": step,
            }

        if not resp.tool_calls:
            assistant = {"role": "assistant", "content": resp.content or "", "ts": _now()}
            data["messages"].append(assistant)
            data["context"] = context.to_dict()
            await store.save(cid, data)
            ui_messages.append(assistant)
            return {
                "conversation_id": cid,
                "type": "text",
                "content": resp.content or "",
                "messages": ui_messages,
                "context": context.to_dict(),
                "steps": step,
            }

        # 先把 assistant(tool_calls) 入历史，再逐个执行并回填 tool 结果
        assistant_tool_msg = {
            "role": "assistant",
            "content": resp.content or "",
            "tool_calls": [c.to_openai() for c in resp.tool_calls],
            "ts": _now(),
        }
        data["messages"].append(assistant_tool_msg)
        ui_messages.append(assistant_tool_msg)

        for call in resp.tool_calls:
            args = call.parsed_arguments()
            result = await dispatch(call.name, db, operator_id, args, context, role=role)
            _save_tool_log(db, cid, call.name, args, result)
            entry = _tool_entry(call.id, call.name, args, result)
            data["messages"].append(entry)
            ui_messages.append(entry)

        data["context"] = context.to_dict()
        await store.save(cid, data)

    error_msg = {
        "role": "assistant",
        "content": f"达到最大工具调用步数（{settings.AGENT_MAX_STEPS}），已中止本轮处理。请把问题拆细一些，或确认工具参数是否正确。",
        "ts": _now(),
        "type": "error",
    }
    data["messages"].append(error_msg)
    data["context"] = context.to_dict()
    await store.save(cid, data)
    ui_messages.append(error_msg)
    return {
        "conversation_id": cid,
        "type": "error",
        "content": error_msg["content"],
        "messages": ui_messages,
        "context": context.to_dict(),
        "steps": settings.AGENT_MAX_STEPS,
    }


async def run_agent_stream(
    db: Session,
    operator_id: str,
    conversation_id: str | None,
    user_input: str,
    role: str = "admin",
) -> AsyncIterator[dict]:
    """SSE 版本：事件 message_delta / tool_start / tool_finish / done / error。"""
    cid = conversation_id or store.new_id()
    data = (
        await store.load(cid)
        if conversation_id
        else {"conversation_id": cid, "messages": [], "context": {}, "updated_at": _now()}
    )
    context = AgentContext.from_dict(data.get("context"))
    user_msg = {"role": "user", "content": user_input, "ts": _now()}
    data.setdefault("messages", []).append(user_msg)

    yield {"event": "conversation", "data": {"conversation_id": cid}}
    yield {"event": "user_message", "data": user_msg}

    for step in range(settings.AGENT_MAX_STEPS):
        content_parts: list[str] = []
        final_resp: LLMResponse | None = None
        try:
            async for kind, payload in llm.chat_stream(
                _llm_messages(data, context, role), tools=tools_for_role(role)
            ):
                if kind == "delta":
                    content_parts.append(payload)
                    yield {"event": "message_delta", "data": {"text": payload}}
                else:
                    final_resp = payload
        except Exception as exc:  # noqa: BLE001
            msg = f"模型调用失败：{exc}"
            err = {"role": "assistant", "content": msg, "ts": _now(), "type": "error"}
            data["messages"].append(err)
            await store.save(cid, data)
            yield {"event": "error", "data": {"message": msg}}
            return

        assert final_resp is not None
        if not final_resp.tool_calls:
            assistant = {"role": "assistant", "content": "".join(content_parts), "ts": _now()}
            data["messages"].append(assistant)
            data["context"] = context.to_dict()
            await store.save(cid, data)
            yield {"event": "done", "data": {"conversation_id": cid, "message": assistant}}
            return

        assistant_tool_msg = {
            "role": "assistant",
            "content": "".join(content_parts),
            "tool_calls": [c.to_openai() for c in final_resp.tool_calls],
            "ts": _now(),
        }
        data["messages"].append(assistant_tool_msg)
        yield {"event": "assistant_tool_call", "data": assistant_tool_msg}

        for call in final_resp.tool_calls:
            args = call.parsed_arguments()
            yield {"event": "tool_start", "data": {"id": call.id, "name": call.name, "args": args}}
            result = await dispatch(call.name, db, operator_id, args, context, role=role)
            _save_tool_log(db, cid, call.name, args, result)
            entry = _tool_entry(call.id, call.name, args, result)
            data["messages"].append(entry)
            yield {
                "event": "tool_finish",
                "data": {
                    "id": call.id,
                    "name": call.name,
                    "ok": entry["ok"],
                    "card": entry["card"],
                    "message": entry,
                },
            }
        data["context"] = context.to_dict()
        await store.save(cid, data)

    msg = f"达到最大工具调用步数（{settings.AGENT_MAX_STEPS}），已中止本轮处理。"
    err = {"role": "assistant", "content": msg, "ts": _now(), "type": "error"}
    data["messages"].append(err)
    await store.save(cid, data)
    yield {"event": "error", "data": {"message": msg}}


async def get_conversation(conversation_id: str) -> dict:
    return await store.load(conversation_id)


def tool_logs_query(db: Session, conversation_id: str | None = None, limit: int = 100) -> list[dict]:
    from sqlalchemy import select

    stmt = select(AgentToolLog)
    if conversation_id:
        stmt = stmt.where(AgentToolLog.conversation_id == conversation_id)
    rows = db.execute(stmt.order_by(AgentToolLog.created_at.desc()).limit(limit)).scalars().all()
    return [
        {
            "log_id": r.id,
            "conversation_id": r.conversation_id,
            "tool_name": r.tool_name,
            "args": r.args_json,
            "result": r.result_json,
            "created_at": r.created_at,
        }
        for r in rows
    ]


__all__: list[Any] = ["run_agent", "run_agent_stream", "get_conversation", "tool_logs_query"]
