"""LLM Connections — connect providers via API key or OAuth 2.0 + PKCE.

Connecting an LLM must be flawless and clear: choose a provider, hand it an API
key *or* complete a correct OAuth 2.0 + PKCE flow, and it becomes "connected".
Credentials are stored **only** in the encrypted secrets vault — never in
plaintext in the database. This package exposes:

* :class:`ConnectionSpec` — declarative provider descriptor (no secrets).
* :class:`OAuthClient` — PKCE auth-code helper (injected HTTP transport).
* :class:`ConnectionRecord` — persisted connection *state* (no secret values).
* :class:`ConnectionRegistry` — the entry point: set keys, run OAuth, test, etc.
"""

from __future__ import annotations

from .models import ConnectionRecord
from .oauth import OAuthClient
from .registry import ConnectionRegistry
from .specs import BUILTIN_SPECS, ConnectionSpec, generic_oauth_spec

__all__ = [
    "ConnectionRegistry",
    "ConnectionSpec",
    "OAuthClient",
    "ConnectionRecord",
    "BUILTIN_SPECS",
    "generic_oauth_spec",
]
