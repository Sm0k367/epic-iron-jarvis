"""Regression tests for webhook security fixes.

F2 (SSRF): outbound webhook targets are validated against internal/loopback/
metadata addresses before any network call, with re-validation at delivery
time to defeat DNS rebinding.

F4 (replay): inbound webhooks gain an opt-in timestamped-signature path with a
freshness window and a seen-signature cache, while the legacy body-only verify
path stays intact for existing callers.

Fully offline: ``socket.getaddrinfo`` is monkeypatched so no real DNS is hit.
"""

from __future__ import annotations

import socket
import time

import pytest

# Register the WebhookRecord table BEFORE init_db creates the schema.
import iron_jarvis.webhooks.models  # noqa: F401

from iron_jarvis.core.db import init_db, make_engine
from iron_jarvis.core.events import Event, EventType
from iron_jarvis.webhooks.inbound import InboundWebhooks
from iron_jarvis.webhooks.outbound import OutboundWebhooks
from iron_jarvis.webhooks.security import sign, sign_v2, verify, verify_signed
from iron_jarvis.webhooks.validate import assert_safe_webhook_url


def _engine(tmp_path):
    engine = make_engine(tmp_path / "webhooks.db")
    init_db(engine)
    return engine


def _fake_getaddrinfo(ip: str):
    """Return a getaddrinfo stub that always resolves to ``ip``."""

    def _gai(host, port, *args, **kwargs):
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port or 0))]

    return _gai


# --- F2: assert_safe_webhook_url ---------------------------------------------


def test_assert_rejects_non_http_scheme():
    with pytest.raises(ValueError):
        assert_safe_webhook_url("ftp://example.com/x")
    with pytest.raises(ValueError):
        assert_safe_webhook_url("file:///etc/passwd")


def test_assert_rejects_missing_host():
    with pytest.raises(ValueError):
        assert_safe_webhook_url("http:///nohost")


def test_assert_rejects_metadata_loopback_and_rfc1918():
    # IP literals don't need DNS, but block getaddrinfo anyway to stay offline.
    for bad in ("http://169.254.169.254/", "http://127.0.0.1/", "http://10.0.0.1/"):
        with pytest.raises(ValueError):
            assert_safe_webhook_url(bad)


def test_assert_allows_public_host(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    # Must not raise.
    assert_safe_webhook_url("https://example.com/hook")


def test_assert_blocks_host_resolving_to_internal(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("10.1.2.3"))
    with pytest.raises(ValueError):
        assert_safe_webhook_url("https://rebind.evil/hook")


def test_assert_allow_internal_bypasses_resolution(monkeypatch):
    def _boom(*a, **k):  # pragma: no cover - must not be called
        raise AssertionError("getaddrinfo should not run when allow_internal")

    monkeypatch.setattr(socket, "getaddrinfo", _boom)
    assert_safe_webhook_url("http://127.0.0.1/", allow_internal=True)


def test_assert_unresolvable_host_is_allowed(monkeypatch):
    def _gai(*a, **k):
        raise socket.gaierror("name resolution failed")

    monkeypatch.setattr(socket, "getaddrinfo", _gai)
    # No internal IP reachable, so not treated as an SSRF block.
    assert_safe_webhook_url("https://does-not-resolve.invalid/hook")


# --- F2: OutboundWebhooks.register / on_event --------------------------------


def test_register_blocks_internal_url(tmp_path):
    out = OutboundWebhooks(_engine(tmp_path), lambda u, p, h: None)
    with pytest.raises(ValueError):
        out.register("evil", "http://169.254.169.254/", ["session.completed"])


def test_register_allow_internal_permits_loopback(tmp_path):
    posted: list[str] = []
    out = OutboundWebhooks(
        _engine(tmp_path),
        lambda u, p, h: posted.append(u),
        allow_internal=True,
    )
    out.register("local", "http://127.0.0.1/hook", ["session.completed"])
    out.on_event(Event(type=EventType.SESSION_COMPLETED, payload={}))
    assert posted == ["http://127.0.0.1/hook"]


def test_register_default_allows_public(monkeypatch, tmp_path):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    out = OutboundWebhooks(_engine(tmp_path), lambda u, p, h: None)
    # Must not raise.
    out.register("ok", "https://example.com/hook", ["session.completed"])


def test_on_event_revalidates_and_skips_rebound_target(tmp_path):
    """A row that becomes internal at delivery time is blocked, not POSTed."""
    posted: list[str] = []
    out = OutboundWebhooks(
        _engine(tmp_path),
        lambda u, p, h: posted.append(u),
        allow_internal=True,  # so register() accepts the loopback URL
    )
    out.register("rebind", "http://127.0.0.1/hook", ["session.completed"])

    # Now flip the instance to enforce: delivery-time re-validation must block.
    out.allow_internal = False
    deliveries = out.on_event(Event(type=EventType.SESSION_COMPLETED, payload={}))

    assert posted == []  # never POSTed
    assert len(deliveries) == 1
    assert deliveries[0]["blocked"] is True
    assert "127.0.0.1" in deliveries[0]["error"]


# --- F4: v2 timestamped signatures + replay ----------------------------------


def test_verify_signed_roundtrip_and_skew():
    payload = b'{"a":1}'
    secret = "s3cr3t"
    ts = int(time.time())
    sig = sign_v2(ts, payload, secret)

    assert verify_signed(ts, payload, secret, sig) is True
    assert verify_signed(ts, payload, secret, "sha256=" + sig) is True
    assert verify_signed(ts, payload, secret, "deadbeef") is False
    assert verify_signed(ts, payload, secret, None) is False
    assert verify_signed(None, payload, secret, sig) is False
    # Stale timestamp outside the window is rejected.
    assert verify_signed(ts - 10_000, payload, secret, sig) is False
    # No secret -> unauthenticated, accept.
    assert verify_signed(ts, payload, "", None) is True


async def test_inbound_v2_replay_rejected(tmp_path):
    inbound = InboundWebhooks(_engine(tmp_path))
    inbound.register("secure", lambda b: {"ok": True, "got": b}, secret="topsecret")

    raw = b'{"hello":"world"}'
    body = {"hello": "world"}
    ts = int(time.time())
    sig = sign_v2(ts, raw, "topsecret")

    first = await inbound.dispatch(
        "secure", body, raw=raw, signature=sig, timestamp=ts
    )
    assert first == {"ok": True, "got": body}

    # Same signature again -> replay rejected.
    second = await inbound.dispatch(
        "secure", body, raw=raw, signature=sig, timestamp=ts
    )
    assert second["ok"] is False
    assert "replay" in second["error"]


async def test_inbound_v2_bad_or_stale_rejected(tmp_path):
    inbound = InboundWebhooks(_engine(tmp_path))
    inbound.register("secure", lambda b: {"ok": True}, secret="topsecret")
    raw = b'{"hello":"world"}'
    body = {"hello": "world"}

    bad = await inbound.dispatch(
        "secure", body, raw=raw, signature="nope", timestamp=int(time.time())
    )
    assert bad["ok"] is False and "signature" in bad["error"]

    ts = int(time.time()) - 10_000
    sig = sign_v2(ts, raw, "topsecret")
    stale = await inbound.dispatch(
        "secure", body, raw=raw, signature=sig, timestamp=ts
    )
    assert stale["ok"] is False and "signature" in stale["error"]


async def test_inbound_legacy_body_only_path_still_works(tmp_path):
    """No timestamp -> legacy verify() path, unchanged behavior."""
    inbound = InboundWebhooks(_engine(tmp_path))
    inbound.register("secure", lambda b: {"ok": True, "got": b}, secret="topsecret")
    raw = b'{"hello":"world"}'
    body = {"hello": "world"}

    good = sign(raw, "topsecret")
    ok = await inbound.dispatch("secure", body, raw=raw, signature=good)
    assert ok == {"ok": True, "got": body}
    # Legacy path has no replay cache; a repeat still succeeds.
    again = await inbound.dispatch("secure", body, raw=raw, signature=good)
    assert again == {"ok": True, "got": body}


def test_legacy_verify_unchanged():
    payload = b'{"hello":"world"}'
    assert verify(payload, "s", sign(payload, "s")) is True
    assert verify(payload, "", None) is True
