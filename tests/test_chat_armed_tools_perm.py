"""Armed chat tools with a GROUPED permission key must actually execute.

R-2 regression: the chat tool loop auto-allowed armed tools keyed by tool NAME,
but the permission engine authorizes on ``tool.perm_key()``. For grouped tools
(pixio_*, view_image / image_*, mcp_*) whose perm_key differs from the name, the
name-only override never matched, so an ARMED tool was silently DENIED. Here we
arm ``image_info`` (name ``image_info``, perm_key ``images`` — NOT in the base
policy, so it defaults to fail-closed ASK) and assert it runs.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from iron_jarvis.daemon.app import create_app
from iron_jarvis.providers.adapters.base import LLMResponse, ToolCall
from iron_jarvis.providers.router import RouteResult


def _png(path) -> None:
    from PIL import Image

    Image.new("RGB", (2, 2), (255, 0, 0)).save(path, format="PNG")


def test_armed_grouped_perm_tool_executes(tmp_path, monkeypatch):
    # image_info has perm_key "images" != its name — the exact mismatch R-2 hit.
    root = tmp_path / "work"
    root.mkdir()
    img = root / "pic.png"
    _png(img)

    client = TestClient(create_app(str(tmp_path)))
    pid = client.post("/projects", json={"name": "Img", "root": str(root)}).json()["id"]
    platform = client.app.state.platform

    seen = {"round2": ""}
    n = {"i": 0}

    async def fake_complete(*, provider=None, model=None, system, messages, tools, task_class):
        n["i"] += 1
        if n["i"] == 1:
            # Round 1: the model asks to inspect the image via the ARMED tool.
            # Note: the model returns NO text here, exercising the no-reply path.
            return RouteResult(
                LLMResponse(
                    text="",
                    tool_calls=[
                        ToolCall(id="i1", name="image_info", arguments={"path": str(img)})
                    ],
                ),
                "mock",
                "mock",
            )
        # Round 2: the tool result is now in the transcript.
        seen["round2"] = " ".join((m.content or "") for m in messages if m.role == "tool")
        return RouteResult(LLMResponse(text="Looked at it."), "mock", "mock")

    monkeypatch.setattr(platform.router, "complete", fake_complete)

    r = client.post(
        "/chat",
        json={
            "messages": [{"role": "user", "content": "inspect pic.png"}],
            "project_id": pid,
            "tools": ["image_info"],
        },
    )
    assert r.status_code == 200
    body = r.json()

    # It EXECUTED: the round-2 tool message carries the real Pillow output
    # (format/dimensions), NOT a permission/denied string.
    assert "PNG" in seen["round2"] and "2x2" in seen["round2"]
    assert "permission denied" not in seen["round2"].lower()
    assert "denied" not in seen["round2"].lower()

    # Honesty: a tool that really ran is counted in tools_used.
    assert "image_info" in (body.get("tools_used") or [])


def test_no_reply_synthesized_from_tool_output(tmp_path, monkeypatch):
    """When the model returns no final text but a tool ran, the reply is an
    honest summary of the tool result — not the bare "(no reply)" placeholder."""
    root = tmp_path / "w2"
    root.mkdir()
    img = root / "p.png"
    _png(img)

    client = TestClient(create_app(str(tmp_path)))
    pid = client.post("/projects", json={"name": "I2", "root": str(root)}).json()["id"]
    platform = client.app.state.platform
    n = {"i": 0}

    async def fake_complete(*, provider=None, model=None, system, messages, tools, task_class):
        n["i"] += 1
        if n["i"] == 1:
            return RouteResult(
                LLMResponse(
                    text="",
                    tool_calls=[
                        ToolCall(id="i1", name="image_info", arguments={"path": str(img)})
                    ],
                ),
                "mock",
                "mock",
            )
        # Round 2: the model STILL returns nothing.
        return RouteResult(LLMResponse(text=""), "mock", "mock")

    monkeypatch.setattr(platform.router, "complete", fake_complete)

    r = client.post(
        "/chat",
        json={
            "messages": [{"role": "user", "content": "inspect p.png"}],
            "project_id": pid,
            "tools": ["image_info"],
        },
    )
    assert r.status_code == 200
    reply = r.json().get("reply") or ""
    assert reply != "(no reply)"
    # The synthesized summary quotes the real tool output.
    assert "PNG" in reply and "2x2" in reply
