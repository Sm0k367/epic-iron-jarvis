"""Knowledge item viewer/editor: GET full text, PATCH rename + edit (re-embed),
and honest 404 when an item isn't in the addressed project. Offline."""

from __future__ import annotations

from fastapi.testclient import TestClient

from iron_jarvis.daemon.app import create_app


def _client(tmp_path):
    return TestClient(create_app(str(tmp_path)))


def test_get_item_returns_full_text(tmp_path):
    client = _client(tmp_path)
    pid = client.post("/projects", json={"name": "P"}).json()["id"]
    kid = client.post(
        f"/projects/{pid}/knowledge", json={"name": "Note", "text": "grounding fact"}
    ).json()["id"]

    r = client.get(f"/projects/{pid}/knowledge/{kid}")
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "grounding fact"
    assert body["name"] == "Note"
    assert body["kind"] == "note"


def test_patch_renames_and_edits_text(tmp_path):
    client = _client(tmp_path)
    pid = client.post("/projects", json={"name": "P"}).json()["id"]
    kid = client.post(
        f"/projects/{pid}/knowledge", json={"name": "Old", "text": "first"}
    ).json()["id"]

    # Rename only.
    client.patch(f"/projects/{pid}/knowledge/{kid}", json={"name": "New"})
    got = client.get(f"/projects/{pid}/knowledge/{kid}").json()
    assert got["name"] == "New" and got["text"] == "first"

    # Edit text (size follows; re-embeds).
    client.patch(
        f"/projects/{pid}/knowledge/{kid}", json={"text": "second longer body"}
    )
    got = client.get(f"/projects/{pid}/knowledge/{kid}").json()
    assert got["text"] == "second longer body"
    assert got["size"] == len("second longer body")

    # Blanking the text is refused.
    assert (
        client.patch(f"/projects/{pid}/knowledge/{kid}", json={"text": "   "}).status_code
        == 400
    )


def test_foreign_project_id_404s(tmp_path):
    client = _client(tmp_path)
    pid = client.post("/projects", json={"name": "P"}).json()["id"]
    other = client.post("/projects", json={"name": "Other"}).json()["id"]
    kid = client.post(
        f"/projects/{pid}/knowledge", json={"text": "only in P"}
    ).json()["id"]

    # The item exists, but not under `other` — honest 404 (no cross-project leak).
    assert client.get(f"/projects/{other}/knowledge/{kid}").status_code == 404
    assert (
        client.patch(f"/projects/{other}/knowledge/{kid}", json={"name": "x"}).status_code
        == 404
    )
    # A wholly unknown id also 404s.
    assert client.get(f"/projects/{pid}/knowledge/pk_missing").status_code == 404
