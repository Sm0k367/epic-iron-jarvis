"""POST /skills/{name}/apply + DELETE /lessons/{id}."""
from __future__ import annotations

from fastapi.testclient import TestClient

from iron_jarvis.daemon.app import create_app


def test_skill_apply_injects_instructions(tmp_path, monkeypatch):
    sd = tmp_path / ".ironjarvis" / "skills" / "haiku-writer"
    sd.mkdir(parents=True)
    (sd / "SKILL.md").write_text(
        "---\nname: haiku-writer\ndescription: writes haiku\n---\nAPPLY-MARKER-5 always write 5-7-5.",
        encoding="utf-8",
    )
    client = TestClient(create_app(str(tmp_path)))
    captured = {}
    platform = client.app.state.platform
    real_get = platform.providers.get

    def spy(p, m=None):
        a = real_get(p, m)
        rc = a.complete

        async def c(*, system, messages, tools):
            captured["system"] = system
            return await rc(system=system, messages=messages, tools=tools)

        a.complete = c
        return a

    monkeypatch.setattr(platform.providers, "get", spy)
    r = client.post("/skills/haiku-writer/apply", json={"request": "one about spring"})
    assert r.status_code == 200 and r.json()["skill"] == "haiku-writer"
    assert "APPLY-MARKER-5" in captured["system"]
    assert client.post("/skills/ghost/apply", json={"request": "x"}).status_code == 404
    assert client.post("/skills/haiku-writer/apply", json={"request": ""}).status_code == 400


def test_lesson_delete(tmp_path):
    client = TestClient(create_app(str(tmp_path)))
    platform = client.app.state.platform
    from iron_jarvis.learning.models import LessonRecord
    from iron_jarvis.core.db import session_scope

    with session_scope(platform.engine) as db:
        rec = LessonRecord(text="test lesson", scope="user")
        db.add(rec)
        db.commit()
        db.refresh(rec)
        lid = rec.id
    assert client.delete(f"/lessons/{lid}").json()["deleted"] == lid
    assert client.delete(f"/lessons/{lid}").status_code == 404
