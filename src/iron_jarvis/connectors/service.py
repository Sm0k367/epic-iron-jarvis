"""Connector Marketplace service — turn a catalog entry into a live connection.

Dispatches by ``connect_via``:

* ``mcp``     — collect the connector's fields, store secret fields in the vault,
  add the MCP server (env tokens injected from the vault via ``env_secrets``),
  and hot-load its tools.
* ``oauth``   — start the OAuth flow through the :class:`ConnectionRegistry`.
* ``api_key`` — store the key through the registry.

:func:`list_connectors` returns the catalog annotated with each connector's LIVE
status. Everything is platform-based (no ``d`` deps object) so it is callable
from routes and tests alike. No secret value is ever returned.
"""

from __future__ import annotations

from typing import Any

from ..core.config import persist_config_values
from ..mcp.tools import mcp_tools
from .catalog import CATALOG, connector_dict, get_connector


def _mcp_servers(platform) -> list[dict]:
    return list(getattr(platform.config, "mcp_servers", None) or [])


def _server_cfg(platform, connector_id: str) -> "dict | None":
    return next((s for s in _mcp_servers(platform) if s.get("name") == connector_id), None)


def _status_for(platform, connector, conn_status: dict) -> dict[str, Any]:
    if connector.connect_via == "mcp":
        connected = _server_cfg(platform, connector.id) is not None
        loaded = platform.registry.mcp_names(connector.id) if connected else []
        return {
            "connected": connected,
            "status": "connected" if connected else "disconnected",
            "tools_loaded": len(loaded),
            "tool_names": [n.split("__", 2)[-1] for n in loaded],
            "account": "",
        }
    st = conn_status.get(connector.provider)
    if st:
        return {
            "connected": bool(st.get("connected")),
            "status": st.get("status", "disconnected"),
            "tools_loaded": 0,
            "account": st.get("account", ""),
        }
    return {"connected": False, "status": "disconnected", "tools_loaded": 0, "account": ""}


def list_connectors(platform) -> list[dict[str, Any]]:
    """The full catalog, each entry annotated with its live status. No secrets."""
    try:
        conn_status = {c["provider"]: c for c in platform.connections.status()}
    except Exception:  # noqa: BLE001 — a broken registry shouldn't blank the gallery
        conn_status = {}
    return [{**connector_dict(c), **_status_for(platform, c, conn_status)} for c in CATALOG]


# --------------------------------------------------------------------------- #
# Connect / test / disconnect.
# --------------------------------------------------------------------------- #
def connect(platform, connector_id: str, values: dict[str, Any] | None = None) -> dict[str, Any]:
    connector = get_connector(connector_id)
    if connector is None:
        raise KeyError(connector_id)
    values = values or {}
    if connector.connect_via == "mcp":
        return _connect_mcp(platform, connector, values)
    if connector.connect_via == "api_key":
        return _connect_api_key(platform, connector, values)
    if connector.connect_via == "oauth":
        return _connect_oauth(platform, connector)
    raise ValueError(f"unknown connect_via '{connector.connect_via}'")


def _secret_name(connector_id: str, field_name: str) -> str:
    return f"conn_{connector_id}_{field_name.lower()}"


def _connect_mcp(platform, connector, values: dict[str, Any]) -> dict[str, Any]:
    missing = [
        f.label
        for f in connector.fields
        if not f.optional and not str(values.get(f.name, "")).strip()
    ]
    if missing:
        raise ValueError("missing required field(s): " + ", ".join(missing))

    args = list(connector.args)
    env: dict[str, str] = {}
    env_secrets: dict[str, str] = {}
    for f in connector.fields:
        val = str(values.get(f.name, "")).strip()
        if not val:
            continue
        if f.kind == "arg":
            args = [a.replace(f"<{f.name}>", val) for a in args]
        elif f.kind == "env":
            env[f.name] = val
        else:  # secret → vault, injected as an env var at launch
            sname = _secret_name(connector.id, f.name)
            platform.secrets.set(sname, val)
            env_secrets[f.name] = sname

    cfg: dict[str, Any] = {"name": connector.id, "command": connector.command, "args": args}
    if env:
        cfg["env"] = env
    if env_secrets:
        cfg["env_secrets"] = env_secrets

    # Persist (replacing any prior config for this connector), then hot-load.
    servers = [s for s in _mcp_servers(platform) if s.get("name") != connector.id]
    servers.append(cfg)
    platform.config.mcp_servers = servers
    persist_config_values(platform.config.home, {"mcp_servers": servers})

    loaded = 0
    try:
        for tool in mcp_tools([cfg], secret_resolver=platform.secrets.get):
            platform.registry.register(tool, mcp=True)
            loaded += 1
    except Exception:  # noqa: BLE001 — persisted config still loads on restart
        loaded = 0
    return {
        "ok": True,
        "connector": connector.id,
        "tools_loaded": loaded,
        "note": None if loaded else "saved — restart the daemon (or check the command is installed) to load its tools",
    }


def _connect_api_key(platform, connector, values: dict[str, Any]) -> dict[str, Any]:
    key = str(values.get("key") or values.get("api_key") or "").strip()
    if not key:
        raise ValueError("an API key is required")
    platform.connections.set_api_key(connector.provider, key)
    return {"ok": True, "connector": connector.id}


def _connect_oauth(platform, connector) -> dict[str, Any]:
    info = platform.connections.start_oauth(connector.provider)
    return {"ok": True, "connector": connector.id, "oauth": info}


def test(platform, connector_id: str) -> dict[str, Any]:
    connector = get_connector(connector_id)
    if connector is None:
        raise KeyError(connector_id)
    if connector.connect_via == "mcp":
        cfg = _server_cfg(platform, connector.id)
        if cfg is None:
            return {"ok": False, "error": "not connected yet"}
        try:
            tools = mcp_tools([cfg], secret_resolver=platform.secrets.get)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "tools": []}
        names = [t.name.split("__", 2)[-1] for t in tools]
        return {
            "ok": bool(tools),
            "count": len(tools),
            "tools": names,
            "error": None if tools else "connected but advertised no tools",
        }
    return platform.connections.test(connector.provider)


def disconnect(platform, connector_id: str) -> dict[str, Any]:
    connector = get_connector(connector_id)
    if connector is None:
        raise KeyError(connector_id)
    if connector.connect_via == "mcp":
        servers = _mcp_servers(platform)
        removed = _server_cfg(platform, connector.id)
        kept = [s for s in servers if s.get("name") != connector.id]
        platform.config.mcp_servers = kept
        persist_config_values(platform.config.home, {"mcp_servers": kept})
        for name in platform.registry.mcp_names(connector.id):
            platform.registry.unregister(name)
        if removed:  # drop the vault secrets we minted for it
            for sname in (removed.get("env_secrets") or {}).values():
                try:
                    platform.secrets.delete(sname)
                except Exception:  # noqa: BLE001
                    pass
        return {"ok": True, "disconnected": connector.id}
    platform.connections.disconnect(connector.provider)
    return {"ok": True, "disconnected": connector.id}
