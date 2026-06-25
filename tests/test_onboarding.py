"""Onboarding + doctor tests — fully offline.

Uses the shared ``platform`` fixture (conftest, built via ``build_platform`` on a
tmp dir). The first-run / checklist assertions clear ANTHROPIC_API_KEY so a key
in the developer's environment can't make a fresh install look "connected".
"""

from __future__ import annotations

import pytest

from iron_jarvis import __version__
from iron_jarvis.agents.orchestrator import Orchestrator
from iron_jarvis.onboarding import doctor, getting_started, is_first_run, readiness


@pytest.fixture(autouse=True)
def _no_real_provider(monkeypatch):
    # A fresh install must look offline-only regardless of the host environment.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


# --- doctor ---------------------------------------------------------------


def test_doctor_returns_ok_shape_with_python_ok():
    result = doctor()

    assert set(result) >= {"ok", "checks"}
    assert isinstance(result["ok"], bool)  # never raises; always a bool
    assert isinstance(result["checks"], list) and result["checks"]

    # Every check carries the documented, renderable shape.
    for check in result["checks"]:
        assert {"name", "ok", "detail", "fix"} <= set(check)
        assert isinstance(check["ok"], bool)

    # The Python check must pass — the test suite is running on a supported Python.
    py = next(c for c in result["checks"] if c["name"] == "python")
    assert py["ok"] is True

    # The dashboard/voice checks exist and are non-fatal (recommended).
    names = {c["name"] for c in result["checks"]}
    assert {"git", "node", "pnpm", "uv", "browser"} <= names


# --- getting_started ------------------------------------------------------


def test_getting_started_returns_four_steps_with_done_booleans(platform):
    steps = getting_started(platform)

    assert len(steps) == 4
    for step in steps:
        assert {"key", "title", "detail", "done", "action"} <= set(step)
        assert isinstance(step["done"], bool)

    keys = [s["key"] for s in steps]
    assert keys == [
        "connect_ai",
        "first_session",
        "work_with_document",
        "teach_style",
    ]


async def test_first_session_step_flips_after_running(platform):
    before = {s["key"]: s["done"] for s in getting_started(platform)}
    assert before["first_session"] is False

    await Orchestrator(platform).run("make a file")

    after = {s["key"]: s["done"] for s in getting_started(platform)}
    assert after["first_session"] is True


# --- is_first_run ---------------------------------------------------------


async def test_is_first_run_true_then_false(platform):
    assert is_first_run(platform) is True

    await Orchestrator(platform).run("make a file")

    assert is_first_run(platform) is False


# --- readiness ------------------------------------------------------------


def test_readiness_includes_version_doctor_and_checklist(platform):
    report = readiness(platform)

    assert report["version"] == __version__
    assert report["first_run"] is True  # fresh platform, no real provider
    assert "ok" in report["doctor"] and isinstance(report["doctor"]["checks"], list)
    assert isinstance(report["checklist"], list) and len(report["checklist"]) == 4
    # next_step is the first incomplete step on a fresh install.
    assert report["next_step"]["key"] == "connect_ai"
