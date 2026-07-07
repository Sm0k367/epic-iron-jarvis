"""Project folder tasks (POST /projects/{id}/task) + Docker OSType gate."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from iron_jarvis.daemon.app import create_app


def _mk_project(client, tmp_path, with_root=True):
    body = {"name": "Acme"}
    if with_root:
        root = tmp_path / "acme"
        root.mkdir(exist_ok=True)
        body["root"] = str(root)
    return client.post("/projects", json=body).json()


def _wait_done(client, sid, seconds=15):
    deadline = time.time() + seconds
    while time.time() < deadline:
        res = client.get(f"/sessions/{sid}").json()
        status = (res.get("session") or res).get("status", "")
        if status in ("completed", "failed", "cancelled"):
            return status
        time.sleep(0.2)
    return "timeout"


def test_project_task_chat_output_runs_tagged_session(tmp_path):
    # `with` keeps the app loop alive so the _spawn_bg session actually runs
    # (a bare TestClient tears the loop down per-request -> cancelled).
    with TestClient(create_app(str(tmp_path))) as client:
        p = _mk_project(client, tmp_path)
        r = client.post(
            f"/projects/{p['id']}/task",
            json={"text": "summarize this folder", "output": "chat"},
        )
        assert r.status_code == 200
        view = r.json()
        assert view["project_id"] == p["id"]
        assert view["output"] == "chat"
        assert "target_path" not in view
        assert "summary IS the deliverable" in view["task"]
        assert _wait_done(client, view["id"]) == "completed"  # mock runs instantly


def test_project_task_file_output_composes_target(tmp_path):
    with TestClient(create_app(str(tmp_path))) as client:
        p = _mk_project(client, tmp_path)
        r = client.post(
            f"/projects/{p['id']}/task",
            json={"text": "inventory the files", "output": "xlsx", "filename": "inventory"},
        )
        assert r.status_code == 200
        view = r.json()
        assert view["target_path"].endswith("inventory.xlsx")
        assert "write_document" in view["task"] and view["target_path"] in view["task"]
        _wait_done(client, view["id"])  # let the bg session settle before teardown


def test_project_task_guards(tmp_path):
    with TestClient(create_app(str(tmp_path))) as client:
        no_root = client.post("/projects", json={"name": "Rootless"}).json()
        # File deliverable without a folder is refused honestly.
        r = client.post(
            f"/projects/{no_root['id']}/task", json={"text": "report", "output": "pdf"}
        )
        assert r.status_code == 400 and "folder" in r.json()["detail"]
        # Chat output works without a root.
        ok = client.post(
            f"/projects/{no_root['id']}/task", json={"text": "hello", "output": "chat"}
        )
        assert ok.status_code == 200
        _wait_done(client, ok.json()["id"])
        # Bad output value / empty text / unknown project.
        assert (
            client.post(
                f"/projects/{no_root['id']}/task", json={"text": "x", "output": "exe"}
            ).status_code
            == 400
        )
        assert (
            client.post(f"/projects/{no_root['id']}/task", json={"text": "  "}).status_code
            == 400
        )
        assert client.post("/projects/nope/task", json={"text": "x"}).status_code == 404


def test_docker_sandbox_requires_linux_daemon(monkeypatch):
    """A Windows-containers daemon pings fine but can't run the Linux sandbox
    image — available() must say False (this exact lie failed CI)."""
    from iron_jarvis.sandbox.docker_runtime import DockerSandbox
    from iron_jarvis.sandbox.policy import SandboxPolicy

    class FakeClient:
        def __init__(self, os_type):
            self._os = os_type

        def ping(self):
            return True

        def info(self):
            return {"OSType": self._os}

        def close(self):
            pass

    import sys
    import types

    for os_type, expected in (("windows", False), ("linux", True)):
        fake_docker = types.SimpleNamespace(from_env=lambda t=os_type: FakeClient(t))
        monkeypatch.setitem(sys.modules, "docker", fake_docker)
        assert DockerSandbox(SandboxPolicy()).available() is expected
