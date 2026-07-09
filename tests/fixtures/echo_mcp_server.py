"""A minimal, REAL stdio MCP server for end-to-end tests (no network, no deps).

Speaks line-delimited JSON-RPC 2.0 on stdin/stdout exactly as
``iron_jarvis.mcp.client.StdioTransport`` expects:

* ``initialize``               -> capabilities handshake (request/response)
* ``notifications/initialized`` -> notification, no response
* ``tools/list``               -> advertises two tools: ``echo`` and ``add``
* ``tools/call``               -> runs the tool, returns MCP ``content`` blocks

Run as a subprocess: ``python tests/fixtures/echo_mcp_server.py``. It loops until
stdin closes (the transport's ``close()`` terminates the process). Kept dead
simple so a test proves the WHOLE chain — spawn, handshake, list, call — against
a genuine child process rather than a FakeTransport.
"""

from __future__ import annotations

import json
import sys

_TOOLS = [
    {
        "name": "echo",
        "description": "Echo the given text back.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "add",
        "description": "Add two numbers and return the sum.",
        "inputSchema": {
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        },
    },
]


def _text_result(text: str, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _call_tool(name: str, args: dict) -> dict:
    if name == "echo":
        return _text_result(str(args.get("text", "")))
    if name == "add":
        try:
            return _text_result(str(float(args.get("a", 0)) + float(args.get("b", 0))))
        except (TypeError, ValueError):
            return _text_result("add: a and b must be numbers", is_error=True)
    return _text_result(f"unknown tool '{name}'", is_error=True)


def _handle(method: str, params: dict) -> dict:
    if method == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "echo-mcp", "version": "1"},
        }
    if method == "tools/list":
        return {"tools": _TOOLS}
    if method == "tools/call":
        return _call_tool(params.get("name", ""), params.get("arguments") or {})
    return {}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = msg.get("method", "")
        msg_id = msg.get("id")
        # Notifications carry no id and expect no response.
        if msg_id is None:
            continue
        result = _handle(method, msg.get("params") or {})
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": result}) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
