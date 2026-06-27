"""Ops & durability: key rotation, event retention, schema versioning, backup."""

from __future__ import annotations

import tarfile
from datetime import timedelta

from sqlmodel import select

from iron_jarvis.core.db import (
    SCHEMA_VERSION,
    get_schema_version,
    init_db,
    make_engine,
    prune_events,
    session_scope,
)
from iron_jarvis.core.ids import new_uid, utcnow
from iron_jarvis.core.models import EventRecord
from iron_jarvis.platform import build_platform


def test_secrets_rotation_preserves_values(tmp_path):
    p = build_platform(str(tmp_path))
    p.secrets.set("anthropic", "sk-secret-123", kind="api_key")
    key_path = p.config.home / "secrets" / ".secrets.key"
    old_key = key_path.read_bytes()

    assert p.secrets.rotate_key() == 1
    assert key_path.read_bytes() != old_key  # key changed
    assert (p.config.home / "secrets" / ".secrets.key.bak").exists()
    assert p.secrets.get("anthropic") == "sk-secret-123"  # still decrypts


def test_vault_rotation_preserves_sessions(tmp_path):
    p = build_platform(str(tmp_path))
    p.vault.store("claude", {"cookies": "abc"})
    assert p.vault.rotate_key() == 1
    assert p.vault.load("claude") == {"cookies": "abc"}


def test_prune_events_deletes_only_old(tmp_path):
    p = build_platform(str(tmp_path))
    with session_scope(p.engine) as db:
        db.add(EventRecord(id=new_uid("evt"), type="old", created_at=utcnow() - timedelta(days=100)))
        db.add(EventRecord(id=new_uid("evt"), type="recent"))
        db.commit()
    assert prune_events(p.engine, 30) == 1  # only the 100-day-old one
    with session_scope(p.engine) as db:
        remaining = list(db.exec(select(EventRecord)))
    assert len(remaining) == 1 and remaining[0].type == "recent"


def test_schema_version_stamped(tmp_path):
    eng = make_engine(tmp_path / "v.db")
    init_db(eng)
    assert get_schema_version(eng) == SCHEMA_VERSION


def test_backup_excludes_keys(tmp_path):
    src = tmp_path / "src"
    p = build_platform(str(src))
    p.secrets.set("k", "v", kind="api_key")
    home = p.config.home
    keys = {
        (home / "secrets" / ".secrets.key").resolve(),
        (home / "browser" / ".vault.key").resolve(),
    }
    archive = tmp_path / "b.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for f in home.rglob("*"):
            if f.is_file() and f.resolve() not in keys:
                tar.add(f, arcname=str(f.relative_to(home.parent)))
    with tarfile.open(archive) as tar:
        names = tar.getnames()
    assert not any(".secrets.key" in n for n in names)  # keys excluded
    assert any("ironjarvis.db" in n for n in names)  # data included
