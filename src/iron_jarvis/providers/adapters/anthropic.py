"""Anthropic adapter (§5 API-provider class).

Default model ``claude-opus-4-8``. Not exercised by the offline test suite; it
runs only when ANTHROPIC_API_KEY is set. When extending this, consult the
`claude-api` skill for current model ids, params, and tool-use shapes.
"""

from __future__ import annotations

import os
from typing import Any

from .base import LLMAdapter, LLMMessage, LLMResponse, ToolCall


class AnthropicAdapter(LLMAdapter):
    provider = "anthropic"

    def __init__(
        self,
        model: str = "claude-opus-4-8",
        max_tokens: int = 4096,
        *,
        api_key: str | None = None,
        credential=None,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self._api_key = api_key
        self._credential = credential  # Callable[[], str | None] | None

    def _key(self) -> str | None:
        if self._api_key:
            return self._api_key
        if self._credential is not None:
            key = self._credential()
            if key:
                return key
        return os.environ.get("ANTHROPIC_API_KEY")

    def _client(self):
        key = self._key()
        if not key:
            raise RuntimeError(
                "No Anthropic credential — connect it on the Connections page."
            )
        from anthropic import AsyncAnthropic  # lazy import

        return AsyncAnthropic(api_key=key)

    @staticmethod
    def _to_anthropic_messages(messages: list[LLMMessage]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "tool":
                out.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": m.tool_call_id,
                                "content": m.content,
                            }
                        ],
                    }
                )
            elif m.role == "assistant" and m.tool_calls:
                blocks: list[dict[str, Any]] = []
                if m.content:
                    blocks.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments,
                        }
                    )
                out.append({"role": "assistant", "content": blocks})
            else:
                out.append({"role": m.role, "content": m.content})
        return out

    async def complete(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        client = self._client()
        resp = await client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system or "",
            messages=self._to_anthropic_messages(messages),
            tools=[
                {
                    "name": t["name"],
                    "description": t["description"],
                    "input_schema": t["input_schema"],
                }
                for t in tools
            ],
        )
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, arguments=dict(block.input))
                )
        finish = "tool_use" if resp.stop_reason == "tool_use" else "stop"
        return LLMResponse(
            text="".join(text_parts), tool_calls=tool_calls, finish_reason=finish
        )
