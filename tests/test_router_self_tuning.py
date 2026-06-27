"""Self-tuning router (§6 phase-1), offline + deterministic.

Verifies the opt-in local-preference hook: it is a no-op by default, it never
prefers an unavailable local model, it prefers a capable local model only on the
default route, and an explicit non-default provider choice bypasses it entirely.
No network and no DB — we assert on `_resolve`'s routing decision directly.
"""

from __future__ import annotations

from iron_jarvis.core.events import EventBus
from iron_jarvis.providers.manager import ProviderManager
from iron_jarvis.providers.router import ModelRouter

OLLAMA_URL = "http://127.0.0.1:11434/v1"


def _manager(ollama_url: str | None = None) -> ProviderManager:
    return ProviderManager(default_model="m", ollama_base_url=ollama_url)


def _router(manager: ProviderManager, **kw) -> ModelRouter:
    return ModelRouter(manager, "mock", EventBus(), **kw)


def test_default_routing_unchanged_without_oracle() -> None:
    r = _router(_manager())
    adapter, wanted, downgraded = r._resolve(None, None)
    assert wanted == "mock"
    assert not downgraded
    assert adapter.provider == "mock"


def test_oracle_off_when_local_unavailable() -> None:
    # Oracle nominates ollama, but no base_url => unavailable => normal routing.
    r = _router(_manager(), local_oracle=lambda tc: ("ollama", "llama3.1"))
    adapter, wanted, downgraded = r._resolve(None, None, task_class="coder")
    assert wanted == "mock"
    assert adapter.provider == "mock"


def test_oracle_none_pick_is_noop() -> None:
    # Oracle present but declines (returns None) => byte-for-byte unchanged.
    r = _router(_manager(OLLAMA_URL), local_oracle=lambda tc: None)
    adapter, wanted, downgraded = r._resolve(None, None, task_class="coder")
    assert wanted == "mock"
    assert adapter.provider == "mock"


def test_oracle_prefers_capable_local_on_default_route() -> None:
    r = _router(_manager(OLLAMA_URL), local_oracle=lambda tc: ("ollama", "llama3.1"))
    adapter, wanted, downgraded = r._resolve(None, None, task_class="coder")
    assert wanted == "ollama"
    assert not downgraded
    assert adapter.provider == "ollama"


def test_explicit_non_default_provider_bypasses_oracle() -> None:
    # User explicitly picked a non-default provider: honor it (here anthropic is
    # unavailable offline => downgrades to mock, NOT ollama).
    r = _router(_manager(OLLAMA_URL), local_oracle=lambda tc: ("ollama", "llama3.1"))
    adapter, wanted, downgraded = r._resolve("anthropic", None, task_class="coder")
    assert adapter.provider == "mock"
    assert downgraded


def test_oracle_exception_never_breaks_routing() -> None:
    def boom(_tc: str | None) -> tuple[str, str]:
        raise RuntimeError("oracle blew up")

    r = _router(_manager(OLLAMA_URL), local_oracle=boom)
    adapter, wanted, downgraded = r._resolve(None, None, task_class="coder")
    assert adapter.provider == "mock"


# --- swarm-review fix: a DOWN self-tuned local pick falls back to the real
#     default provider, never to a fabricated mock answer --------------------
from iron_jarvis.providers.adapters.base import LLMResponse  # noqa: E402


class _Adapter:
    def __init__(self, provider: str, *, ok: bool = True) -> None:
        self.provider = provider
        self.model = "m"
        self._ok = ok

    async def complete(self, *, system, messages, tools) -> LLMResponse:
        if not self._ok:
            raise ConnectionError(f"{self.provider} down")
        return LLMResponse(text=f"hi from {self.provider}")


class _FakeManager:
    def __init__(self, adapters: dict, available: dict) -> None:
        self._a = adapters
        self._avail = available

    def get(self, provider: str, model=None):
        return self._a[provider]

    def available(self, provider: str) -> bool:
        return bool(self._avail.get(provider, False))


async def test_failed_local_pick_falls_back_to_default_not_mock() -> None:
    adapters = {
        "ollama": _Adapter("ollama", ok=False),  # self-tuned local pick is DOWN
        "anthropic": _Adapter("anthropic", ok=True),  # healthy cloud default
        "mock": _Adapter("mock", ok=True),
    }
    mgr = _FakeManager(adapters, {"ollama": True, "anthropic": True, "mock": True})
    r = ModelRouter(mgr, "anthropic", EventBus(), local_oracle=lambda tc: ("ollama", "llama3.1"))
    res = await r.complete(system="s", messages=[], tools=[], task_class="coder")
    assert res.provider == "anthropic"  # fell back to the healthy default, NOT mock
    assert "anthropic" in res.response.text
