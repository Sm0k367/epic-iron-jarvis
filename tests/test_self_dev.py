"""Self-development: an Iron Jarvis agent can read/edit/fix Iron Jarvis's OWN
source, gated (opt-in) and review-only (never auto-merge).

Offline: drives the real ``git`` binary in ``tmp_path``; no network/provider.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from iron_jarvis.agents.orchestrator import Orchestrator
from iron_jarvis.core.db import session_scope
from iron_jarvis.core.models import AgentType, Session, SessionStatus
from iron_jarvis.core.self_dev import iron_jarvis_repo_root, self_dev_status
from iron_jarvis.git.integration import list_session_worktrees
from iron_jarvis.platform import build_platform
from iron_jarvis.tools.base import ToolContext
from iron_jarvis.tools.builtins import EditFileTool


def _run(args, cwd):
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return proc.stdout


def _make_fake_ij_repo(path: Path) -> Path:
    """A throwaway git repo that looks like the Iron Jarvis project."""
    path.mkdir(parents=True, exist_ok=True)
    _run(["init"], path)
    _run(["config", "user.email", "t@t"], path)
    _run(["config", "user.name", "t"], path)
    (path / "pyproject.toml").write_text('[project]\nname = "iron-jarvis"\n')
    (path / "src").mkdir()
    (path / "src" / "thing.py").write_text("VALUE = 1\n")
    _run(["add", "-A"], path)
    _run(["commit", "-m", "base"], path)
    return path.resolve()


def test_repo_root_auto_detect():
    root = iron_jarvis_repo_root(None)
    if root is None:
        pytest.skip("installed as a package (no source checkout) — override path is used")
    assert (root / "pyproject.toml").is_file()
    assert (root / "src" / "iron_jarvis").is_dir()


def test_status_disabled_by_default(tmp_path):
    platform = build_platform(str(tmp_path))
    st = self_dev_status(platform.config)
    assert st["enabled"] is False
    assert st["available"] is False


def test_status_enabled_with_override(tmp_path):
    repo = _make_fake_ij_repo(tmp_path / "ijrepo")
    platform = build_platform(str(tmp_path / "proj"))
    platform.config.self_dev_enabled = True
    platform.config.self_dev_root = str(repo)
    st = self_dev_status(platform.config)
    assert st["enabled"] is True and st["available"] is True
    assert Path(st["repo_root"]) == repo


async def test_self_dev_disabled_is_refused(tmp_path):
    platform = build_platform(str(tmp_path / "proj"))
    orch = Orchestrator(platform)
    with pytest.raises(PermissionError):
        await orch.create_session("fix a bug", self_dev=True)


async def test_self_dev_session_edits_own_source_review_gated(tmp_path):
    repo = _make_fake_ij_repo(tmp_path / "ijrepo")
    base_value = (repo / "src" / "thing.py").read_text()

    platform = build_platform(str(tmp_path / "proj"))
    platform.config.self_dev_enabled = True
    platform.config.self_dev_root = str(repo)
    orch = Orchestrator(platform)

    session = await orch.create_session("improve thing.py", self_dev=True)
    try:
        # Runs as the Maintainer, on a git worktree of the IJ repo itself.
        assert session.agent_type is AgentType.MAINTAINER
        ws = Path(session.workspace_path)
        assert (ws / "pyproject.toml").is_file()  # the repo's OWN files are present
        assert (ws / "src" / "thing.py").is_file()
        assert session.id in orch._git_sessions

        # The maintainer's file tools edit the worktree (its own source)...
        ctx = ToolContext(
            workspace=ws, session_id=session.id, agent_run_id="r",
            config=platform.config, event_bus=platform.event_bus, engine=platform.engine,
        )
        res = await EditFileTool().execute(
            {"path": "src/thing.py", "old": "VALUE = 1", "new": "VALUE = 2"}, ctx
        )
        assert res.ok
        assert "VALUE = 2" in (ws / "src" / "thing.py").read_text()

        # ...but the base repo is UNTOUCHED — changes land only via review/approve.
        assert (repo / "src" / "thing.py").read_text() == base_value
        gs = orch._git_sessions[session.id]
        assert "VALUE = 2" in gs.diff()  # captured as a reviewable patch
    finally:
        gs = orch._git_sessions.get(session.id)
        if gs is not None:
            try:
                gs.discard()
            except Exception:
                pass


def test_self_dev_root_requires_iron_jarvis_identity(tmp_path):
    # A plain git repo that is NOT Iron Jarvis must be rejected by the override.
    other = tmp_path / "other"
    other.mkdir()
    _run(["init"], other)
    (other / "pyproject.toml").write_text('[project]\nname = "something-else"\n')

    class Cfg:
        self_dev_root = str(other)
        self_dev_enabled = True

    assert iron_jarvis_repo_root(Cfg()) is None


def test_merge_conflict_leaves_clean_checkout(tmp_path):
    from iron_jarvis.git.integration import GitError, GitSession

    repo = _make_fake_ij_repo(tmp_path / "r")  # on master, thing.py VALUE=1
    gs = GitSession.start(repo, tmp_path / "ws", "conflict")
    (Path(gs.workspace) / "src" / "thing.py").write_text("VALUE = 999\n")
    gs.commit("session change")
    # Advance base (master) with a CONFLICTING edit to the same line.
    (repo / "src" / "thing.py").write_text("VALUE = 111\n")
    _run(["add", "-A"], repo)
    _run(["commit", "-m", "advance base"], repo)

    with pytest.raises(GitError):
        gs.merge_into_base()

    # The main checkout must be left clean — no in-progress/aborted merge, no
    # conflict markers parked in the developer's tree.
    assert not (repo / ".git" / "MERGE_HEAD").exists()
    assert _run(["status", "--porcelain"], repo).strip() == ""
    assert _run(["rev-parse", "--abbrev-ref", "HEAD"], repo).strip() == "master"


async def test_prune_orphan_worktrees(tmp_path):
    repo = _make_fake_ij_repo(tmp_path / "ijrepo")
    platform = build_platform(str(tmp_path / "proj"))
    platform.config.self_dev_enabled = True
    platform.config.self_dev_root = str(repo)
    orch = Orchestrator(platform)

    session = await orch.create_session("orphan me", self_dev=True)
    branch = orch._git_sessions[session.id].branch
    assert any(b == branch for _, b in list_session_worktrees(repo))

    # Simulate a daemon restart: in-memory review state is gone, session FAILED.
    orch._git_sessions.clear()
    orch._reviews.clear()
    with session_scope(platform.engine) as db:
        s = db.get(Session, session.id)
        s.status = SessionStatus.FAILED
        db.add(s)
        db.commit()

    pruned = orch.prune_orphan_worktrees()
    assert branch in pruned
    assert not any(b == branch for _, b in list_session_worktrees(repo))
