# Freezing the Iron Jarvis daemon (standalone Windows exe)

This directory freezes the Iron Jarvis daemon into a **standalone Windows
application** with [PyInstaller]. The result runs with **no Python and no uv
installed** — ideal for bundling inside an Electron shell or shipping to a
machine without a dev toolchain.

- Build type: **onedir** (a folder, not a single `.exe`). Onedir is preferred
  for a complex app — faster cold start and easy to embed in Electron.
- Entry point: `ironjarvis_entry.py` → `from iron_jarvis.daemon.cli import app; app()`
  (the full Typer CLI, so every subcommand works, `serve` being the daemon).
- Provider at boot: **mock** (offline). No network is touched to boot or serve
  `/health`.

## Build

From the repo root, with the project venv at `.venv`:

```powershell
# one-shot, reproducible (installs pyinstaller if missing, then builds):
powershell -ExecutionPolicy Bypass -File packaging\build_daemon.ps1

# build + boot-and-verify GET /health == 200 from the frozen exe:
powershell -ExecutionPolicy Bypass -File packaging\build_daemon.ps1 -Verify
```

Or call PyInstaller directly:

```powershell
.\.venv\Scripts\activate
pip install pyinstaller          # once
pyinstaller packaging\ironjarvis.spec --noconfirm `
    --distpath packaging\dist --workpath packaging\build
```

## Output

```
packaging/dist/ironjarvis/ironjarvis.exe   <- launch this
packaging/dist/ironjarvis/_internal/       <- bundled stdlib + deps + iron_jarvis
```

Approximate onedir size: **~136 MB**. The `ironjarvis.exe` launcher itself is
~23 MB; the rest lives under `_internal/`. Build artifacts (`packaging/build/`,
`packaging/dist/`) are git-ignored.

## Run the daemon

```powershell
packaging\dist\ironjarvis\ironjarvis.exe serve --port 8799 --root C:\path\to\state
```

- `serve` starts FastAPI + uvicorn (the long-running daemon).
- `--port` HTTP port (CLI default 8787).
- `--root` project root; Iron Jarvis writes its state under `<root>\.ironjarvis`.
  Use a writable, app-owned directory.

Any other CLI subcommand works too, e.g. `ironjarvis.exe status`,
`ironjarvis.exe demo`, `ironjarvis.exe doc-read <file>`.

## Verified result (frozen exe, offline)

Booted `ironjarvis.exe serve --port 8799 --root <temp>` and called
`GET http://127.0.0.1:8799/health`:

```
STATUS 200
{"status":"ok","version":"0.1.0","default_provider":"mock",
 "default_model":"claude-opus-4-8",
 "providers":[{"provider":"anthropic","available":false,"class":"api"},
   {"provider":"google","available":false,"class":"api"},
   {"provider":"mock","available":true,"class":"mock"},
   {"provider":"ollama","available":false,"class":"local"},
   {"provider":"openai","available":false,"class":"api"}, ...browser providers...]}
```

Daemon log: `Application startup complete.` (the lifespan startup runs the
APScheduler cron scheduler with no error — apscheduler is bundled). No network
at boot; `mock` is the only available provider, exactly as intended.

## What is bundled vs. excluded

**Bundled** (so the daemon and its tools work out of the box): the whole
`iron_jarvis` package (every submodule, so all SQLModel tables register) +
fastapi, starlette, uvicorn[standard] (+ websockets/httptools), sqlmodel,
sqlalchemy (+ greenlet), pydantic / pydantic_core, cryptography, apscheduler,
numpy, httpx/httpcore/h11, typer/click/rich, anyio, tomli_w, pyyaml, the
`SKILL.md` skill data, and the document libraries **pypdf, python-docx,
openpyxl, python-pptx, fpdf2, Pillow**. On Windows, `pywinpty` (terminals) is
included.

**Excluded** — heavy *optional* deps the daemon must boot **without**. Each is
imported lazily and only when a real key / opt-in feature is used:

| Excluded     | Used only for                                  |
|--------------|------------------------------------------------|
| `playwright` | computer-use (browser automation)              |
| `docker`     | the Docker sandbox runtime                      |
| `anthropic`  | a real Anthropic API key (mock is the default) |
| `openai`     | a real OpenAI API key                           |

> The Google provider needs **no SDK** (it uses raw `httpx`), so nothing is
> excluded for it.

### Re-including an excluded dependency

1. Open `packaging/ironjarvis.spec`, find the `excludes = [...]` list, and
   delete the name (e.g. remove `"anthropic"`).
2. (Recommended) add it to the `_collect(...)` loop so its submodules/data are
   pulled in, e.g. add `"anthropic"` to the core `for pkg in (...)` tuple.
3. For **playwright** specifically, the bundle only carries the Python package —
   the browser binaries are installed separately at runtime via
   `playwright install`, into a path the frozen app can reach
   (`PLAYWRIGHT_BROWSERS_PATH`).
4. Rebuild.

See `hidden_imports.txt` for the full collect/hiddenimport/exclude reference.

## Notes for the Electron shell (spawning this exe)

- **Exe path:** `packaging/dist/ironjarvis/ironjarvis.exe` (ship the *entire*
  `ironjarvis/` folder — the exe needs its sibling `_internal/`).
- **Spawn args:** `serve --port <PORT> --root <STATE_DIR>`. Pick a free port and
  a writable per-user state dir (e.g. under `app.getPath('userData')`).
- **Readiness:** poll `GET http://127.0.0.1:<PORT>/health` until HTTP 200
  (boots in ~1–2 s). The JSON body has `status: "ok"`.
- **Shutdown:** the process runs in the foreground (uvicorn); terminate the
  child process to stop it. It handles CTRL+C / SIGTERM cleanly.
- **Offline:** no network is required to boot or serve; default provider is
  `mock`. Real LLM providers are connected later at runtime via the
  Connections API / secrets vault (no rebuild needed for keys).
- **Optional auth/CORS:** set `IRONJARVIS_TOKEN` (bearer) and
  `IRONJARVIS_CORS_ORIGINS` in the spawned process's env for a locked-down
  deployment; both are no-ops locally.

[PyInstaller]: https://pyinstaller.org/
