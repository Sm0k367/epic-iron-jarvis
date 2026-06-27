"""Daemon endpoints: file upload, settings, diagnostics."""

from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from iron_jarvis.daemon.app import create_app


def test_documents_upload(tmp_path):
    client = TestClient(create_app(str(tmp_path)))
    content = base64.b64encode(b"hello upload").decode()
    r = client.post(
        "/documents/upload", json={"filename": "a b/c.txt", "content_b64": content}
    )
    assert r.status_code == 200
    data = r.json()
    assert data["bytes"] == len(b"hello upload")
    assert "uploads" in data["path"]
    assert "/" not in data["name"] and " " not in data["name"]  # sanitized


def test_settings_get_and_put(tmp_path):
    client = TestClient(create_app(str(tmp_path)))
    g = client.get("/settings").json()["settings"]
    assert "default_provider" in g and "self_dev_enabled" in g
    p = client.put(
        "/settings", json={"values": {"max_agent_steps": 7, "not_a_key": 1}}
    )
    assert p.status_code == 200
    assert "max_agent_steps" in p.json()["updated"]
    assert "not_a_key" not in p.json()["updated"]
    assert client.get("/settings").json()["settings"]["max_agent_steps"] == 7


def test_diagnostics(tmp_path):
    client = TestClient(create_app(str(tmp_path)))
    d = client.get("/diagnostics").json()
    assert d["db_integrity"] == "ok"
    assert "running_sessions" in d and "providers" in d
    assert isinstance(d["secrets_key_present"], bool)


def test_settings_rejects_bad_value_and_does_not_brick(tmp_path):
    from iron_jarvis.core.config import load_config

    client = TestClient(create_app(str(tmp_path)))
    r = client.put("/settings", json={"values": {"max_agent_steps": "not-a-number"}})
    assert r.status_code == 400  # validate_assignment rejects the bad type
    # config.toml must remain loadable (the bad value was never persisted).
    cfg = load_config(str(tmp_path))
    assert cfg.max_agent_steps == 12  # untouched default
