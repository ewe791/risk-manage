"""会话存储：Redis 优先（会话 + Agent 上下文），不可用时自动降级为进程内缓存。

存储结构（每个会话一条记录）：
{
  "conversation_id": "...",
  "messages": [ {role, content, tool_calls?, tool_call_id?, name?, card?, ts} ],
  "context": {"subject_user_id": ..., "last_order_id": ..., ...},
  "updated_at": "ISO8601"
}
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.config import settings

_KEY_PREFIX = "risk:conv:"
_INDEX_KEY = "risk:conv:index"


class ConversationStore:
    def __init__(self) -> None:
        self._memory: dict[str, dict] = {}
        self._expire_at: dict[str, float] = {}
        self._redis = None
        self._redis_checked = False
        self._lock = asyncio.Lock()

    async def _client(self):
        if self._redis_checked:
            return self._redis
        self._redis_checked = True
        if not settings.REDIS_URL:
            self._redis = None
            return None
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(
                settings.REDIS_URL, encoding="utf-8", decode_responses=True
            )
            await client.ping()
            self._redis = client
        except Exception:  # noqa: BLE001 —— Redis 不可用则降级，不阻塞业务
            self._redis = None
        return self._redis

    @property
    def backend(self) -> str:
        return "redis" if self._redis is not None else "memory"

    def new_id(self) -> str:
        return f"CONV-{uuid.uuid4().hex[:10]}"

    async def load(self, conversation_id: str) -> dict:
        client = await self._client()
        if client:
            try:
                raw = await client.get(f"{_KEY_PREFIX}{conversation_id}")
                if raw:
                    return json.loads(raw)
            except Exception:  # noqa: BLE001
                self._redis = None
        async with self._lock:
            self._gc()
            return self._memory.get(conversation_id) or {
                "conversation_id": conversation_id,
                "messages": [],
                "context": {},
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

    async def save(self, conversation_id: str, data: dict) -> None:
        data["conversation_id"] = conversation_id
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        client = await self._client()
        if client:
            try:
                await client.set(
                    f"{_KEY_PREFIX}{conversation_id}",
                    json.dumps(data, ensure_ascii=False, default=str),
                    ex=settings.CONVERSATION_TTL_SECONDS,
                )
                await client.zadd(_INDEX_KEY, {conversation_id: time.time()})
                return
            except Exception:  # noqa: BLE001
                self._redis = None
        async with self._lock:
            self._gc()
            self._memory[conversation_id] = data
            self._expire_at[conversation_id] = time.time() + settings.CONVERSATION_TTL_SECONDS

    def _gc(self) -> None:
        now = time.time()
        expired = [k for k, exp in self._expire_at.items() if exp < now]
        for k in expired:
            self._memory.pop(k, None)
            self._expire_at.pop(k, None)

    async def list_conversations(self, limit: int = 30) -> list[dict]:
        items: list[dict] = []
        client = await self._client()
        if client:
            try:
                ids = await client.zrevrange(_INDEX_KEY, 0, limit - 1)
            except Exception:  # noqa: BLE001
                ids = []
                self._redis = None
            for cid in ids:
                data = await self.load(cid)
                items.append(self._summary(data))
            if items:
                return items
        async with self._lock:
            self._gc()
            ordered = sorted(
                self._memory.values(), key=lambda d: d.get("updated_at", ""), reverse=True
            )
        return [self._summary(d) for d in ordered[:limit]]

    @staticmethod
    def _summary(data: dict) -> dict:
        messages = data.get("messages") or []
        last_user = next((m for m in reversed(messages) if m.get("role") == "user"), None)
        return {
            "conversation_id": data.get("conversation_id"),
            "title": (last_user or {}).get("content", "")[:40] or "新会话",
            "message_count": len(messages),
            "updated_at": data.get("updated_at"),
        }

    def llm_history(self, data: dict, limit: int) -> list[dict]:
        """截取最近 N 条并转成 OpenAI 消息格式（剔除 UI 的 card 字段）。"""
        out: list[dict] = []
        for msg in (data.get("messages") or [])[-limit:]:
            item: dict[str, Any] = {"role": msg["role"], "content": msg.get("content") or ""}
            if msg.get("tool_calls"):
                item["tool_calls"] = msg["tool_calls"]
            if msg.get("tool_call_id"):
                item["tool_call_id"] = msg["tool_call_id"]
            if msg.get("name"):
                item["name"] = msg["name"]
            out.append(item)
        return out


store = ConversationStore()
