"""Frozen entry point for the Iron Jarvis daemon.

PyInstaller targets THIS file. A frozen app has no console-script shim, so we
import the Typer ``app`` and invoke it directly. Every CLI subcommand
(``serve``, ``status``, ``demo``, ...) is therefore available from the exe, e.g.

    ironjarvis.exe serve --port 8799 --root C:\\path\\to\\state

``serve`` is the long-running daemon (FastAPI + uvicorn) the dashboard/Electron
shell spawns.
"""

from __future__ import annotations

import multiprocessing


def main() -> None:
    # Defer the (heavy) package import until after freeze_support so the
    # multiprocessing bootstrap path stays cheap if it is ever taken.
    from iron_jarvis.daemon.cli import app

    app()


if __name__ == "__main__":
    # Harmless on a single-process daemon, but mandatory if any dependency ever
    # spawns a child process under a frozen Windows build.
    multiprocessing.freeze_support()
    main()
