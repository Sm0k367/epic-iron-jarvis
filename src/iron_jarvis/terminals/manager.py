"""Manager that owns every live terminal session for the dashboard."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .backend import PtyBackend
from .session import TerminalSession
from .shells import resolve_shell

#: Default cap on concurrent live sessions to prevent runaway shell spawning.
MAX_SESSIONS = 20


class TerminalManager:
    """Create, look up, list, and kill multiple live terminal sessions.

    Caps the number of *live* sessions (``max_sessions``) so a misbehaving UI
    can't spawn unbounded shells. Killed sessions stay queryable (with
    ``alive=False``) but no longer count against the cap.
    """

    def __init__(self, *, max_sessions: int = MAX_SESSIONS) -> None:
        self.max_sessions = max_sessions
        self._sessions: dict[str, TerminalSession] = {}

    def create(
        self,
        cwd: str | None = None,
        shell: str | None = None,
        cols: int = 80,
        rows: int = 24,
        *,
        backend: PtyBackend | None = None,
        env: dict | None = None,
    ) -> TerminalSession:
        """Create, start, and register a new session.

        ``cwd`` defaults to the user's home; ``shell`` defaults via
        :func:`resolve_shell`. Raises :class:`RuntimeError` at the cap.
        """
        live = sum(1 for s in self._sessions.values() if s.alive)
        if live >= self.max_sessions:
            raise RuntimeError(
                f"terminal session cap reached ({self.max_sessions})"
            )
        cwd = cwd or str(Path.home())
        name, argv = resolve_shell(shell)
        session = TerminalSession(
            cwd=cwd, shell=name, argv=argv, cols=cols, rows=rows, backend=backend
        )
        session.start(env=env)
        self._sessions[session.id] = session
        return session

    def get(self, id: str) -> TerminalSession | None:
        return self._sessions.get(id)

    def list(self) -> list[dict[str, Any]]:
        return [s.info() for s in self._sessions.values()]

    def kill(self, id: str) -> bool:
        session = self._sessions.get(id)
        if session is None:
            return False
        session.kill()
        return True

    def kill_all(self) -> None:
        for session in list(self._sessions.values()):
            try:
                session.kill()
            except Exception:  # pragma: no cover - defensive
                pass
