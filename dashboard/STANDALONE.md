# Iron Jarvis Dashboard — Standalone Build (for Electron packaging)

The dashboard is configured for Next.js **standalone output** (`output: "standalone"`
in `next.config.mjs`). This bundles a minimal self-contained Node server at
`.next/standalone/server.js` together with a trimmed `node_modules`, so the
dashboard runs with **NO separate Node/npm install at runtime** — Electron starts
it with its bundled Node.

Standalone (not static export) is required because the app has one dynamic,
server-rendered route — `ƒ /sessions/[id]` — which a pure `output: "export"`
static build cannot serve.

## 1. Build command

```sh
cd dashboard
npm run build
```

Produces:

```
dashboard/.next/
├── standalone/
│   ├── server.js          # minimal Node HTTP server (entrypoint)
│   ├── package.json
│   ├── node_modules/      # only the deps the server actually needs
│   └── .next/             # server manifests + compiled server code
│                          #   NOTE: does NOT contain ./static (see step 2)
└── static/                # client JS/CSS chunks — served at /_next/static/*
```

## 2. Packaging copy steps (REQUIRED)

Next standalone deliberately does **not** copy `.next/static` or `public/` into the
standalone folder. The packager (Electron build script) must place them next to
`server.js` so the running server can serve client chunks and static assets:

```sh
# from dashboard/
cp -r .next/static   .next/standalone/.next/static     # client JS/CSS chunks  (REQUIRED)
cp -r public         .next/standalone/public           # static assets         (only if a public/ dir exists)
```

> As of this build there is **no `public/` directory** in the dashboard, so the
> second copy is a no-op today — keep it in the packager script so it keeps
> working if static assets are added later.

After copying, the self-contained tree to ship is just `.next/standalone/`
(which now contains `server.js`, `node_modules/`, `.next/`, `.next/static/`,
and optionally `public/`).

## 3. Run command + env vars (what Electron does)

```sh
# cwd = the standalone root (the folder that holds server.js)
PORT=3000 HOSTNAME=127.0.0.1 node server.js
```

`server.js` reads these env vars:

| Env var            | Default     | Electron sets |
|--------------------|-------------|---------------|
| `PORT`             | `3000`      | `3000`        |
| `HOSTNAME`         | `0.0.0.0`   | `127.0.0.1`   |
| `KEEP_ALIVE_TIMEOUT` (optional) | Node default | — |

(Confirmed in `.next/standalone/server.js`:
`const currentPort = parseInt(process.env.PORT, 10) || 3000` and
`const hostname = process.env.HOSTNAME || '0.0.0.0'`.)

Electron then loads the UI from `http://127.0.0.1:3000`.

## 4. API base + auth token (important caveat)

The dashboard talks to the bundled Iron Jarvis daemon. The base URL comes from
`lib/api.ts`:

```ts
export const API_BASE = (process.env.NEXT_PUBLIC_IJ_API || "http://127.0.0.1:8787")...
```

- **`NEXT_PUBLIC_IJ_API` defaults to `http://127.0.0.1:8787`** (the bundled daemon).
- **CAVEAT — baked at build time.** Any env var prefixed `NEXT_PUBLIC_*` is inlined
  into the client bundle during `npm run build`. Setting it at runtime has **no
  effect**; to point the dashboard at a different daemon URL you must rebuild.
  For the standard Electron packaging (daemon on `127.0.0.1:8787`) the default is
  correct and nothing needs to be set.
- **Runtime daemon token still works.** The auth token is resolved at runtime from
  `localStorage` (the Connections/login box, key `ij_token`) and wins over the
  build-time `NEXT_PUBLIC_IJ_TOKEN`. So you can log into a token-protected daemon
  WITHOUT a rebuild — only the API *base URL* is fixed at build time.

## 5. Notes

- `.next/` is already gitignored (`/.next` in `dashboard/.gitignore`), so the build
  output is not committed.
- `.npmrc` pins `node-linker=hoisted`, which keeps the standalone `node_modules`
  flat — required for Next App Router production to work correctly under npm.
