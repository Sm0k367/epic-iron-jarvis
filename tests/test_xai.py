"""xAI (Grok) provider — OpenAI-compatible, key now + OAuth-ready spec."""

from __future__ import annotations

from iron_jarvis.agents.dynamic import available_models
from iron_jarvis.platform import build_platform
from iron_jarvis.providers.manager import API_PROVIDERS, XAI_ENDPOINT


def test_xai_in_api_providers():
    assert "xai" in API_PROVIDERS


def test_xai_available_only_with_a_credential(tmp_path):
    p = build_platform(str(tmp_path))
    assert not p.providers.available("xai")  # no key -> not available
    p.connections.set_api_key("xai", "xai-test-key")
    assert p.providers.available("xai")  # connected via key -> available


def test_xai_routes_through_openai_compatible_endpoint(tmp_path):
    p = build_platform(str(tmp_path))
    adapter = p.providers.get("xai", "grok-2-latest")
    assert adapter.provider == "xai"
    assert adapter._endpoint == XAI_ENDPOINT  # api.x.ai, not OpenAI


def test_xai_spec_is_key_now_oauth_ready(tmp_path):
    spec = build_platform(str(tmp_path)).connections.get_spec("xai")
    assert spec is not None
    assert spec.supports_api_key and spec.key_secret_name == "xai_api_key"
    assert not spec.supports_oauth  # no public OAuth client yet (overridable later)


def test_grok_in_model_catalog():
    provs = {m["provider"] for m in available_models()}
    assert "xai" in provs
    assert any(m["model"].startswith("grok") for m in available_models())
