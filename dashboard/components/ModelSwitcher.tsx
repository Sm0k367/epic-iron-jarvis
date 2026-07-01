"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Cpu, Check, PlugZap, ChevronDown } from "lucide-react";
import { usePolledApi, useApi } from "@/lib/useApi";
import { put, ApiError } from "@/lib/api";
import type { Health, ModelOption } from "@/lib/types";

/**
 * Topbar provider/model switcher — set the ACTIVE default model in one click,
 * across every connected account (beyond the per-session dropdown). Reuses
 * /health (current default + availability) + /models (catalog) and persists the
 * choice via PUT /settings. Opens on the global `ij:open-switcher` event (the
 * ⌘K palette dispatches it).
 */
export function ModelSwitcher() {
  const health = usePolledApi<Health>("/health", 5000);
  const modelsData = useApi<{ models: ModelOption[] }>("/models");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  const h = health.data;
  const models = useMemo(() => modelsData.data?.models ?? [], [modelsData.data]);
  const avail = useMemo(() => {
    const m = new Map<string, boolean>();
    for (const p of h?.providers ?? []) m.set(p.provider, p.available);
    return m;
  }, [h]);

  // Open via a global event so ⌘K can summon it from anywhere.
  useEffect(() => {
    const onOpen = () => setOpen(true);
    window.addEventListener("ij:open-switcher", onOpen);
    return () => window.removeEventListener("ij:open-switcher", onOpen);
  }, []);

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function choose(m: ModelOption) {
    const key = `${m.provider}|${m.model}`;
    setBusy(key);
    setErr(null);
    try {
      await put("/settings", {
        values: { default_provider: m.provider, default_model: m.model },
      });
      await health.reload?.();
      setOpen(false);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  if (!h) return null; // until /health loads (the offline banner covers downtime)

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-xs text-zinc-300 transition-colors hover:border-white/20"
        title="Switch the active model"
        aria-label="Switch the active model"
      >
        <Cpu size={13} className="text-accent-soft" />
        <span className="hidden max-w-[150px] truncate font-mono text-[11px] sm:inline">
          {h.default_model}
        </span>
        <ChevronDown size={12} className="text-zinc-500" />
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-1.5 w-72 rounded-xl border border-white/10 bg-ink-950/95 p-1.5 shadow-card-hover backdrop-blur-xl">
          <div className="px-2 py-1.5 text-[10px] uppercase tracking-wider text-zinc-400">
            Active model
          </div>
          <div className="max-h-80 overflow-y-auto">
            {models.length === 0 ? (
              <div className="px-2 py-2 text-[11px] text-zinc-500">No models.</div>
            ) : (
              models.map((m) => {
                const active =
                  m.provider === h.default_provider && m.model === h.default_model;
                const ok = avail.get(m.provider) ?? false;
                const key = `${m.provider}|${m.model}`;
                return (
                  <button
                    key={key}
                    onClick={() => ok && choose(m)}
                    disabled={!ok || busy === key}
                    className={`flex w-full items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left text-xs transition-colors ${
                      ok ? "hover:bg-white/[0.06]" : "cursor-not-allowed opacity-40"
                    } ${active ? "bg-accent/[0.1]" : ""}`}
                  >
                    <span className="min-w-0">
                      <span className="block truncate font-mono text-[11px] text-zinc-200">
                        {m.model}
                      </span>
                      <span className="text-[10px] text-zinc-500">
                        {m.provider}
                        {!ok && " · not connected"}
                      </span>
                    </span>
                    {active && <Check size={13} className="text-accent-soft" />}
                  </button>
                );
              })
            )}
          </div>
          {err && <div className="px-2 py-1.5 text-[11px] text-rose-300">{err}</div>}
          <Link
            href="/connections"
            onClick={() => setOpen(false)}
            className="mt-1 flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[11px] text-accent-soft transition-colors hover:bg-white/[0.04]"
          >
            <PlugZap size={12} /> Connect another account…
          </Link>
        </div>
      )}
    </div>
  );
}
