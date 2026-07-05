"""/chat: '/' skill invocation + '+' armed-tool loop."""
from __future__ import annotations

from fastapi.testclient import TestClient

from iron_jarvis.daemon.app import create_app


def _app(tmp_path):
    sd = tmp_path / ".ironjarvis" / "skills" / "greeter"
    sd.mkdir(parents=True)
    (sd / "SKILL.md").write_text(
        "---\nname: greeter\ndescription: greet warmly\n---\nSLASH-MARKER-9 greet warmly.",
        encoding="utf-8",
    )
    return TestClient(create_app(str(tmp_path)))


def test_slash_skill_injected(tmp_path, monkeypatch):
    client = _app(tmp_path)
    captured = {}
    platform = client.app.state.platform
    real_get = platform.providers.get

    def spy(p, m=None):
        a = real_get(p, m)
        rc = a.complete

        async def c(*, system, messages, tools):
            captured["system"] = system
            captured["tools"] = tools
            return await rc(system=system, messages=messages, tools=tools)

        a.complete = c
        return a

    monkeypatch.setattr(platform.providers, "get", spy)
    r = client.post("/chat", json={"messages": [{"role": "user", "content": "hi"}],
                                   "skill": "greeter"})
    assert r.status_code == 200 and r.json()["skill"] == "greeter"
    assert "SLASH-MARKER-9" in captured["system"]
    assert client.post("/chat", json={"messages": [{"role": "user", "content": "x"}],
                                      "skill": "ghost"}).status_code == 404


def test_armed_tools_reach_model_and_unknown_skipped(tmp_path, monkeypatch):
    client = _app(tmp_path)
    captured = {}
    platform = client.app.state.platform
    real_get = platform.providers.get

    def spy(p, m=None):
        a = real_get(p, m)
        rc = a.complete

        async def c(*, system, messages, tools):
            captured["tools"] = tools
            captured["system"] = system
            return await rc(system=system, messages=messages, tools=tools)

        a.complete = c
        return a

    monkeypatch.setattr(platform.providers, "get", spy)
    r = client.post("/chat", json={
        "messages": [{"role": "user", "content": "list stuff"}],
        "tools": ["list_folder", "definitely_not_a_tool"],
    })
    assert r.status_code == 200
    names = [t.get("name") for t in captured["tools"]]
    assert names == ["list_folder"]  # armed + unknown skipped
    assert "armed these tools" in captured["system"]
    assert r.json()["tools_used"] == []  # mock returns no tool_calls
