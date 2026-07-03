"""POST /terminals/{id}/workflow — turn a terminal session into a workflow."""

from __future__ import annotations

from fastapi.testclient import TestClient

from iron_jarvis.daemon.app import create_app


def test_unknown_terminal_404(tmp_path):
    client = TestClient(create_app(str(tmp_path)))
    r = client.post("/terminals/does-not-exist/workflow", json={})
    assert r.status_code == 404


def test_route_is_registered(tmp_path):
    app = create_app(str(tmp_path))
    paths = {r.path for r in app.routes}
    assert "/terminals/{term_id}/workflow" in paths
