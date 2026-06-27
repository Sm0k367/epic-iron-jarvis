"""Regression tests for the OAuth / Google-credential audit fixes (offline).

Covers three confirmed findings:

* (6) ``GoogleAdapter`` must send an OAuth access token as ``Authorization:
  Bearer`` (not ``x-goog-api-key``), while a true api_key connection keeps
  ``x-goog-api-key``.
* (7) A failed token exchange (HTTP 4xx / ``{"error": ...}`` / missing
  ``access_token``) must RAISE and never be persisted as a "connected"
  credential.
* (8) Availability/health checks must be presence-only: ``has_credential`` and a
  ``presence_resolver``-wired ``ProviderManager`` never trigger a network
  refresh.

Everything is faked (HTTP transport + secrets vault) so nothing touches the
network or real encryption, mirroring ``test_new_adapters.py`` /
``test_connections.py``.
"""

from __future__ import annotations

import json

import pytest

import iron_jarvis.connections.models  # noqa: F401  (register table before init_db)
from iron_jarvis.connections import ConnectionRegistry
from iron_jarvis.core.db import init_db, make_engine
from iron_jarvis.providers.adapters.base import LLMMessage
from iron_jarvis.providers.adapters.google import GoogleAdapter
from iron_jarvis.providers.manager import ProviderManager


# --- fakes ---------------------------------------------------------------


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeAsyncHTTP:
    """Async ``post`` recorder returning a canned response (adapter transport)."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.calls: list[dict] = []

    async def post(self, url, *, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers or {}, "json": json or {}})
        return FakeResponse(self._payload)

    @property
    def last(self) -> dict:
        return self.calls[-1]


class FakeSyncHTTP:
    """Sync ``post`` recorder for token exchange/refresh (registry transport)."""

    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.calls: list[dict] = []
        self.closed = False

    def post(self, url, data=None, headers=None):
        self.calls.append({"url": url, "data": dict(data or {})})
        return FakeResponse(self.payload, self.status_code)

    def close(self):
        self.closed = True


class BoomHTTP:
    """Any network use is a hard failure — proves presence checks stay offline."""

    def post(self, *a, **k):  # pragma: no cover - must never be reached
        raise AssertionError("network refresh attempted during a presence-only check")


class FakeSecrets:
    """In-memory SecretsManager stand-in (get/set/set_oauth/get_oauth/delete)."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def set(self, name, value, kind="generic", description=""):
        self.store[name] = value
        return {"name": name, "kind": kind}

    def get(self, name):
        return self.store.get(name)

    def set_oauth(self, name, token, description=""):
        self.store[name] = json.dumps(token)
        return {"name": name, "kind": "oauth"}

    def get_oauth(self, name):
        raw = self.store.get(name)
        return json.loads(raw) if raw is not None else None

    def delete(self, name):
        return self.store.pop(name, None) is not None


def _oauth_app(provider):
    return {
        "client_id": "client-123.apps.googleusercontent.com",
        "client_secret": "shh-secret",
        "redirect_uri": "http://localhost:8765/oauth/google/callback",
    }


# --- fixtures ------------------------------------------------------------


@pytest.fixture
def engine(tmp_path):
    e = make_engine(str(tmp_path / "t.db"))
    init_db(e)
    return e


@pytest.fixture
def secrets():
    return FakeSecrets()


def _registry(engine, secrets, http):
    return ConnectionRegistry(
        engine, secrets, http_factory=lambda: http, oauth_app=_oauth_app
    )


_GEMINI_OK = {
    "candidates": [
        {"content": {"role": "model", "parts": [{"text": "hi"}]}, "finishReason": "STOP"}
    ]
}


# --- Finding 6: Google credential header --------------------------------


async def test_google_oauth_sends_authorization_bearer():
    http = FakeAsyncHTTP(_GEMINI_OK)
    adapter = GoogleAdapter(api_key="ya29.access-token", http=http, oauth=True)
    await adapter.complete(
        system="", messages=[LLMMessage(role="user", content="hi")], tools=[]
    )
    assert http.last["headers"]["Authorization"] == "Bearer ya29.access-token"
    # the api_key header must NOT be sent for an OAuth credential
    assert "x-goog-api-key" not in http.last["headers"]


async def test_google_api_key_still_sends_x_goog_api_key():
    http = FakeAsyncHTTP(_GEMINI_OK)
    adapter = GoogleAdapter(api_key="g-test", http=http)  # oauth defaults False
    await adapter.complete(
        system="", messages=[LLMMessage(role="user", content="hi")], tools=[]
    )
    assert http.last["headers"]["x-goog-api-key"] == "g-test"
    assert "Authorization" not in http.last["headers"]


# --- Finding 7: failed token exchange must not "connect" -----------------


def test_complete_oauth_raises_on_error_body_and_does_not_connect(engine, secrets):
    http = FakeSyncHTTP({"error": "invalid_grant", "error_description": "bad code"}, 400)
    registry = _registry(engine, secrets, http)
    state = registry.start_oauth("google")["state"]

    with pytest.raises(ValueError):
        registry.complete_oauth("google", code="abc", state=state)

    # nothing was persisted and the provider is NOT connected
    assert secrets.get_oauth("google_oauth") is None
    by_provider = {s["provider"]: s for s in registry.status()}
    assert by_provider["google"]["connected"] is False
    assert by_provider["google"]["status"] != "connected"


def test_complete_oauth_raises_on_missing_access_token(engine, secrets):
    http = FakeSyncHTTP({"token_type": "Bearer", "expires_in": 3600}, 200)  # no token
    registry = _registry(engine, secrets, http)
    state = registry.start_oauth("google")["state"]

    with pytest.raises(ValueError):
        registry.complete_oauth("google", code="abc", state=state)
    assert secrets.get_oauth("google_oauth") is None


def test_exchange_code_raises_on_http_error():
    from iron_jarvis.connections import OAuthClient
    from iron_jarvis.connections.specs import BUILTIN_SPECS

    http = FakeSyncHTTP({"error": "invalid_client"}, 401)
    with pytest.raises(ValueError):
        OAuthClient.exchange_code(
            BUILTIN_SPECS["google"],
            code="c",
            code_verifier="v",
            client_id="id",
            client_secret="sec",
            redirect_uri="uri",
            http=http,
        )


def test_refresh_raises_on_error_body():
    from iron_jarvis.connections import OAuthClient
    from iron_jarvis.connections.specs import BUILTIN_SPECS

    http = FakeSyncHTTP({"error": "invalid_grant"}, 400)
    with pytest.raises(ValueError):
        OAuthClient.refresh(
            BUILTIN_SPECS["google"],
            refresh_token="rt",
            client_id="id",
            client_secret="sec",
            http=http,
        )


# --- Finding 8: presence-only availability (no network refresh) ----------


def test_has_credential_oauth_presence_only_no_refresh(engine, secrets):
    # An expired token WITH a refresh_token would normally trigger a refresh —
    # has_credential must report presence WITHOUT touching the network.
    secrets.set_oauth(
        "google_oauth",
        {
            "access_token": "stale",
            "refresh_token": "rt",
            "expires_at": "2000-01-01T00:00:00+00:00",  # long expired
        },
    )
    registry = _registry(engine, secrets, BoomHTTP())
    assert registry.has_credential("google") is True  # no AssertionError from BoomHTTP


def test_has_credential_false_when_absent(engine, secrets):
    registry = _registry(engine, secrets, BoomHTTP())
    assert registry.has_credential("google") is False  # oauth, nothing stored
    assert registry.has_credential("anthropic") is False  # api_key, nothing stored


def test_has_credential_api_key_presence(engine, secrets):
    registry = _registry(engine, secrets, BoomHTTP())
    registry.set_api_key("anthropic", "sk-x")
    assert registry.has_credential("anthropic") is True


def test_provider_manager_availability_is_presence_only(engine, secrets):
    # Expired token present -> available True via presence resolver, no refresh.
    secrets.set_oauth(
        "google_oauth",
        {"access_token": "stale", "refresh_token": "rt",
         "expires_at": "2000-01-01T00:00:00+00:00"},
    )
    registry = _registry(engine, secrets, BoomHTTP())
    pm = ProviderManager(
        credential_resolver=registry.credential,  # would refresh if used
        presence_resolver=registry.has_credential,  # but availability uses this
    )
    # Must not raise (BoomHTTP) — i.e. availability never refreshed.
    assert pm.available("google") is True
    assert pm.available("openai") is False
    assert pm.available("mock") is True
    # health() also stays presence-only
    rows = {r["provider"]: r for r in pm.health()}
    assert rows["google"]["available"] is True
