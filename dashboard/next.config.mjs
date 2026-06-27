/** @type {import('next').NextConfig} */
const nextConfig = {
  // Bundle a minimal self-contained Node server at .next/standalone/server.js so
  // the dashboard (incl. the dynamic `ƒ /sessions/[id]` route) can run WITHOUT a
  // separate Node/pnpm install at runtime — Electron runs it via its bundled Node.
  // A pure static export ("output: 'export'") cannot serve that dynamic route.
  output: "standalone",
  // Lint is run separately; never let it block the production build proof.
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
