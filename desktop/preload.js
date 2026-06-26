// Iron Jarvis — preload (runs in an isolated context with limited Node access).
// Exposes a tiny, read-only surface to the dashboard renderer.
const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("ironjarvis", {
  // Lets the dashboard detect it's running inside the desktop shell.
  isDesktop: true,
  version: process.versions.electron,
});
