"""Regression tests for F8: bounded retention of dead terminal sessions.

TerminalManager.kill() used to leave the killed session in ``_sessions``
forever, and create()'s cap only counted live sessions, so dead entries
accumulated without bound across create/kill churn. These tests assert the
dict stays bounded while a just-killed session remains queryable.
"""

from __future__ import annotations

from iron_jarvis.terminals import FakeBackend, TerminalManager


def _create(m: TerminalManager) -> str:
    return m.create(backend=FakeBackend()).id


def test_dead_sessions_are_bounded_across_create_kill_churn():
    m = TerminalManager(max_sessions=5, max_dead_retained=10)
    # Churn many sessions: create then immediately kill, far more than caps.
    for _ in range(200):
        sid = _create(m)
        m.kill(sid)
    # The dict must not grow without bound: only the retained dead window
    # (plus any live sessions, of which there are none here) survives.
    assert len(m._sessions) <= m.max_dead_retained
    assert all(not s.alive for s in m._sessions.values())


def test_just_killed_session_stays_queryable():
    m = TerminalManager(max_sessions=20, max_dead_retained=10)
    sid = _create(m)
    assert m.kill(sid) is True
    # Still queryable right after the kill, reporting alive=False.
    s = m.get(sid)
    assert s is not None
    assert s.alive is False
    assert any(i["id"] == sid for i in m.list())


def test_oldest_dead_session_is_evicted_first():
    m = TerminalManager(max_sessions=50, max_dead_retained=3)
    ids = []
    for _ in range(10):
        sid = _create(m)
        m.kill(sid)
        ids.append(sid)
    # Only the 3 most-recently-killed remain queryable; older ones evicted.
    assert m.get(ids[0]) is None
    assert m.get(ids[-1]) is not None
    survivors = [sid for sid in ids if m.get(sid) is not None]
    assert survivors == ids[-3:]


def test_purge_dead_keeps_live_sessions():
    m = TerminalManager(max_sessions=20, max_dead_retained=2)
    live_ids = [_create(m) for _ in range(3)]
    # Create and kill several extra sessions to overflow the dead window.
    for _ in range(10):
        m.kill(_create(m))
    m.purge_dead()
    # Every live session is untouched, regardless of the dead retention cap.
    for sid in live_ids:
        s = m.get(sid)
        assert s is not None and s.alive is True
    dead = [s for s in m._sessions.values() if not s.alive]
    assert len(dead) <= 2


def test_create_purges_before_cap_check():
    # Live cap of 2; churn leaves dead entries that must not block creation
    # and must not accumulate unbounded.
    m = TerminalManager(max_sessions=2, max_dead_retained=4)
    for _ in range(100):
        m.kill(_create(m))
    # Two live slots are still freely available after all that churn.
    a = m.create(backend=FakeBackend())
    b = m.create(backend=FakeBackend())
    assert a.alive and b.alive
    # Total dict size stays bounded by live + retained-dead window.
    assert len(m._sessions) <= m.max_sessions + m.max_dead_retained


def test_purge_dead_returns_count_evicted():
    m = TerminalManager(max_sessions=20, max_dead_retained=1)
    for _ in range(5):
        m.kill(_create(m))
    # 5 dead, retain 1 -> the next purge has nothing more to evict.
    assert m.purge_dead() == 0
    assert len([s for s in m._sessions.values() if not s.alive]) == 1
