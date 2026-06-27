// Iron Jarvis — desktop window-state persistence (CommonJS).
//
// Small, dependency-free helpers (fs + path only, NO electron) so the desktop
// window remembers its size/position across launches. The caller (main.js)
// supplies the userData directory and the list of connected displays (from the
// electron `screen` module, which is only valid after app-ready); keeping the
// `screen` access out of this module lets it be required at top level and
// `node --check`ed in isolation.

const fs = require("fs");
const path = require("path");

// Sensible default for a first launch (or when the saved state is unusable):
// the same 1440x900 the app shipped with, centered (no x/y => caller centers).
const DEFAULT_BOUNDS = { width: 1440, height: 900 };

// Hard floors so a corrupt/teeny saved size can never produce an unusable window.
const MIN_WIDTH = 800;
const MIN_HEIGHT = 560;

function stateFile(userDataDir) {
  return path.join(userDataDir, "window-state.json");
}

// Read the persisted bounds, or null when missing/corrupt/unreasonable.
// Returns { width, height, x?, y? } — x/y are only included when both are finite.
function loadBounds(userDataDir) {
  let data;
  try {
    data = JSON.parse(fs.readFileSync(stateFile(userDataDir), "utf8"));
  } catch {
    return null; // not created yet / unreadable / invalid JSON
  }
  const b = data && data.bounds;
  if (
    !b ||
    !Number.isFinite(b.width) ||
    !Number.isFinite(b.height) ||
    b.width < MIN_WIDTH ||
    b.height < MIN_HEIGHT
  ) {
    return null;
  }
  const out = { width: Math.round(b.width), height: Math.round(b.height) };
  if (Number.isFinite(b.x) && Number.isFinite(b.y)) {
    out.x = Math.round(b.x);
    out.y = Math.round(b.y);
  }
  return out;
}

// Persist the bounds (best-effort; failures are swallowed so a read-only
// userData dir can never crash the app).
function saveBounds(userDataDir, bounds) {
  if (!bounds || !Number.isFinite(bounds.width) || !Number.isFinite(bounds.height)) {
    return;
  }
  const payload = {
    bounds: {
      width: Math.round(bounds.width),
      height: Math.round(bounds.height),
      x: Number.isFinite(bounds.x) ? Math.round(bounds.x) : undefined,
      y: Number.isFinite(bounds.y) ? Math.round(bounds.y) : undefined,
    },
    savedAt: new Date().toISOString(),
  };
  try {
    fs.writeFileSync(stateFile(userDataDir), JSON.stringify(payload, null, 2), "utf8");
  } catch {
    /* non-fatal */
  }
}

// Is the rectangle visible enough on SOME connected display that the user can
// grab its title bar? Guards against restoring a window onto a monitor that has
// since been unplugged (saved x/y now far off-screen). `displays` is the array
// from electron's screen.getAllDisplays(). When bounds has no x/y we return
// false so the caller centers it on the primary display.
function isVisibleOnDisplay(bounds, displays) {
  if (!bounds || !Number.isFinite(bounds.x) || !Number.isFinite(bounds.y)) {
    return false;
  }
  if (!Array.isArray(displays) || displays.length === 0) {
    return false;
  }
  return displays.some((d) => {
    const wa = (d && d.workArea) || {};
    if (
      !Number.isFinite(wa.x) ||
      !Number.isFinite(wa.y) ||
      !Number.isFinite(wa.width) ||
      !Number.isFinite(wa.height)
    ) {
      return false;
    }
    const overlapX =
      Math.min(bounds.x + bounds.width, wa.x + wa.width) - Math.max(bounds.x, wa.x);
    const overlapY =
      Math.min(bounds.y + bounds.height, wa.y + wa.height) - Math.max(bounds.y, wa.y);
    // Require a grabbable strip of the window to be on-screen.
    return overlapX > 120 && overlapY > 48;
  });
}

module.exports = {
  DEFAULT_BOUNDS,
  MIN_WIDTH,
  MIN_HEIGHT,
  loadBounds,
  saveBounds,
  isVisibleOnDisplay,
};
