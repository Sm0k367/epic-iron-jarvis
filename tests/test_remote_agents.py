"""Remote agents (run elsewhere) + dynamic-agent CRUD.

Offline: httpx.AsyncClient.post is monkeypatched to canned 200s, so nothing
touches the network. Covers vault storage (token never leaked back), the
test/run probes for BOTH kinds, LAN-url acceptance (the user's own box is
allowed), delete-removes-secret, and the dynamic-agent delete/patch/blank-name
routes.
"""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from iron_jarvis.daemon.app import create_app


class _FakeResp:
    def __init__(self, status_code: int, payload, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


def _install_fake_post(monkeypatch, captured: dict) -> None:
    async def fake_post(self, url, json=None, headers=None, **kw):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers or {}
        if json and "messages" in json:  # openai-chat shape
            return _FakeResp(
                200, {"choices": [{"message": {"content": "openai-said-ok"}}]}
            )
        return _FakeResp(200, {"result": "http-said-ok"})  # http-task shape

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)


def _client(tmp_path):
    return TestClient(create_app(str(tmp_path)))


# --- registration: secret vaulted, token never leaked back ---------------------


def test_add_remote_vaults_token_and_list_omits_it(tmp_path):
    client = _client(tmp_path)
    r = client.post(
        "/agents/remote",
        json={
            "name": "hermes",
            "base_url": "http://192.168.1.50:8080",  # the user's OWN LAN box
            "kind": "http-task",
            "token": "sekret-123",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "hermes"
    assert body["has_credential"] is True
    # LAN base_url is ACCEPTED (explicitly registered, not an SSRF target).
    assert body["base_url"] == "http://192.168.1.50:8080"
    assert "token" not in body and "sekret" not in str(body)

    # The token is really in the vault under the derived secret name...
    secrets = client.app.state.platform.secrets
    assert secrets.get("remote_agent_hermes") == "sekret-123"

    # ...but the listing surface never returns it.
    agents = client.get("/agents/remote").json()["agents"]
    assert len(agents) == 1
    assert "sekret" not in str(agents[0])
    assert agents[0]["has_credential"] is True


def test_add_remote_rejects_bad_input(tmp_path):
    client = _client(tmp_path)
    assert client.post("/agents/remote", json={"name": "", "base_url": "http://x"}).status_code == 400
    assert client.post("/agents/remote", json={"name": "ok", "base_url": ""}).status_code == 400
    assert (
        client.post(
            "/agents/remote", json={"name": "ok", "base_url": "http://x", "kind": "bogus"}
        ).status_code
        == 400
    )


# --- test + run probes for BOTH kinds -----------------------------------------


def test_run_and_test_http_task(tmp_path, monkeypatch):
    captured: dict = {}
    _install_fake_post(monkeypatch, captured)
    client = _client(tmp_path)
    client.post(
        "/agents/remote",
        json={"name": "box", "base_url": "http://192.168.1.9:9000/run", "kind": "http-task", "token": "t"},
    )
    # test() probe
    t = client.post("/agents/remote/box/test")
    assert t.status_code == 200 and t.json()["ok"] is True
    # run() relays {result}
    r = client.post("/agents/remote/box/run", json={"task": "do it"})
    assert r.status_code == 200, r.text
    assert r.json()["result"] == "http-said-ok"
    assert captured["json"] == {"task": "do it"}
    assert captured["headers"].get("Authorization") == "Bearer t"


def test_run_openai_chat(tmp_path, monkeypatch):
    captured: dict = {}
    _install_fake_post(monkeypatch, captured)
    client = _client(tmp_path)
    client.post(
        "/agents/remote",
        json={
            "name": "gpt",
            "base_url": "http://192.168.1.10:1234/v1",
            "kind": "openai-chat",
            "model": "local-model",
        },
    )
    r = client.post("/agents/remote/gpt/run", json={"task": "hi"})
    assert r.status_code == 200, r.text
    assert r.json()["result"] == "openai-said-ok"
    # base_url got /chat/completions appended; body is an OpenAI chat payload.
    assert captured["url"] == "http://192.168.1.10:1234/v1/chat/completions"
    assert captured["json"]["model"] == "local-model"
    assert captured["json"]["messages"] == [{"role": "user", "content": "hi"}]


def test_run_fail_closed_on_non_2xx(tmp_path, monkeypatch):
    async def fake_post(self, url, json=None, headers=None, **kw):
        return _FakeResp(503, None, text="upstream down")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    client = _client(tmp_path)
    client.post(
        "/agents/remote",
        json={"name": "down", "base_url": "http://192.168.1.5:80/run", "kind": "http-task"},
    )
    r = client.post("/agents/remote/down/run", json={"task": "x"})
    assert r.status_code == 424  # honest failed-dependency, not a fake success
    assert "503" in r.json()["detail"]


# --- delete removes the agent AND its vault secret -----------------------------


def test_delete_remote_removes_agent_and_secret(tmp_path):
    client = _client(tmp_path)
    client.post(
        "/agents/remote",
        json={"name": "gone", "base_url": "http://192.168.1.1:8080", "kind": "http-task", "token": "zap"},
    )
    secrets = client.app.state.platform.secrets
    assert secrets.get("remote_agent_gone") == "zap"

    d = client.delete("/agents/remote/gone")
    assert d.status_code == 200 and d.json()["removed"] == "gone"
    assert secrets.get("remote_agent_gone") is None
    assert client.get("/agents/remote").json()["agents"] == []
    # A second delete 404s.
    assert client.delete("/agents/remote/gone").status_code == 404


# --- dynamic-agent CRUD --------------------------------------------------------


def test_dynamic_agent_delete_and_404(tmp_path):
    client = _client(tmp_path)
    client.post(
        "/agents",
        json={"name": "helper", "system_prompt": "help", "tools": ["read_file"]},
    )
    names = [a["name"] for a in client.get("/agents").json()["dynamic"]]
    assert "helper" in names
    assert client.delete("/agents/helper").status_code == 200
    assert "helper" not in [a["name"] for a in client.get("/agents").json()["dynamic"]]
    assert client.delete("/agents/helper").status_code == 404


def test_dynamic_agent_patch(tmp_path):
    client = _client(tmp_path)
    client.post(
        "/agents",
        json={"name": "edith", "system_prompt": "v1", "tools": ["a"], "description": "d1"},
    )
    r = client.patch("/agents/edith", json={"description": "d2", "system_prompt": "v2"})
    assert r.status_code == 200 and r.json()["description"] == "d2"
    rec = client.app.state.platform.agents_registry.get("edith")
    assert rec.system_prompt == "v2" and rec.description == "d2"
    # tools untouched (not provided in the patch)
    import json as _json

    assert _json.loads(rec.tools_json) == ["a"]
    assert client.patch("/agents/nope", json={"description": "x"}).status_code == 404


def test_create_agent_blank_name_rejected(tmp_path):
    client = _client(tmp_path)
    assert client.post("/agents", json={"name": "   ", "system_prompt": "x", "tools": []}).status_code == 400
