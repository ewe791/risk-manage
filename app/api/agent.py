"""Agent 对话接口：普通 JSON 与 SSE 流式两种形态。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agent.orchestrator import get_conversation, run_agent, run_agent_stream, tool_logs_query
from app.agent.store import store
from app.deps import BizError, CurrentOperator, get_current_operator, get_db, ok
from app.schemas.risk import ChatRequest

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    operator: CurrentOperator = Depends(get_current_operator),
):
    """对话入口：operator_id 从 JWT 注入，LLM 无法指定身份。"""
    result = await run_agent(
        db,
        operator_id=operator.operator_id,
        conversation_id=payload.conversation_id,
        user_input=payload.message,
        role=operator.role,
    )
    return ok(
        {
            "conversation_id": result["conversation_id"],
            "messages": result["messages"],
            "type": result["type"],
            "steps": result.get("steps", 0),
            "context": result.get("context", {}),
        }
    )


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    operator: CurrentOperator = Depends(get_current_operator),
):
    async def event_source():
        try:
            async for evt in run_agent_stream(
                db,
                operator_id=operator.operator_id,
                conversation_id=payload.conversation_id,
                user_input=payload.message,
                role=operator.role,
            ):
                yield f"event: {evt['event']}\ndata: {json.dumps(evt['data'], ensure_ascii=False, default=str)}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield f"event: error\ndata: {json.dumps({'message': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations")
async def list_conversations(
    limit: int = Query(30, ge=1, le=100),
    operator: CurrentOperator = Depends(get_current_operator),
):
    return ok({"items": await store.list_conversations(limit), "backend": store.backend})


@router.get("/conversations/{conversation_id}/messages")
async def conversation_messages(
    conversation_id: str,
    operator: CurrentOperator = Depends(get_current_operator),
):
    data = await get_conversation(conversation_id)
    if not data.get("messages"):
        raise BizError(f"会话不存在或已过期: {conversation_id}", 404)
    return ok(
        {
            "conversation_id": conversation_id,
            "messages": data.get("messages", []),
            "context": data.get("context", {}),
            "updated_at": data.get("updated_at"),
        }
    )


@router.get("/tool-logs")
def tool_logs(
    conversation_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    operator: CurrentOperator = Depends(get_current_operator),
):
    return ok({"items": tool_logs_query(db, conversation_id, limit)})
