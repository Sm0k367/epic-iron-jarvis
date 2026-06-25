"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import {
  Search,
  PlugZap,
  Plus,
  CornerDownLeft,
  LayoutDashboard,
  Boxes,
  Bot,
  Sparkles,
  KeyRound,
  CalendarClock,
  BrainCircuit,
  type LucideIcon,
} from "lucide-react";

interface Command {
  id: string;
  label: string;
  hint?: string;
  icon: LucideIcon;
  href: string;
  keywords?: string;
}

const COMMANDS: Command[] = [
  { id: "connect", label: "Connect a model", hint: "Connections", icon: PlugZap, href: "/connections", keywords: "llm api key oauth anthropic openai google provider" },
  { id: "new-session", label: "New session", hint: "Run an agent", icon: Plus, href: "/sessions", keywords: "run task agent start" },
  { id: "overview", label: "Overview", icon: LayoutDashboard, href: "/", keywords: "home dashboard health metrics" },
  { id: "sessions", label: "Sessions", icon: Boxes, href: "/sessions" },
  { id: "agents", label: "Agents", icon: Bot, href: "/agents" },
  { id: "skills", label: "Skills", icon: Sparkles, href: "/skills" },
  { id: "memory", label: "Memory", icon: BrainCircuit, href: "/memory" },
  { id: "schedules", label: "Schedules", icon: CalendarClock, href: "/schedules" },
  { id: "secrets", label: "Secrets", icon: KeyRound, href: "/secrets" },
];

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // ⌘K / Ctrl+K toggles; Esc closes.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
      // focus after the panel mounts
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return COMMANDS;
    return COMMANDS.filter((c) =>
      `${c.label} ${c.hint ?? ""} ${c.keywords ?? ""}`.toLowerCase().includes(q),
    );
  }, [query]);

  useEffect(() => {
    setActive(0);
  }, [query]);

  function run(cmd: Command | undefined) {
    if (!cmd) return;
    setOpen(false);
    router.push(cmd.href);
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 px-4 pt-[14vh] backdrop-blur-sm"
          onClick={() => setOpen(false)}
        >
          <motion.div
            initial={{ opacity: 0, y: -10, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.98 }}
            transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
            className="w-full max-w-xl overflow-hidden rounded-2xl border border-white/10 bg-ink-850/95 shadow-card-hover backdrop-blur-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3 border-b hairline px-4 py-3">
              <Search size={16} className="text-accent-soft/80" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "ArrowDown") {
                    e.preventDefault();
                    setActive((a) => Math.min(a + 1, results.length - 1));
                  } else if (e.key === "ArrowUp") {
                    e.preventDefault();
                    setActive((a) => Math.max(a - 1, 0));
                  } else if (e.key === "Enter") {
                    e.preventDefault();
                    run(results[active]);
                  }
                }}
                placeholder="Search or jump to…"
                className="flex-1 bg-transparent text-sm text-zinc-100 outline-none placeholder:text-zinc-600"
              />
              <kbd className="rounded border border-white/10 bg-white/[0.04] px-1.5 py-0.5 text-[10px] font-medium text-zinc-500">
                esc
              </kbd>
            </div>
            <div className="max-h-80 overflow-y-auto p-2">
              {results.length === 0 ? (
                <div className="px-3 py-6 text-center text-sm text-zinc-500">
                  No matches.
                </div>
              ) : (
                results.map((c, i) => {
                  const Icon = c.icon;
                  const on = i === active;
                  return (
                    <button
                      key={c.id}
                      onMouseEnter={() => setActive(i)}
                      onClick={() => run(c)}
                      className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition-colors ${
                        on ? "bg-accent/[0.1] text-accent-soft" : "text-zinc-300 hover:bg-white/[0.04]"
                      }`}
                    >
                      <Icon size={16} className={on ? "text-accent" : "text-zinc-500"} />
                      <span className="flex-1 font-medium">{c.label}</span>
                      {c.hint && <span className="text-[11px] text-zinc-500">{c.hint}</span>}
                      {on && <CornerDownLeft size={13} className="text-accent-soft/70" />}
                    </button>
                  );
                })
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
