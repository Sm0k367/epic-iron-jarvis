"""A single live terminal session — an id'd wrapper around a :class:`PtyBackend`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.ids import new_id, utcnow
from .backend import PtyBackend, default_backend
from .shells import resolve_shell


class TerminalSession:
    """One real shell the user can type into, streamed over a WebSocket.

    The backend is injectable (tests pass a :class:`FakeBackend`); when omitted
    the best backend for the current OS is built via :func:`default_backend`.
    """

    def __init__(
        self,
        cwd: str | None = None,
        shell: str | None = None,
        *,
        argv: list[str] | None = None,
        cols: int = 80,
        rows: int = 24,
        backend: PtyBackend | None = None,
    ) -> None:
        if argv is None:
            shell, argv = resolve_shell(shell)
        self.id = new_id("term")
        self.cwd = cwd or str(Path.home())
        self.shell = shell or "shell"
        self.argv = list(argv)
        self.cols = cols
        self.rows = rows
        self.created_at = utcnow()
        self.backend: PtyBackend = backend if backend is not None else default_backend()
        self._started = False

    def start(self, env: dict | None = None) -> "TerminalSession":
        """Spawn the shell (idempotent)."""
        if not self._started:
            self.backend.start(self.argv, self.cwd, env, self.cols, self.rows)
            self._started = True
        return self

    def write(self, data: str | bytes) -> None:
        self.backend.write(data)

    def read(self, max_bytes: int = 65536) -> bytes:
        """Non-blocking read of pending output (``b""`` if nothing ready)."""
        return self.backend.read_nonblocking(max_bytes)

    def resize(self, cols: int, rows: int) -> None:
        self.cols = cols
        self.rows = rows
        self.backend.resize(cols, rows)

    def kill(self) -> None:
        self.backend.kill()

    @property
    def alive(self) -> bool:
        return self._started and self.backend.is_alive()

    @property
    def exit_code(self) -> int | None:
        return self.backend.exit_code

    def info(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "cwd": self.cwd,
            "shell": self.shell,
            "argv": list(self.argv),
            "cols": self.cols,
            "rows": self.rows,
            "alive": self.alive,
            "exit_code": self.exit_code,
            "created_at": self.created_at.isoformat(),
        }
