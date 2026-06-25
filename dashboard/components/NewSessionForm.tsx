"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Play, Cpu, PlugZap, ArrowRight } from "lucide-react";
import { post, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import type { SessionView, ModelOption, Health } from "@/lib/types";
import { ErrorNote, LoaderInline } from "./ui";
import { VoiceInput, appendDictation } from "./VoiceInput";

const AGENT_TYPES = ["builder", "supervisor", "planner", "researcher", "reviewer"];

/** A stable "provider|model" key used as the <select> value. */
const optKey = (m: ModelOption) => `${m.provider}|${m.model}`;

export function NewSessionForm({ onCreated }: { onCreated?: () => void }) {
  const router = useRouter();
  const { data: modelsData } = useApi<{ models: ModelOption[] }>("/models");
  const { data: health } = useApi<Health>("/health");

  const [task, setTask] = useState("");
  const [agentType, setAgentType] = useState("builder");
  const [choice, setChoice] = useState(""); // "provider|model" or "" => default
  const [wait, setWait] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const models = useMemo(() => modelsData?.models ?? [], [modelsData]);

  // Which providers are actually available (from /health)?
  const availability = useMemo(() => {
    const map = new Map<string, boolean>();
    for (const p of health?.providers ?? []) map.set(p.provider, p.available);
    return map;
  }, [health]);

  const isAvailable = (m: ModelOption) => availability.get(m.provider) ?? false;

  // True when no *real* (non-mock) provider is connected — mock still works.
  const onlyMock = useMemo(() => {
    const reals = (health?.providers ?? []).filter(
      (p) => p.provider !== "mock" && p.class !== "mock",
    );
    return reals.length === 0 || reals.every((p) => !p.available);
  }, [health]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!task.trim()) return;
    setBusy(true);
    setError(null);
    const [provider, model] = choice ? choice.split("|") : ["", ""];
    try {
      const session = await post<SessionView>("/sessions", {
        task: task.trim(),
        agent_type: agentType,
        provider: provider || undefined,
        model: model || undefined,
        wait,
      });
      setTask("");
      onCreated?.();
      if (session?.id) router.push(`/sessions/${session.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3.5">
      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <label className="block text-[11px] uppercase tracking-[0.1em] text-zinc-500">
            Task
          </label>
          <VoiceInput
            size="sm"
            onTranscript={(chunk) => setTask((p) => appendDictation(p, chunk))}
          />
        </div>
        <textarea
          value={task}
          onChange={(e) => setTask(e.target.value)}
          rows={3}
          placeholder="Describe what the agent should do… or dictate with the mic"
          className="field resize-y"
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1.5 block text-[11px] uppercase tracking-[0.1em] text-zinc-500">
            Agent type
          </label>
          <select
            value={agentType}
            onChange={(e) => setAgentType(e.target.value)}
            className="field"
          >
            {AGENT_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1.5 flex items-center gap-1.5 text-[11px] uppercase tracking-[0.1em] text-zinc-500">
            <Cpu size={12} /> Model
          </label>
          <select
            value={choice}
            onChange={(e) => setChoice(e.target.value)}
            className="field"
          >
            <option value="">
              {health
                ? `Default · ${health.default_provider} / ${health.default_model}`
                : "Default"}
            </option>
            {models.map((m) => {
              const avail = isAvailable(m);
              return (
                <option key={optKey(m)} value={optKey(m)} disabled={!avail}>
                  {m.provider} · {m.model}
                  {avail ? "" : " — not connected"}
                </option>
              );
            })}
          </select>
        </div>
      </div>

      {onlyMock && (
        <Link
          href="/connections"
          className="flex items-center gap-2 rounded-xl border border-amber-500/20 bg-amber-500/[0.05] px-3 py-2 text-[11px] text-amber-100/80 transition-colors hover:bg-amber-500/[0.1]"
        >
          <PlugZap size={13} className="shrink-0 text-amber-300" />
          <span>
            Running on the built-in offline model.{" "}
            <span className="font-medium text-accent-soft">Connect a real model</span>
          </span>
          <ArrowRight size={12} className="ml-auto shrink-0 text-amber-300/70" />
        </Link>
      )}

      <div className="flex items-center justify-between">
        <label className="flex items-center gap-2 text-sm text-zinc-400">
          <input
            type="checkbox"
            checked={wait}
            onChange={(e) => setWait(e.target.checked)}
            className="h-4 w-4 accent-[#22d3ee]"
          />
          Wait for completion
        </label>
        <button type="submit" disabled={busy || !task.trim()} className="btn-accent">
          {busy ? <LoaderInline label="Running…" /> : <><Play size={14} /> Run session</>}
        </button>
      </div>

      {error && <ErrorNote>{error}</ErrorNote>}
    </form>
  );
}
