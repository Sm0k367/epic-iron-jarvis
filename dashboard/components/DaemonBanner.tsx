"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ServerCrash, ShieldAlert, X, RefreshCw } from "lucide-react";
import Link from "next/link";
import { API_BASE } from "@/lib/api";
import { useDaemon } from "@/lib/daemon";

/** The port the dashboard is pointed at, surfaced in the "start it" hint. */
function apiPort(): string {
  try {
    return new URL(API_BASE).port || "8787";
  } catch {
    return "8787";
  }
}

/**
 * A single, app-wide banner shown when the daemon can't be reached. Dismissible
 * for the current view; reappears on the next route load if still offline.
 */
export function DaemonBanner() {
  const { online, unauthorized, checking } = useDaemon();
  const [dismissed, setDismissed] = useState(false);
  const port = apiPort();

  // Dismiss lasts only until the daemon state clears — a fresh problem re-shows the
  // banner (the App Router root layout never remounts, so a plain flag was sticky
  // for the whole session).
  useEffect(() => {
    if (online && !unauthorized) setDismissed(false);
  }, [online, unauthorized]);

  const showOffline = !checking && !online && !dismissed;
  // Daemon is reachable but rejecting our token — a distinct, actionable state.
  const showAuth = !checking && online && unauthorized && !dismissed;

  return (
    <AnimatePresence>
      {showOffline && (
        <motion.div
          role="status"
          aria-live="polite"
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
          className="overflow-hidden border-b border-amber-500/25 bg-amber-500/[0.08] backdrop-blur-sm"
        >
          <div className="flex items-center gap-3 px-6 py-2.5 lg:px-10">
            <ServerCrash size={16} className="shrink-0 text-amber-300" aria-hidden="true" />
            <div className="min-w-0 flex-1 text-sm text-amber-100/90">
              <span className="font-semibold text-amber-200">Daemon offline.</span>{" "}
              <span className="text-amber-100/70">
                Start it with{" "}
                <code className="rounded bg-black/40 px-1.5 py-0.5 font-mono text-xs text-amber-100/90">
                  uv run ironjarvis serve --port {port} --root .
                </code>
              </span>
            </div>
            <button
              onClick={() => window.location.reload()}
              aria-label="Retry connection"
              className="flex shrink-0 items-center gap-1.5 rounded-lg border border-amber-500/30 px-2.5 py-1 text-xs font-medium text-amber-200 transition-colors hover:bg-amber-500/15"
            >
              <RefreshCw size={12} aria-hidden="true" /> Retry
            </button>
            <button
              onClick={() => setDismissed(true)}
              aria-label="Dismiss offline banner"
              className="shrink-0 rounded-lg p-1 text-amber-300/70 transition-colors hover:bg-amber-500/15 hover:text-amber-200"
            >
              <X size={15} aria-hidden="true" />
            </button>
          </div>
        </motion.div>
      )}
      {showAuth && (
        <motion.div
          role="alert"
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
          className="overflow-hidden border-b border-rose-500/25 bg-rose-500/[0.08] backdrop-blur-sm"
        >
          <div className="flex items-center gap-3 px-6 py-2.5 lg:px-10">
            <ShieldAlert size={16} className="shrink-0 text-rose-300" aria-hidden="true" />
            <div className="min-w-0 flex-1 text-sm text-rose-100/90">
              <span className="font-semibold text-rose-200">Daemon rejected your token.</span>{" "}
              <span className="text-rose-100/70">
                The daemon is running but your access token is missing or stale — data
                below may look empty. Re-enter it to reconnect.
              </span>
            </div>
            <Link
              href="/settings"
              className="flex shrink-0 items-center gap-1.5 rounded-lg border border-rose-500/30 px-2.5 py-1 text-xs font-medium text-rose-200 transition-colors hover:bg-rose-500/15"
            >
              Enter token
            </Link>
            <button
              onClick={() => setDismissed(true)}
              aria-label="Dismiss token banner"
              className="shrink-0 rounded-lg p-1 text-rose-300/70 transition-colors hover:bg-rose-500/15 hover:text-rose-200"
            >
              <X size={15} aria-hidden="true" />
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
