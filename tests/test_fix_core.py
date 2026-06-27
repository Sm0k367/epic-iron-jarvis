"""Core hardening fixes: full-width ids, FS policy, SQLite WAL + additive
schema reconciler, and event-bus offload / bounded-queue / error-logging.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from iron_jarvis.core import fs_policy
from iron_jarvis.core.db import _reconcile_additive_columns, init_db, make_engine
from iron_jarvis.core.events import Event, EventBus, EventType
from iron_jarvis.core.ids import new_id, new_uid


# --- ids ---------------------------------------------------------------------
def test_new_uid_is_full_width():
    uid = new_uid("evt")
    assert uid.startswith("evt_")
    assert len(uid.split("_", 1)[1]) == 32  # 128-bit hex — collision-free
    assert len(new_id("session").split("_", 1)[1]) == 12  # short id unchanged


def test_event_id_uses_full_width():
    assert len(Event(type="x").id.split("_", 1)[1]) == 32


# --- fs_policy ---------------------------------------------------------------
def test_protected_path(tmp_path):
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir()
    key = secret_dir / ".secrets.key"
    key.write_text("topsecret")
    fs_policy.register_protected_root(secret_dir)
    assert fs_policy.is_protected_path(key) is True
    ok, reason = fs_policy.fs_read_ok(key)
    assert ok is False and reason
    other = tmp_path / "ok.txt"
    other.write_text("x")
    assert fs_policy.is_protected_path(other) is False


def test_allowlist(tmp_path, monkeypatch):
    inside = tmp_path / "allowed"
    inside.mkdir()
    f = inside / "a.txt"
    f.write_text("x")
    outside = tmp_path / "denied.txt"
    outside.write_text("y")
    monkeypatch.setenv("IRONJARVIS_FS_ALLOWLIST", str(inside))
    assert fs_policy.fs_path_allowed(f) is True
    assert fs_policy.fs_path_allowed(outside) is False
    monkeypatch.delenv("IRONJARVIS_FS_ALLOWLIST")
    assert fs_policy.fs_path_allowed(outside) is True  # unset -> unrestricted


# --- db: WAL + busy_timeout + additive reconciler ----------------------------
def test_db_pragmas(tmp_path):
    engine = make_engine(tmp_path / "x.db")
    with engine.connect() as conn:
        mode = conn.execute(text("PRAGMA journal_mode")).scalar()
        busy = conn.execute(text("PRAGMA busy_timeout")).scalar()
    assert str(mode).lower() == "wal"
    assert int(busy) >= 30000


def test_reconcile_adds_missing_columns(tmp_path):
    engine = make_engine(tmp_path / "y.db")
    # Simulate an OLD db whose eventrecord predates newer model columns.
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE eventrecord (id TEXT PRIMARY KEY)"))
    init_db(engine)  # create_all skips the existing table; reconciler heals it
    with engine.connect() as conn:
        cols = {r[1] for r in conn.execute(text('PRAGMA table_info("eventrecord")')).all()}
    assert {"type", "session_id", "payload_json", "created_at"} <= cols
    # idempotent: a second pass adds nothing and does not error
    _reconcile_additive_columns(engine)


# --- event bus ---------------------------------------------------------------
def _boom(_ev):
    raise RuntimeError("bad handler")


async def test_failing_handler_swallowed_and_event_still_delivered():
    bus = EventBus()
    seen: list[str] = []
    bus.add_handler(_boom)
    bus.add_handler(lambda ev: seen.append(ev.type))
    ev = await bus.publish(EventType.AGENT_STARTED, {"x": 1})
    # publish returns normally despite the raising handler...
    assert ev.type == EventType.AGENT_STARTED
    # ...and handlers DID run (awaited off-loop), in order, by the time we return.
    assert EventType.AGENT_STARTED in seen
    assert bus.history[-1].type == EventType.AGENT_STARTED


async def test_subscriber_queue_is_bounded():
    bus = EventBus()
    agen = bus.subscribe()
    task = asyncio.create_task(agen.__anext__())
    await asyncio.sleep(0.02)  # let the subscriber register its queue
    q = next(iter(bus._subscribers))
    assert q.maxsize == 1000  # bounded — drop-oldest on overflow
    await bus.publish(EventType.AGENT_STARTED, {})
    await asyncio.wait_for(task, timeout=1.0)
    await agen.aclose()
