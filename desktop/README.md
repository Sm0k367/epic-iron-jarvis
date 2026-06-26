# Iron Jarvis — Desktop

A thin **Electron** wrapper that turns Iron Jarvis into a native desktop app. It
launches the local Python daemon and the Next.js dashboard for you, waits for
them to come up behind a splash screen, then opens the dashboard in a real
window — no terminal juggling.

> **Scope:** this is a *dev-mode* wrapper. It runs the daemon and dashboard
> **straight out of this repo** (the folder one level up). It does **not** yet
> bundle Python or a prebuilt dashboard into a standalone installer — that's a
> future step (see [Packaging](#packaging) and [Roadmap](#roadmap)).

```
desktop/
├── package.json     # iron-jarvis-desktop — its own deps, separate from the dashboard
├── main.js          # Electron main process: spawns daemon + dashboard, manages windows
├── preload.js       # exposes window.ironjarvis = { isDesktop, version }
├── loading.html     # dark "Starting Iron Jarvis…" splash
└── assets/
    ├── icon.png     # placeholder app icon (replace with your brand icon)
    └── README.md
```

## What it does

On launch, `main.js`:

1. Shows a dark **"Starting Iron Jarvis…"** splash window.
2. Verifies `uv` and `pnpm` are on your `PATH` (friendly error dialog if not).
3. Spawns the **daemon**:
   `uv run ironjarvis serve --host 127.0.0.1 --port 8787 --root <repoRoot>`
   (cwd = repo root, one directory above `desktop/`).
4. Spawns the **dashboard**: `pnpm start` (cwd = `../dashboard`, `PORT` set from env).
5. Polls `http://127.0.0.1:3000` for up to ~30s until it answers.
6. Opens the main **1440×900** window on `http://localhost:3000` and closes the splash.
7. On quit, **kills both child processes** (`taskkill /T /F` on Windows) so nothing
   is left listening.

External links (target `_blank` / off-origin navigations) open in your system
browser. The app menu has reload / force-reload / toggle devtools / quit.

## Prerequisites

This wrapper drives the existing repo tooling, so you need:

- **Node 20** and **pnpm 10** (`npm i -g pnpm`)
- **uv** — the Python runner (<https://docs.astral.sh/uv/>)
- The Python deps installable by uv (handled automatically by `uv run`)
- **The dashboard built once** (Next.js `start` serves a *production* build):

  ```bash
  cd ../dashboard
  pnpm install
  pnpm build
  ```

  If you skip this, the splash will time out and show a dialog telling you to run
  `pnpm build`.

## Run

```bash
cd desktop
pnpm install      # installs Electron (downloads the Electron binary — expected)
pnpm start        # boots the daemon + dashboard and opens the native window
```

`pnpm dev` is an alias for `pnpm start`.

### Configuration

| Env var             | Default | Purpose                        |
| ------------------- | ------- | ------------------------------ |
| `IJ_DAEMON_PORT`    | `8787`  | Port for `ironjarvis serve`    |
| `IJ_DASHBOARD_PORT` | `3000`  | Port for the Next.js dashboard |

Example:

```bash
IJ_DAEMON_PORT=9001 IJ_DASHBOARD_PORT=3100 pnpm start
```

## Packaging

```bash
cd desktop
pnpm dist          # electron-builder --win → NSIS installer in desktop/release/
```

The `electron-builder` config lives in `package.json` under `build`:

- `appId`: `com.realdealcpa.ironjarvis`
- `productName`: `Iron Jarvis`
- `directories.output`: `release`
- `win.target`: `nsis`
- `files`: `main.js`, `preload.js`, `loading.html`, `assets/**`

> **Important:** the packaged app **still expects the repo (daemon + `dashboard/`)
> to live one directory above the installed app** and still shells out to `uv`
> and `pnpm`. The installer ships the Electron shell, *not* Python or the
> dashboard. Treat `pnpm dist` as "package the shell", not "ship to a machine
> that doesn't have the repo".

## Roadmap

To become a true standalone install (no repo, no global `uv`/`pnpm` required):

- Bundle a prebuilt dashboard (`next build` output or a static export) inside the
  app and serve it locally instead of shelling out to `pnpm start`.
- Ship the daemon as a packaged binary (e.g. PyInstaller) or an embedded Python,
  and reference it via `extraResources` instead of `uv run`.
- Code-sign the installer.

## Troubleshooting

- **"missing prerequisites" dialog** — install `uv` and/or `pnpm`, then relaunch.
- **"dashboard did not start" dialog** — you almost certainly haven't built the
  dashboard: `cd ../dashboard && pnpm install && pnpm build`. Watch the terminal
  for `[daemon]` / `[dashboard]` logs.
- **Port already in use** — set `IJ_DAEMON_PORT` / `IJ_DASHBOARD_PORT`.
