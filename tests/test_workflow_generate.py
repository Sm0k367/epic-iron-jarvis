"""POST /workflows/generate: an agent turns NL into a saved workflow (offline)."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from iron_jarvis.daemon.app import create_app
from iron_jarvis.providers.adapters.base import LLMResponse


class _FakeAdapter:
    def __init__(self, text: str):
        self._text = text

    async def complete(self, *, system, messages, tools):
        return LLMResponse(text=self._text)


def _app_with_reply(tmp_path, text):
    app = create_app(str(tmp_path))
    app.state.platform.providers.get = lambda *a, **k: _FakeAdapter(text)
    return TestClient(app)


_WF = {
    "name": "Daily Report",
    "description": "Compile a daily report",
    "steps": [
        {"name": "Gather", "agent": "researcher", "task": "collect the day's data"},
        {"name": "Write", "agent": "builder", "task": "write the report", "tool": None},
    ],
}


def test_generate_saves_and_returns_workflow(tmp_path):
    client = _app_with_reply(tmp_path, json.dumps(_WF))
    r = client.post("/workflows/generate", json={"description": "a daily report"})
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "daily-report"  # slugified
    assert len(data["steps"]) == 2
    assert data["steps"][0]["agent"] == "researcher"
    assert "reply" in data
    # It was persisted and is loadable in the editor.
    assert client.get("/workflows/daily-report").status_code == 200


def test_generate_tolerates_prose_around_json(tmp_path):
    text = "Sure! Here's your workflow:\n\n" + json.dumps(_WF) + "\n\nHope that helps."
    client = _app_with_reply(tmp_path, text)
    r = client.post("/workflows/generate", json={"description": "x"})
    assert r.status_code == 200 and len(r.json()["steps"]) == 2


def test_generate_bad_agent_coerced_to_builder(tmp_path):
    wf = {"name": "w", "steps": [{"name": "s", "agent": "wizard", "task": "do"}]}
    client = _app_with_reply(tmp_path, json.dumps(wf))
    r = client.post("/workflows/generate", json={"description": "x"})
    assert r.json()["steps"][0]["agent"] == "builder"


def test_generate_422_on_non_json(tmp_path):
    client = _app_with_reply(tmp_path, "I cannot help with that.")
    r = client.post("/workflows/generate", json={"description": "x"})
    assert r.status_code == 422
