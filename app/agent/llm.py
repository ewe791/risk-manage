"""LLM 客户端：OpenAI 兼容接口（base_url 可配，支持 DeepSeek/Qwen/vLLM）。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from app.config import settings


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str

    def parsed_arguments(self) -> dict:
        """容错解析：非法 JSON 返回空字典，由 tool 层报错回填给模型。"""
        try:
            data = json.loads(self.arguments or "{}")
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def to_openai(self) -> dict:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments or "{}"},
        }


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    usage: dict = field(default_factory=dict)
    raw: Any = None


class LLMClient:
    """薄封装，不做重试魔改：失败由 orchestrator 决定如何回填。"""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            timeout=settings.LLM_TIMEOUT_SECONDS,
            max_retries=1,
        )

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
        temperature: float | None = None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": settings.LLM_MODEL,
            "messages": messages,
            "temperature": settings.LLM_TEMPERATURE if temperature is None else temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        resp = await self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        msg = choice.message
        calls = [
            ToolCall(
                id=tc.id or f"call_{i}",
                name=tc.function.name,
                arguments=tc.function.arguments or "{}",
            )
            for i, tc in enumerate(msg.tool_calls or [])
        ]
        return LLMResponse(
            content=msg.content or "",
            tool_calls=calls,
            model=resp.model or settings.LLM_MODEL,
            usage=resp.usage.model_dump() if resp.usage else {},
            raw=resp,
        )

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
    ) -> AsyncIterator[tuple[str, Any]]:
        """流式：yield ("delta", 文本片段) ... 最后 yield ("done", LLMResponse)。"""
        kwargs: dict[str, Any] = {
            "model": settings.LLM_MODEL,
            "messages": messages,
            "temperature": settings.LLM_TEMPERATURE,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        stream = await self._client.chat.completions.create(**kwargs)
        parts: list[str] = []
        slots: dict[int, dict] = {}
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if getattr(delta, "content", None):
                parts.append(delta.content)
                yield "delta", delta.content
            for tc in getattr(delta, "tool_calls", None) or []:
                slot = slots.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                if tc.id:
                    slot["id"] = tc.id
                if tc.function and tc.function.name:
                    slot["name"] += tc.function.name
                if tc.function and tc.function.arguments:
                    slot["arguments"] += tc.function.arguments
        calls = [
            ToolCall(
                id=slot["id"] or f"call_{idx}",
                name=slot["name"],
                arguments=slot["arguments"] or "{}",
            )
            for idx, slot in sorted(slots.items())
        ]
        yield "done", LLMResponse(content="".join(parts), tool_calls=calls, model=settings.LLM_MODEL)


llm = LLMClient()
