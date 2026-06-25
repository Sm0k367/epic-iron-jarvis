"""Self-diagnostic ("doctor") for Iron Jarvis.

A SAFE, read-only health check anyone can run from zero to confirm their machine
can get value out of Iron Jarvis. No check ever raises; each returns a human
``detail`` and an actionable ``fix`` hint. *Required* checks gate the overall
``ok`` (these are what the install itself needs); *recommended* checks — the web
dashboard and voice/browser tooling — only warn so a minimal Python+uv install
still reports healthy.
"""

from __future__ import annotations

import os
import shutil
import sys

#: Minimum Python the platform supports (matches pyproject's requires-python).
MIN_PYTHON: tuple[int, int] = (3, 12)

REQUIRED = "required"
RECOMMENDED = "recommended"


def _result(
    name: str, ok: bool, detail: str, fix: str = "", level: str = REQUIRED
) -> dict:
    """One normalized check row: ``{name, ok, detail, fix, level}``."""
    return {"name": name, "ok": bool(ok), "detail": detail, "fix": fix, "level": level}


def _which(*names: str) -> str | None:
    """First executable among ``names`` found on PATH, else None (read-only)."""
    for n in names:
        try:
            path = shutil.which(n)
        except Exception:  # noqa: BLE001 — never let a probe crash the doctor
            path = None
        if path:
            return path
    return None


def _find_browser() -> str | None:
    """Locate a Chromium-based browser (Chrome/Edge) without launching it.

    Checks PATH first (cross-platform), then well-known Windows/macOS install
    locations. Pure ``os.path.exists`` lookups — nothing is executed.
    """
    path = _which(
        "chrome",
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "msedge",
    )
    if path:
        return path

    candidates: list[str] = []
    for env in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData"):
        base = os.environ.get(env)
        if not base:
            continue
        candidates += [
            os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
        ]
    candidates.append(
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    )
    candidates.append(
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
    )
    for c in candidates:
        try:
            if c and os.path.exists(c):
                return c
        except OSError:
            continue
    return None


def check_python() -> dict:
    v = sys.version_info
    ok = (v.major, v.minor) >= MIN_PYTHON
    cur = f"{v.major}.{v.minor}.{v.micro}"
    need = f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]}"
    detail = (
        f"Python {cur} (>= {need} required)."
        if ok
        else f"Python {cur} is too old; Iron Jarvis needs >= {need}."
    )
    return _result(
        "python",
        ok,
        detail,
        fix=""
        if ok
        else f"Install Python {need}+ from https://python.org and recreate the venv.",
    )


def check_uv() -> dict:
    path = _which("uv")
    ok = path is not None
    return _result(
        "uv",
        ok,
        f"uv found at {path}."
        if ok
        else "uv (the Python package/runtime manager) is not on PATH.",
        fix=""
        if ok
        else "Install uv: https://docs.astral.sh/uv/ "
        "(PowerShell: `irm https://astral.sh/uv/install.ps1 | iex`).",
    )


def check_git() -> dict:
    path = _which("git")
    ok = path is not None
    return _result(
        "git",
        ok,
        f"git found at {path}."
        if ok
        else "git is not on PATH — needed for git-native sessions and review/approve.",
        fix=""
        if ok
        else "Install Git: https://git-scm.com/downloads (optional unless you "
        "want git-native review).",
        level=RECOMMENDED,
    )


def check_node() -> dict:
    path = _which("node")
    ok = path is not None
    return _result(
        "node",
        ok,
        f"node found at {path}."
        if ok
        else "Node.js not found — only needed to run the web dashboard.",
        fix=""
        if ok
        else "Install Node.js LTS: https://nodejs.org "
        "(the dashboard is optional; the CLI and daemon work without it).",
        level=RECOMMENDED,
    )


def check_pnpm() -> dict:
    path = _which("pnpm")
    ok = path is not None
    return _result(
        "pnpm",
        ok,
        f"pnpm found at {path}."
        if ok
        else "pnpm not found — only needed to install/run the web dashboard.",
        fix=""
        if ok
        else "Install pnpm: https://pnpm.io/installation (or run `corepack enable`). "
        "Dashboard-only.",
        level=RECOMMENDED,
    )


def check_browser() -> dict:
    path = _find_browser()
    ok = path is not None
    return _result(
        "browser",
        ok,
        f"Chromium-based browser found ({path})."
        if ok
        else "No Chrome/Edge found — needed for the voice UI and browser automation.",
        fix=""
        if ok
        else "Install Google Chrome (https://google.com/chrome) or Microsoft Edge.",
        level=RECOMMENDED,
    )


#: Ordered list of every check callable — callers may render this directly.
CHECKS = [
    check_python,
    check_uv,
    check_git,
    check_node,
    check_pnpm,
    check_browser,
]


def doctor() -> dict:
    """Run every check and summarize machine readiness.

    Returns ``{"ok": bool, "checks": [{name, ok, detail, fix, level}, ...]}``.
    ``ok`` is True iff every *required* check passes; recommended checks only
    warn. Never raises — a check that errors is reported as a failed row.
    """
    checks: list[dict] = []
    for fn in CHECKS:
        try:
            checks.append(fn())
        except Exception as exc:  # noqa: BLE001 — diagnostics must never crash
            name = getattr(fn, "__name__", "check").replace("check_", "")
            checks.append(
                _result(
                    name,
                    False,
                    f"check '{name}' failed to run: {exc}",
                    fix="This is a bug in the doctor check; please report it.",
                    level=RECOMMENDED,
                )
            )
    ok = all(c["ok"] for c in checks if c.get("level") == REQUIRED)
    return {"ok": ok, "checks": checks}
