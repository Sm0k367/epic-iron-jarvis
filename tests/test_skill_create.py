"""User-authored skills: save_skill + POST /skills (offline)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from iron_jarvis.daemon.app import create_app
from iron_jarvis.skills import load_skill, save_skill, slugify


def test_slugify():
    assert slugify("My Cool Skill!") == "my-cool-skill"
    assert slugify("  ") == "skill"


def test_save_skill_roundtrips(tmp_path):
    d = save_skill(tmp_path, "Weekly Report", "Summarize the week", "Do X then Y.")
    sk = load_skill(d)
    assert sk.name == "Weekly Report"
    assert sk.description == "Summarize the week"
    assert "Do X then Y." in sk.instructions


def test_save_skill_requires_name_and_instructions(tmp_path):
    with pytest.raises(ValueError):
        save_skill(tmp_path, "", "d", "i")
    with pytest.raises(ValueError):
        save_skill(tmp_path, "n", "d", "")


def test_post_skills_creates_and_lists(tmp_path):
    client = TestClient(create_app(str(tmp_path)))
    before = {s["name"] for s in client.get("/skills").json()["skills"]}
    r = client.post(
        "/skills",
        json={"name": "Invoice Chaser", "description": "Nudge late invoices",
              "instructions": "1. Find overdue invoices. 2. Draft a polite nudge."},
    )
    assert r.status_code == 200 and r.json()["created"] is True
    after = client.get("/skills").json()["skills"]
    names = {s["name"] for s in after}
    assert "Invoice Chaser" in names and "Invoice Chaser" not in before
    # And it's viewable with its instructions.
    detail = client.get("/skills/Invoice Chaser").json()
    assert "overdue invoices" in detail["instructions"]


def test_post_skills_rejects_empty(tmp_path):
    client = TestClient(create_app(str(tmp_path)))
    assert client.post("/skills", json={"name": "", "instructions": "x"}).status_code == 400
