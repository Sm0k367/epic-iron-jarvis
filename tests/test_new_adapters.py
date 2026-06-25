"""Offline tests for the OpenAI + Google Gemini adapters (no network).

A fake async ``http`` client is injected: its ``post`` is an async coroutine that
records the call and returns a fake response whose ``.json()`` yields a canned
vendor payload. This exercises both request shaping (URL + credential + body) and
response parsing without ever touching the network.
"""

from __future__ import annotations

import json

import pytest

from iron_jarvis.providers.adapters.base import LLMMessage, ToolCall
from iron_jarvis.providers.adapters.google import GoogleAdapter
from iron_jarvis.providers.adapters.openai import OpenAIAdapter


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class FakeHTTP:
    """Records the last POST and returns a canned response (async post)."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.calls: list[dict] = []

    async def post(self, url, *, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers or {}, "json": json or {}})
        return FakeResponse(self._payload)

    @property
    def last(self) -> dict:
        return self.calls[-1]


SAMPLE_TOOLS = [
    {
        "name": "write_file",
        "description": "Write a file",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    }
]


# --------------------------------------------------------------------------- #
# OpenAI
# --------------------------------------------------------------------------- #
async def test_openai_text_response():
    http = FakeHTTP(
        {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "hello world"},
                    "finish_reason": "stop",
                }
            ]
        }
    )
    adapter = OpenAIAdapter(api_key="sk-test", http=http)
    res = await adapter.complete(
        system="be terse",
        messages=[LLMMessage(role="user", content="hi")],
        tools=[],
    )

    # request shaping: right URL + credential + system message first
    assert http.last["url"] == "https://api.openai.com/v1/chat/completions"
    assert http.last["headers"]["Authorization"] == "Bearer sk-test"
    assert http.last["json"]["messages"][0] == {
        "role": "system",
        "content": "be terse",
    }
    # response parsing
    assert res.text == "hello world"
    assert res.finish_reason == "stop"
    assert not res.wants_tools


async def test_openai_tool_call_response():
    http = FakeHTTP(
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_42",
                                "type": "function",
                                "function": {
                                    "name": "write_file",
                                    "arguments": json.dumps(
                                        {"path": "a.txt", "content": "hi"}
                                    ),
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }
    )
    adapter = OpenAIAdapter(api_key="sk-test", http=http)
    res = await adapter.complete(
        system="",
        messages=[LLMMessage(role="user", content="write a file")],
        tools=SAMPLE_TOOLS,
    )

    # tools were mapped into the OpenAI function shape
    sent_tool = http.last["json"]["tools"][0]
    assert sent_tool["type"] == "function"
    assert sent_tool["function"]["name"] == "write_file"
    assert sent_tool["function"]["parameters"] == SAMPLE_TOOLS[0]["input_schema"]
    # no system message when system is empty
    assert http.last["json"]["messages"][0]["role"] == "user"

    # parsed into a ToolCall with the right name + arguments
    assert res.finish_reason == "tool_use"
    assert res.wants_tools
    tc = res.tool_calls[0]
    assert tc.id == "call_42"
    assert tc.name == "write_file"
    assert tc.arguments == {"path": "a.txt", "content": "hi"}


async def test_openai_replays_assistant_tool_calls_and_tool_results():
    http = FakeHTTP({"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})
    adapter = OpenAIAdapter(api_key="sk-test", http=http)
    await adapter.complete(
        system="",
        messages=[
            LLMMessage(role="user", content="go"),
            LLMMessage(
                role="assistant",
                tool_calls=[ToolCall("c1", "write_file", {"path": "a"})],
            ),
            LLMMessage(role="tool", tool_call_id="c1", name="write_file", content="done"),
        ],
        tools=SAMPLE_TOOLS,
    )
    sent = http.last["json"]["messages"]
    assistant = next(m for m in sent if m["role"] == "assistant")
    assert assistant["tool_calls"][0]["id"] == "c1"
    assert assistant["tool_calls"][0]["function"]["name"] == "write_file"
    tool_msg = next(m for m in sent if m["role"] == "tool")
    assert tool_msg == {"role": "tool", "tool_call_id": "c1", "content": "done"}


async def test_openai_missing_credential_raises():
    adapter = OpenAIAdapter(http=FakeHTTP({}))
    with pytest.raises(RuntimeError):
        await adapter.complete(system="", messages=[], tools=[])


async def test_openai_credential_callable_resolved_at_call_time():
    box = {"key": None}
    http = FakeHTTP({"choices": [{"message": {"content": "x"}, "finish_reason": "stop"}]})
    adapter = OpenAIAdapter(credential=lambda: box["key"], http=http)
    # not yet provisioned -> raises
    with pytest.raises(RuntimeError):
        await adapter.complete(system="", messages=[], tools=[])
    # provision later -> now works
    box["key"] = "sk-late"
    await adapter.complete(system="", messages=[LLMMessage("user", "hi")], tools=[])
    assert http.last["headers"]["Authorization"] == "Bearer sk-late"


# --------------------------------------------------------------------------- #
# Google Gemini
# --------------------------------------------------------------------------- #
async def test_google_text_response():
    http = FakeHTTP(
        {
            "candidates": [
                {
                    "content": {"role": "model", "parts": [{"text": "bonjour"}]},
                    "finishReason": "STOP",
                }
            ]
        }
    )
    adapter = GoogleAdapter(api_key="g-test", http=http)
    res = await adapter.complete(
        system="be nice",
        messages=[LLMMessage(role="user", content="hi")],
        tools=[],
    )

    assert http.last["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-1.5-flash:generateContent"
    )
    assert http.last["headers"]["x-goog-api-key"] == "g-test"
    assert http.last["json"]["system_instruction"] == {"parts": [{"text": "be nice"}]}
    assert http.last["json"]["contents"][0] == {
        "role": "user",
        "parts": [{"text": "hi"}],
    }
    assert res.text == "bonjour"
    assert res.finish_reason == "stop"
    assert not res.wants_tools


async def test_google_function_call_response():
    http = FakeHTTP(
        {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "write_file",
                                    "args": {"path": "a.txt", "content": "hi"},
                                }
                            }
                        ],
                    },
                    "finishReason": "STOP",
                }
            ]
        }
    )
    adapter = GoogleAdapter(api_key="g-test", http=http)
    res = await adapter.complete(
        system="",
        messages=[LLMMessage(role="user", content="write a file")],
        tools=SAMPLE_TOOLS,
    )

    # tools mapped to function_declarations; no system_instruction when empty
    decls = http.last["json"]["tools"][0]["function_declarations"]
    assert decls[0]["name"] == "write_file"
    assert decls[0]["parameters"] == SAMPLE_TOOLS[0]["input_schema"]
    assert "system_instruction" not in http.last["json"]

    assert res.finish_reason == "tool_use"
    assert res.wants_tools
    tc = res.tool_calls[0]
    assert tc.name == "write_file"
    assert tc.arguments == {"path": "a.txt", "content": "hi"}


async def test_google_maps_roles_and_tool_results():
    http = FakeHTTP(
        {"candidates": [{"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}]}
    )
    adapter = GoogleAdapter(api_key="g-test", http=http)
    await adapter.complete(
        system="",
        messages=[
            LLMMessage(role="user", content="go"),
            LLMMessage(
                role="assistant",
                tool_calls=[ToolCall("c1", "write_file", {"path": "a"})],
            ),
            LLMMessage(role="tool", tool_call_id="c1", name="write_file", content="done"),
        ],
        tools=SAMPLE_TOOLS,
    )
    contents = http.last["json"]["contents"]
    # assistant -> role "model" carrying a functionCall part
    assert contents[1]["role"] == "model"
    assert contents[1]["parts"][0]["functionCall"]["name"] == "write_file"
    # tool result -> role "user" carrying a functionResponse part
    assert contents[2]["role"] == "user"
    fr = contents[2]["parts"][0]["functionResponse"]
    assert fr["name"] == "write_file"
    assert fr["response"] == {"result": "done"}


async def test_google_missing_credential_raises():
    adapter = GoogleAdapter(http=FakeHTTP({}))
    with pytest.raises(RuntimeError):
        await adapter.complete(system="", messages=[], tools=[])
