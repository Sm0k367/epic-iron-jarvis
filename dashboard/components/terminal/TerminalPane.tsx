"use client";

// A single live terminal pane: an xterm.js terminal attached over a WebSocket
// to one daemon shell session. xterm itself is imported dynamically inside the
// effect so it never runs during SSR / `next build`.

import { useEffect, useRef, useState } from "react";
import "@xterm/xterm/css/xterm.css";
import { Loader2, Plug, PlugZap, Terminal as TerminalIcon, X } from "lucide-react";
import { wsUrl } from "@/lib/api";
import type { TerminalInfo } from "@/lib/types";

type ConnState = "connecting" | "open" | "reconnecting" | "closed";

/** xterm theme tuned to the arc-reactor cyan / near-black aesthetic. */
const XTERM_THEME = {
  background: "#0a0c11",
  foreground: "#cdd3df",
  cursor: "#22d3ee",
  cursorAccent: "#0a0c11",
  selectionBackground: "rgba(34,211,238,0.28)",
  black: "#0b0d11",
  red: "#fb7185",
  green: "#34d399",
  yellow: "#fbbf24",
  blue: "#38bdf8",
  magenta: "#a78bfa",
  cyan: "#22d3ee",
  white: "#cdd3df",
  brightBlack: "#475569",
  brightRed: "#fda4af",
  brightGreen: "#6ee7b7",
  brightYellow: "#fcd34d",
  brightBlue: "#7dd3fc",
  brightMagenta: "#c4b5fd",
  brightCyan: "#67e8f9",
  brightWhite: "#f4f4f5",
} as const;

export function TerminalPane({
  info,
  focused,
  onFocus,
  onClose,
}: {
  info: TerminalInfo;
  focused: boolean;
  onFocus: () => void;
  onClose: () => void;
}) {
  const holderRef = useRef<HTMLDivElement | null>(null);
  const [state, setState] = useState<ConnState>("connecting");

  useEffect(() => {
    const holder = holderRef.current;
    if (!holder || typeof window === "undefined") return;

    let disposed = false;
    let term: import("@xterm/xterm").Terminal | null = null;
    let fit: import("@xterm/addon-fit").FitAddon | null = null;
    let ws: WebSocket | null = null;
    let ro: ResizeObserver | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let attempts = 0;

    const doFit = () => {
      try {
        fit?.fit();
      } catch {
        /* container not measurable yet */
      }
    };

    const sendResize = () => {
      if (ws && ws.readyState === WebSocket.OPEN && term) {
        ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
      }
    };

    const onWinResize = () => {
      doFit();
      sendResize();
    };

    const connect = () => {
      ws = new WebSocket(wsUrl(`/terminals/${info.id}/ws`));
      ws.binaryType = "arraybuffer";
      ws.onopen = () => {
        attempts = 0;
        setState("open");
        doFit();
        sendResize();
        term?.focus();
      };
      ws.onmessage = (ev: MessageEvent) => {
        if (!term) return;
        // Server -> client: PTY output as binary (ArrayBuffer); text just in case.
        if (typeof ev.data === "string") term.write(ev.data);
        else term.write(new Uint8Array(ev.data as ArrayBuffer));
      };
      ws.onclose = () => {
        if (disposed) return;
        if (attempts < 4) {
          attempts += 1;
          setState("reconnecting");
          reconnectTimer = setTimeout(connect, 500 * attempts);
        } else {
          setState("closed");
        }
      };
      ws.onerror = () => {
        try {
          ws?.close();
        } catch {
          /* noop */
        }
      };
    };

    (async () => {
      const [{ Terminal }, { FitAddon }] = await Promise.all([
        import("@xterm/xterm"),
        import("@xterm/addon-fit"),
      ]);
      if (disposed) return;

      term = new Terminal({
        cursorBlink: true,
        cursorStyle: "bar",
        fontSize: 12.5,
        lineHeight: 1.15,
        fontFamily:
          'ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace',
        theme: { ...XTERM_THEME },
        scrollback: 5000,
        allowProposedApi: true,
      });
      fit = new FitAddon();
      term.loadAddon(fit);
      term.open(holder);
      doFit();

      // Client -> server: raw keystrokes as text.
      term.onData((d: string) => {
        if (ws && ws.readyState === WebSocket.OPEN) ws.send(d);
      });

      ro = new ResizeObserver(() => {
        doFit();
        sendResize();
      });
      ro.observe(holder);
      window.addEventListener("resize", onWinResize);

      setState("connecting");
      connect();
    })();

    return () => {
      disposed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      window.removeEventListener("resize", onWinResize);
      ro?.disconnect();
      try {
        ws?.close();
      } catch {
        /* noop */
      }
      try {
        term?.dispose();
      } catch {
        /* noop */
      }
    };
    // Re-wire only when the session id changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [info.id]);

  return (
    <div
      onMouseDown={onFocus}
      className={`group flex h-full flex-col overflow-hidden rounded-2xl border bg-[#0a0c11] shadow-card transition-colors ${
        focused
          ? "border-accent/50 shadow-glow-sm ring-1 ring-accent/30"
          : "border-white/[0.07] hover:border-white/[0.14]"
      }`}
    >
      {/* Pane header: shell · cwd · connection state · close */}
      <header className="flex shrink-0 items-center gap-2 border-b border-white/[0.06] bg-ink-900/60 px-3 py-2">
        <TerminalIcon
          size={13}
          className={focused ? "text-accent" : "text-zinc-500"}
        />
        <span className="shrink-0 font-mono text-[11px] font-semibold text-zinc-200">
          {info.shell}
        </span>
        <span
          className="min-w-0 flex-1 truncate font-mono text-[11px] text-zinc-500"
          title={info.cwd}
        >
          {info.cwd}
        </span>
        <ConnPill state={state} />
        <button
          onClick={(e) => {
            e.stopPropagation();
            onClose();
          }}
          title="Close terminal"
          className="grid h-5 w-5 shrink-0 place-items-center rounded-md text-zinc-500 transition-colors hover:bg-rose-500/15 hover:text-rose-300"
        >
          <X size={13} />
        </button>
      </header>

      {/* Terminal surface */}
      <div className="relative flex-1 overflow-hidden px-2 py-1.5">
        <div ref={holderRef} className="h-full w-full" />
        {(state === "reconnecting" || state === "closed") && (
          <div className="pointer-events-none absolute inset-0 grid place-items-center bg-[#0a0c11]/70 backdrop-blur-[1px]">
            <div
              className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-medium ${
                state === "reconnecting"
                  ? "border-amber-500/30 bg-amber-500/10 text-amber-200"
                  : "border-rose-500/30 bg-rose-500/10 text-rose-200"
              }`}
            >
              {state === "reconnecting" ? (
                <>
                  <Loader2 size={13} className="animate-spin" /> Reconnecting…
                </>
              ) : (
                <>
                  <Plug size={13} /> Session closed
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ConnPill({ state }: { state: ConnState }) {
  if (state === "open") {
    return (
      <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-emerald-500/25 bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-medium text-emerald-300">
        <PlugZap size={9} /> live
      </span>
    );
  }
  if (state === "closed") {
    return (
      <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-rose-500/25 bg-rose-500/10 px-1.5 py-0.5 text-[9px] font-medium text-rose-300">
        <Plug size={9} /> closed
      </span>
    );
  }
  return (
    <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-amber-500/25 bg-amber-500/10 px-1.5 py-0.5 text-[9px] font-medium text-amber-300">
      <Loader2 size={9} className="animate-spin" />
      {state === "reconnecting" ? "reconnecting" : "connecting"}
    </span>
  );
}
