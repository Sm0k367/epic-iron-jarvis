# Iron Jarvis Desktop — assets

`icon.png` is a **placeholder** application icon: a 256×256 RGBA PNG with a dark
background and a crimson "arc-reactor" core (matches the Iron Jarvis splash).

It is referenced by:

- `main.js` → `BrowserWindow({ icon: assets/icon.png })`
- `package.json` → `build.win.icon`

To ship a real brand icon, replace `icon.png` with a **256×256 (or larger)**
PNG. `electron-builder` will convert it to `.ico` automatically for the Windows
NSIS installer. (You can also drop in a prebuilt `icon.ico` and point
`build.win.icon` at it.)

Nothing here fails the build if the icon is missing — Electron falls back to its
default window icon — but keeping a valid PNG here means `pnpm dist` produces a
branded installer out of the box.
