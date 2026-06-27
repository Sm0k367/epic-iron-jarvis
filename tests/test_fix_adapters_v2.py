"""Offline tests for the v2 adapter features (no network):

A. Token usage — each REAL adapter populates ``LLMResponse.usage`` from the
   vendor response; the offline mock stays at 0/0.
B. Image/vision — anthropic + openai (+ google) emit image parts in the request
   body when a user ``LLMMessage`` carries ``images``.
C. Local Ollama / OpenAI-compatible — ``OpenAIAdapter(base_url=..., api_key=None)``
   posts to the custom URL and sends NO Authorization header.
D. ProviderManager — with ``ollama_base_url`` configured, ``available("ollama")``
   is True and ``get("ollama")`` builds an adapter pointed at the base_url.

Fake async HTTP clients are injected exactly like ``test_new_adapters.py`` /
``test_fix_oauth.py`` so nothing touches the network.
"""

from __future__ import annotations

from iron_jarvis.providers.adapters.anthropic import AnthropicAdapter
from iron_jarvis.providers.adapters.base import LLMMessage
from iron_jarvis.providers.adapters.google import GoogleAdapter
from iron_jarvis.providers.adapters.mock import MockLLMAdapter
from iron_jarvis.providers.adapters.openai import OpenAIAdapter
from iron_jarvis.providers.manager import ProviderManager


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class FakeHTTP:
    """Records each POST and returns a canned response (async post)."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.calls: list[dict] = []

    async def post(self, url, *, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers or {}, "json": json or {}})
        return FakeResponse(self._payload)

    @property
    def last(self) -> dict:
        return self.calls[-1]


# -- Anthropic SDK stand-ins (the adapter speaks the SDK, not raw httpx) ----- #
class _Attr:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _FakeMessages:
    def __init__(self, parent):
        self._parent = parent

    async def create(self, **kwargs):
        self._parent.calls.append(kwargs)
        return self._parent.response


class FakeAnthropicClient:
    def __init__(self, response) -> None:
        self.response = response
        self.calls: list[dict] = []
        self.messages = _FakeMessages(self)


def _anthropic_response(*, input_tokens=0, output_tokens=0):
    return _Attr(
        content=[_Attr(type="text", text="hi")],
        stop_reason="end_turn",
        usage=_Attr(input_tokens=input_tokens, output_tokens=output_tokens),
    )


IMG = {"data_b64": "QUJD", "media_type": "image/png"}


# --------------------------------------------------------------------------- #
# A. token usage
# --------------------------------------------------------------------------- #
async def test_anthropic_populates_usage():
    adapter = AnthropicAdapter(api_key="sk-ant")
    client = FakeAnthropicClient(_anthropic_response(input_tokens=21, output_tokens=8))
    adapter._client = lambda: client  # inject the fake SDK client
    res = await adapter.complete(
        system="s", messages=[LLMMessage(role="user", content="hi")], tools=[]
    )
    assert res.usage == {"input_tokens": 21, "output_tokens": 8}


async def test_anthropic_usage_guards_missing():
    adapter = AnthropicAdapter(api_key="sk-ant")
    resp = _Attr(content=[_Attr(type="text", text="hi")], stop_reason="end_turn")
    adapter._client = lambda: FakeAnthropicClient(resp)
    res = await adapter.complete(system="", messages=[], tools=[])
    assert res.usage == {"input_tokens": 0, "output_tokens": 0}


async def test_openai_populates_usage():
    http = FakeHTTP(
        {
            "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 31, "completion_tokens": 12},
        }
    )
    adapter = OpenAIAdapter(api_key="sk-test", http=http)
    res = await adapter.complete(
        system="", messages=[LLMMessage(role="user", content="hi")], tools=[]
    )
    assert res.usage == {"input_tokens": 31, "output_tokens": 12}


async def test_openai_usage_guards_missing():
    http = FakeHTTP({"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}]})
    adapter = OpenAIAdapter(api_key="sk-test", http=http)
    res = await adapter.complete(system="", messages=[], tools=[])
    assert res.usage == {"input_tokens": 0, "output_tokens": 0}


async def test_google_populates_usage():
    http = FakeHTTP(
        {
            "candidates": [
                {"content": {"parts": [{"text": "hi"}]}, "finishReason": "STOP"}
            ],
            "usageMetadata": {"promptTokenCount": 17, "candidatesTokenCount": 5},
        }
    )
    adapter = GoogleAdapter(api_key="g-test", http=http)
    res = await adapter.complete(
        system="", messages=[LLMMessage(role="user", content="hi")], tools=[]
    )
    assert res.usage == {"input_tokens": 17, "output_tokens": 5}


async def test_google_usage_guards_missing():
    http = FakeHTTP(
        {"candidates": [{"content": {"parts": [{"text": "hi"}]}, "finishReason": "STOP"}]}
    )
    adapter = GoogleAdapter(api_key="g-test", http=http)
    res = await adapter.complete(system="", messages=[], tools=[])
    assert res.usage == {"input_tokens": 0, "output_tokens": 0}


async def test_mock_usage_stays_zero():
    adapter = MockLLMAdapter()
    res = await adapter.complete(
        system="", messages=[LLMMessage(role="user", content="do a thing")], tools=[]
    )
    assert res.usage == {"input_tokens": 0, "output_tokens": 0}


# --------------------------------------------------------------------------- #
# B. image / vision request shaping
# --------------------------------------------------------------------------- #
async def test_anthropic_emits_image_block():
    adapter = AnthropicAdapter(api_key="sk-ant")
    client = FakeAnthropicClient(_anthropic_response())
    adapter._client = lambda: client
    await adapter.complete(
        system="",
        messages=[LLMMessage(role="user", content="look", images=[IMG])],
        tools=[],
    )
    content = client.calls[-1]["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "look"}
    assert content[1] == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": "QUJD"},
    }


async def test_anthropic_plain_string_without_images():
    adapter = AnthropicAdapter(api_key="sk-ant")
    client = FakeAnthropicClient(_anthropic_response())
    adapter._client = lambda: client
    await adapter.complete(
        system="", messages=[LLMMessage(role="user", content="plain")], tools=[]
    )
    assert client.calls[-1]["messages"][0]["content"] == "plain"


async def test_openai_emits_image_part():
    http = FakeHTTP({"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})
    adapter = OpenAIAdapter(api_key="sk-test", http=http)
    await adapter.complete(
        system="",
        messages=[LLMMessage(role="user", content="look", images=[IMG])],
        tools=[],
    )
    content = http.last["json"]["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "look"}
    assert content[1] == {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,QUJD"},
    }


async def test_openai_plain_string_without_images():
    http = FakeHTTP({"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})
    adapter = OpenAIAdapter(api_key="sk-test", http=http)
    await adapter.complete(
        system="", messages=[LLMMessage(role="user", content="plain")], tools=[]
    )
    assert http.last["json"]["messages"][0]["content"] == "plain"


async def test_google_emits_inline_data_part():
    http = FakeHTTP(
        {"candidates": [{"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}]}
    )
    adapter = GoogleAdapter(api_key="g-test", http=http)
    await adapter.complete(
        system="",
        messages=[LLMMessage(role="user", content="look", images=[IMG])],
        tools=[],
    )
    parts = http.last["json"]["contents"][0]["parts"]
    assert parts[0] == {"text": "look"}
    assert parts[1] == {"inline_data": {"mime_type": "image/png", "data": "QUJD"}}


# --------------------------------------------------------------------------- #
# C. local Ollama / OpenAI-compatible endpoint (no API key)
# --------------------------------------------------------------------------- #
_OLLAMA_URL = "http://localhost:11434/v1/chat/completions"


async def test_openai_custom_base_url_no_auth_header():
    http = FakeHTTP({"choices": [{"message": {"content": "local hi"}, "finish_reason": "stop"}]})
    adapter = OpenAIAdapter(base_url=_OLLAMA_URL, api_key=None, http=http)
    res = await adapter.complete(
        system="", messages=[LLMMessage(role="user", content="hi")], tools=[]
    )
    assert http.last["url"] == _OLLAMA_URL
    assert "Authorization" not in http.last["headers"]
    assert res.text == "local hi"


async def test_openai_custom_base_url_with_key_still_sends_auth():
    http = FakeHTTP({"choices": [{"message": {"content": "x"}, "finish_reason": "stop"}]})
    adapter = OpenAIAdapter(base_url=_OLLAMA_URL, api_key="sk-local", http=http)
    await adapter.complete(
        system="", messages=[LLMMessage(role="user", content="hi")], tools=[]
    )
    assert http.last["headers"]["Authorization"] == "Bearer sk-local"


# --------------------------------------------------------------------------- #
# D. ProviderManager: ollama availability + adapter wiring
# --------------------------------------------------------------------------- #
def test_manager_ollama_unavailable_without_base_url():
    pm = ProviderManager()
    assert pm.available("ollama") is False


def test_manager_ollama_available_with_base_url():
    pm = ProviderManager(ollama_base_url=_OLLAMA_URL, ollama_model="llama3.1")
    assert pm.available("ollama") is True
    adapter = pm.get("ollama")
    assert isinstance(adapter, OpenAIAdapter)
    assert adapter._endpoint == _OLLAMA_URL
    assert adapter.model == "llama3.1"
    assert adapter.provider == "ollama"


def test_manager_ollama_health_row_local_class():
    pm = ProviderManager(ollama_base_url=_OLLAMA_URL)
    rows = {r["provider"]: r for r in pm.health()}
    assert rows["ollama"]["available"] is True
    assert rows["ollama"]["class"] == "local"
