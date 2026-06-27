"""MCP client tests (§ external tool consumption). Fully offline — FakeTransport
only; no subprocess is ever spawned and no socket is ever opened.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from iron_jarvis.mcp import FakeTransport, MCPClient, MCPRemoteTool, mcp_tools
from iron_jarvis.tools.base import ToolContext


# --- canned MCP responses -----------------------------------------------------

TOOLS_LIST = {
    "tools": [
        {
            "name": "send_email",
            "description": "Send an email via Gmail.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "subject"],
            },
        },
        {
            "name": "list_inbox",
            "description": "List recent inbox messages.",
            "inputSchema": {"type": "object", "properties": {}},
        },
    ]
}

TOOLS_CALL = {
    "content": [{"type": "text", "text": "queued message 42"}],
    "isError": False,
}


def fake_gmail() -> FakeTransport:
    return FakeTransport({"tools/list": TOOLS_LIST, "tools/call": TOOLS_CALL})


# --- ToolContext fixture (matches tests/test_filesearch.py / test_documents.py) #


@pytest.fixture
def ctx(tmp_path: Path) -> ToolContext:
    return ToolContext(
        workspace=tmp_path,
        session_id="s1",
        agent_run_id="r1",
        config=None,
        event_bus=None,
        engine=None,
    )


# --- (1) list_tools parses a canned tools/list response into tool specs -------


async def test_list_tools_parses_specs():
    client = MCPClient(fake_gmail(), name="gmail")
    specs = await client.list_tools()
    assert [s["name"] for s in specs] == ["send_email", "list_inbox"]
    assert specs[0]["inputSchema"]["required"] == ["to", "subject"]


# --- (2) mcp_tools builds one MCPRemoteTool per remote tool, wired correctly ---


def test_mcp_tools_builds_wrapped_tools():
    configs = [{"name": "gmail", "transport_obj": fake_gmail()}]
    tools = mcp_tools(configs)

    assert len(tools) == 2
    assert all(isinstance(t, MCPRemoteTool) for t in tools)

    names = {t.name for t in tools}
    assert names == {"mcp__gmail__send_email", "mcp__gmail__list_inbox"}

    send = next(t for t in tools if t.name == "mcp__gmail__send_email")
    assert send.permission_key == "mcp_call"
    assert send.perm_key() == "mcp_call"
    # The advertised schema is exactly the remote tool's inputSchema.
    assert send.input_schema == TOOLS_LIST["tools"][0]["inputSchema"]
    # And it surfaces through the model-facing spec under the §19 key.
    assert send.spec()["input_schema"] == TOOLS_LIST["tools"][0]["inputSchema"]


# --- (3) execute() calls tools/call via the transport, returns the text -------


async def test_execute_calls_tool_and_returns_text(ctx):
    transport = fake_gmail()
    configs = [{"name": "gmail", "transport_obj": transport}]
    send = next(t for t in mcp_tools(configs) if t.name == "mcp__gmail__send_email")

    res = await send.execute({"to": "a@b.com", "subject": "hi"}, ctx)

    assert res.ok is True
    assert res.output == "queued message 42"

    # The fake transport actually received a JSON-RPC tools/call with our args.
    call = next(c for c in transport.calls if c[0] == "tools/call")
    assert call[1]["name"] == "send_email"
    assert call[1]["arguments"] == {"to": "a@b.com", "subject": "hi"}


async def test_execute_surfaces_remote_error_without_crashing(ctx):
    transport = FakeTransport(
        {
            "tools/list": {"tools": [{"name": "boom", "inputSchema": {}}]},
            "tools/call": {
                "content": [{"type": "text", "text": "upstream exploded"}],
                "isError": True,
            },
        }
    )
    tool = mcp_tools([{"name": "srv", "transport_obj": transport}])[0]
    res = await tool.execute({}, ctx)
    assert res.ok is False
    assert "upstream exploded" in (res.error or "")


# --- (4) empty / None config -> [] (safe default no-op) -----------------------


def test_mcp_tools_empty_is_noop():
    assert mcp_tools([]) == []
    assert mcp_tools(None) == []


# --- (5) a server whose transport raises on list_tools is skipped -------------


def test_failing_server_is_skipped():
    bad = FakeTransport(raise_on="tools/list")
    good = fake_gmail()
    tools = mcp_tools(
        [
            {"name": "broken", "transport_obj": bad},
            {"name": "gmail", "transport_obj": good},
        ]
    )
    # No exception bubbled; the broken server contributed nothing, the good one
    # contributed its two tools.
    names = {t.name for t in tools}
    assert names == {"mcp__gmail__send_email", "mcp__gmail__list_inbox"}


def test_all_failing_servers_yield_empty():
    bad = FakeTransport(raise_on=True)
    assert mcp_tools([{"name": "broken", "transport_obj": bad}]) == []
