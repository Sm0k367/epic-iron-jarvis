"""Connector Marketplace (CX-01).

A curated, one-tap gallery over everything Iron Jarvis can connect to — MCP
servers, OAuth apps, and API-key services — unifying the MCP catalog, the
ConnectionRegistry, and the vault behind one surface with health, scopes, and a
plain-English 'what this unlocks'.
"""

from __future__ import annotations

from .catalog import CATALOG, CATEGORY_ORDER, Connector, Field, get_connector
from .service import connect, disconnect, list_connectors, test

__all__ = [
    "CATALOG",
    "CATEGORY_ORDER",
    "Connector",
    "Field",
    "get_connector",
    "list_connectors",
    "connect",
    "test",
    "disconnect",
]
