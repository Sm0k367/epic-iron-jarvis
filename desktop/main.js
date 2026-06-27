// Iron Jarvis — Electron main process (CommonJS).
//
// What this does (dev-mode wrapper):
//   1. Spawns the Python daemon:  uv run ironjarvis serve --host 127.0.0.1 --port <DAEMON_PORT> --root <repoRoot>
//   2. Spawns the Next.js dashboard:  pnpm start   (Next reads PORT from env)
//   3. Shows a dark "Starting Iron Jarvis…" splash while polling the dashboard.
//   4. When the dashboard answers, opens the real 1440x900 window on http://localhost:<DASHBOARD_PORT>.
//   5. On quit, kills BOTH child processes (taskkill /T /F on Windows).
//
// The repo (daemon + ./dashboard) is expected one directory above this file.

const { app, BrowserWindow, Menu, shell, dialog } = require("electron");
const { spawn } = require("child_process");
const http = require("http");
const path = require("path");

// --- Configuration -------------------------------------------------------

// Two run modes:
//  - DEV (not packaged): the repo (daemon + ./dashboard) sits one dir above this
//    file; we drive it via `uv run ironjarvis serve` + `pnpm start`.
//  - PACKAGED (installed .exe): a frozen daemon exe + a Next.js *standalone*
//    server are bundled under resources/; we run them via the frozen exe and
//    Electron's own bundled Node — NO Python, uv, Node, or pnpm required.
const IS_PACKAGED = app.isPackaged;
const REPO_ROOT = path.join(__dirname, "..");
const DASHBOARD_DIR = path.join(REPO_ROOT, "dashboard");
const RES_DIR = process.resourcesPath || REPO_ROOT;
const DAEMON_EXE = path.join(RES_DIR, "daemon", "ironjarvis.exe");
const DASHBOARD_SERVER = path.join(RES_DIR, "dashboard", "server.js");

// The dashboard's API base (NEXT_PUBLIC_IJ_API) is baked at build time to
// 127.0.0.1:8787, so the bundled daemon MUST listen on 8787.
const DAEMON_PORT = parseInt(process.env.IJ_DAEMON_PORT || "8787", 10);
const DASHBOARD_PORT = parseInt(process.env.IJ_DASHBOARD_PORT || "3000", 10);

const DASHBOARD_URL = `http://localhost:${DASHBOARD_PORT}`;
const DASHBOARD_PROBE_URL = `http://127.0.0.1:${DASHBOARD_PORT}/`;
const STARTUP_TIMEOUT_MS = 30000;

// --- State ---------------------------------------------------------------

let daemonProc = null;
let dashboardProc = null;
let loadingWin = null;
let mainWin = null;
let shuttingDown = false;

// --- Child process helpers ----------------------------------------------

function spawnChild(label, command, args, cwd, extraEnv, useShell = true) {
  const child = spawn(command, args, {
    cwd,
    // Dev resolves uv/pnpm via cmd.exe (shell:true); packaged spawns the frozen
    // exe and Electron's node binary directly (shell:false).
    shell: useShell,
    windowsHide: true,
    env: { ...process.env, ...(extraEnv || {}) },
  });

  if (child.stdout) {
    child.stdout.on("data", (d) => process.stdout.write(`[${label}] ${d}`));
  }
  if (child.stderr) {
    child.stderr.on("data", (d) => process.stderr.write(`[${label}] ${d}`));
  }
  child.on("error", (err) => {
    // With shell:true the inner command (uv/pnpm) won't raise ENOENT here —
    // that's covered by the preflight check below. This catches shell failures.
    console.error(`[${label}] spawn error:`, err.message);
  });
  child.on("exit", (code, signal) => {
    console.log(`[${label}] exited (code=${code}, signal=${signal}, pid=${child.pid})`);
  });

  console.log(`[${label}] started pid=${child.pid}: ${command} ${args.join(" ")} (cwd=${cwd})`);
  return child;
}

// Resolve whether a command is on PATH (so we can show a friendly dialog
// instead of silently timing out when uv/pnpm aren't installed).
function commandExists(cmd) {
  return new Promise((resolve) => {
    const probe = process.platform === "win32" ? "where" : "which";
    const child = spawn(probe, [cmd], { shell: true, windowsHide: true });
    child.on("error", () => resolve(false));
    child.on("exit", (code) => resolve(code === 0));
  });
}

function killChild(child, label) {
  if (!child) return;
  // Already exited?
  if (child.exitCode !== null || child.signalCode !== null) return;
  const pid = child.pid;
  if (!pid) return;
  try {
    if (process.platform === "win32") {
      // shell:true means `pid` is the cmd.exe wrapper; /T kills the whole tree.
      spawn("taskkill", ["/pid", String(pid), "/T", "/F"], { windowsHide: true });
    } else {
      child.kill("SIGTERM");
    }
    console.log(`[${label}] kill signal sent (pid=${pid})`);
  } catch (err) {
    console.error(`[${label}] failed to kill (pid=${pid}):`, err.message);
  }
}

function shutdown() {
  if (shuttingDown) return;
  shuttingDown = true;
  killChild(daemonProc, "daemon");
  killChild(dashboardProc, "dashboard");
}

// --- Dashboard readiness polling ----------------------------------------

function waitForDashboard(timeoutMs, intervalMs) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const req = http.get(DASHBOARD_PROBE_URL, (res) => {
        res.resume(); // drain
        resolve(); // any HTTP response means the server is listening
      });
      req.on("error", () => {
        if (Date.now() >= deadline) {
          reject(new Error(`dashboard did not respond within ${timeoutMs}ms`));
        } else {
          setTimeout(attempt, intervalMs);
        }
      });
      req.setTimeout(2500, () => req.destroy(new Error("probe timeout")));
    };
    attempt();
  });
}

// --- Windows -------------------------------------------------------------

function createLoadingWindow() {
  loadingWin = new BrowserWindow({
    width: 520,
    height: 380,
    backgroundColor: "#0a0a0f",
    frame: false,
    resizable: false,
    center: true,
    show: true,
    title: "Starting Iron Jarvis…",
    webPreferences: { contextIsolation: true, nodeIntegration: false },
  });
  loadingWin.loadFile(path.join(__dirname, "loading.html"));
}

function createMainWindow() {
  mainWin = new BrowserWindow({
    width: 1440,
    height: 900,
    backgroundColor: "#0a0a0f",
    show: false,
    title: "Iron Jarvis",
    icon: path.join(__dirname, "assets", "icon.png"),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWin.once("ready-to-show", () => {
    mainWin.show();
    if (loadingWin && !loadingWin.isDestroyed()) loadingWin.close();
    loadingWin = null;
  });

  // Open target=_blank / external links in the system browser, not in-app.
  mainWin.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  // Keep navigation inside the dashboard origin; everything else → browser.
  mainWin.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith(DASHBOARD_URL) && !url.startsWith(DASHBOARD_PROBE_URL)) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  mainWin.on("closed", () => {
    mainWin = null;
  });

  mainWin.loadURL(DASHBOARD_URL);
}

// --- Auto-update (packaged builds only) ---------------------------------
// Dev mode uses the in-app git self-update (ironjarvis self-update / the
// Updates page); a packaged installer self-updates from GitHub Releases via
// electron-updater (publish config in package.json -> build.publish).

function checkForUpdates() {
  if (!IS_PACKAGED) return;
  let autoUpdater;
  try {
    ({ autoUpdater } = require("electron-updater"));
  } catch (err) {
    console.error("[update] electron-updater unavailable:", err.message);
    return;
  }
  autoUpdater.autoDownload = true;
  autoUpdater.on("error", (err) => console.error("[update] error:", err && err.message));
  autoUpdater.on("update-available", (info) =>
    console.log("[update] available:", info && info.version)
  );
  autoUpdater.on("update-downloaded", (info) => {
    const choice = dialog.showMessageBoxSync({
      type: "info",
      buttons: ["Restart now", "Later"],
      defaultId: 0,
      title: "Iron Jarvis — update ready",
      message: `Version ${info && info.version} has been downloaded.`,
      detail: "Restart to install the update.",
    });
    if (choice === 0) {
      shuttingDown = true; // ensure the daemon/dashboard children are killed
      autoUpdater.quitAndInstall();
    }
  });
  autoUpdater
    .checkForUpdatesAndNotify()
    .catch((err) => console.error("[update] check failed:", err && err.message));
}

// --- Application menu ----------------------------------------------------

function buildMenu() {
  const template = [
    {
      label: "Iron Jarvis",
      submenu: [
        { role: "reload" },
        { role: "forceReload" },
        { role: "toggleDevTools" },
        { type: "separator" },
        { role: "quit" },
      ],
    },
    { role: "editMenu" },
    {
      label: "View",
      submenu: [
        { role: "resetZoom" },
        { role: "zoomIn" },
        { role: "zoomOut" },
        { type: "separator" },
        { role: "togglefullscreen" },
      ],
    },
    { role: "windowMenu" },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

// --- Startup sequence ----------------------------------------------------

async function startup() {
  buildMenu();
  createLoadingWindow();

  if (IS_PACKAGED) {
    // PACKAGED: frozen daemon exe + standalone dashboard run by Electron's Node.
    // No Python/uv/Node/pnpm required on the user's machine.
    const stateDir = app.getPath("userData"); // writable per-user state (.ironjarvis lives here)
    // 1) Frozen daemon. Must serve on 8787 to match the build-time-baked client URL.
    daemonProc = spawnChild(
      "daemon",
      DAEMON_EXE,
      ["serve", "--host", "127.0.0.1", "--port", String(DAEMON_PORT), "--root", stateDir],
      path.dirname(DAEMON_EXE),
      {},
      false
    );
    // 2) Next.js standalone server (server.js) via Electron's bundled Node.
    dashboardProc = spawnChild(
      "dashboard",
      process.execPath,
      [DASHBOARD_SERVER],
      path.dirname(DASHBOARD_SERVER),
      {
        ELECTRON_RUN_AS_NODE: "1",
        PORT: String(DASHBOARD_PORT),
        HOSTNAME: "127.0.0.1",
        NODE_ENV: "production",
      },
      false
    );
  } else {
    // DEV: drive the repo via uv + pnpm; preflight that they're installed.
    const [hasUv, hasPnpm] = await Promise.all([
      commandExists("uv"),
      commandExists("pnpm"),
    ]);
    const missing = [];
    if (!hasUv) missing.push("uv          → https://docs.astral.sh/uv/getting-started/installation/");
    if (!hasPnpm) missing.push("pnpm        → https://pnpm.io/installation");
    if (missing.length) {
      dialog.showErrorBox(
        "Iron Jarvis — missing prerequisites",
        "Could not find the required tool(s) on your PATH:\n\n" +
          "  - " + missing.join("\n  - ") + "\n\n" +
          "Iron Jarvis (dev mode) launches the local repo's Python daemon (via uv) and\n" +
          "the Next.js dashboard (via pnpm). Install the tool(s) above, then relaunch."
      );
      shutdown();
      app.quit();
      return;
    }
    // 1) Python daemon (FastAPI on DAEMON_PORT).
    daemonProc = spawnChild(
      "daemon",
      "uv",
      ["run", "ironjarvis", "serve", "--host", "127.0.0.1", "--port", String(DAEMON_PORT), "--root", REPO_ROOT],
      REPO_ROOT
    );
    // 2) Next.js dashboard. `next start` honours the PORT env var.
    dashboardProc = spawnChild("dashboard", "pnpm", ["start"], DASHBOARD_DIR, {
      PORT: String(DASHBOARD_PORT),
    });
  }

  // 3) Wait for the dashboard, then swap the splash for the real window.
  try {
    await waitForDashboard(STARTUP_TIMEOUT_MS, 500);
  } catch (err) {
    dialog.showErrorBox(
      "Iron Jarvis — dashboard did not start",
      `The dashboard at ${DASHBOARD_PROBE_URL} did not respond within ` +
        `${Math.round(STARTUP_TIMEOUT_MS / 1000)}s.\n\n` +
        "Most common cause: the dashboard has not been built yet. Build it once:\n\n" +
        "    cd dashboard\n    pnpm install\n    pnpm build\n\n" +
        "Then relaunch Iron Jarvis. Check the terminal for [daemon]/[dashboard] logs."
    );
    shutdown();
    app.quit();
    return;
  }

  createMainWindow();
  checkForUpdates();
}

// --- App lifecycle -------------------------------------------------------

// Single-instance: a second launch focuses the existing window instead of
// spawning a duplicate daemon/dashboard pair.
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    const win = mainWin || loadingWin;
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });

  app.whenReady().then(startup);

  app.on("activate", () => {
    // macOS: re-open a window if the children are still alive.
    if (BrowserWindow.getAllWindows().length === 0 && !shuttingDown) {
      createMainWindow();
    }
  });

  app.on("window-all-closed", () => {
    shutdown();
    app.quit();
  });

  app.on("before-quit", () => {
    shutdown();
  });

  // Belt-and-suspenders: kill children if the main process is torn down.
  process.on("exit", shutdown);
  process.on("SIGINT", () => {
    shutdown();
    app.quit();
  });
  process.on("SIGTERM", () => {
    shutdown();
    app.quit();
  });
}
