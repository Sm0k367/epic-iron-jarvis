"use client";

import { useState } from "react";
import { Sparkles, BookOpen, Plus, Save } from "lucide-react";
import { useApi } from "@/lib/useApi";
import { post, ApiError } from "@/lib/api";
import type { Skill, SkillDetail } from "@/lib/types";
import {
  Card,
  Spinner,
  OfflineHint,
  Empty,
  SkeletonRows,
  SuccessNote,
  ErrorNote,
  LoaderInline,
} from "@/components/ui";
import { PageHeader } from "@/components/PageHeader";
import { PageShell, Reveal } from "@/components/motion";

export default function SkillsPage() {
  const { data, error, loading, reload } = useApi<{ skills: Skill[] }>("/skills");
  const [selected, setSelected] = useState<string | null>(null);
  const detail = useApi<SkillDetail>(selected ? `/skills/${selected}` : null, [selected]);

  // --- New-skill form state -------------------------------------------------
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [created, setCreated] = useState<string | null>(null);

  const offline = error && error.status === 0;
  const skills = data?.skills ?? [];
  const canSubmit = !busy && name.trim().length > 0 && instructions.trim().length > 0;

  function resetForm() {
    setName("");
    setDescription("");
    setInstructions("");
    setFormError(null);
  }

  async function createSkill(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setFormError(null);
    setCreated(null);
    try {
      await post("/skills", {
        name: name.trim(),
        description: description.trim(),
        instructions: instructions.trim(),
      });
      setCreated(name.trim());
      setShowForm(false);
      resetForm();
      reload();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageShell>
      <Reveal>
        <PageHeader
          title="Skills"
          subtitle="Reusable skills your agents can call on to handle specialized tasks faster."
          actions={
            <button
              onClick={() => {
                setShowForm((v) => !v);
                setCreated(null);
                setFormError(null);
              }}
              className={`${showForm ? "btn-ghost" : "btn-accent"} py-1.5 text-xs`}
            >
              <Plus size={14} /> New skill
            </button>
          }
        />
      </Reveal>
      {offline && (
        <Reveal>
          <OfflineHint />
        </Reveal>
      )}

      {created && !showForm && (
        <Reveal>
          <SuccessNote>Skill &ldquo;{created}&rdquo; created.</SuccessNote>
        </Reveal>
      )}

      <Reveal>
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-1">
            {showForm && (
              <Card title="New skill" icon={<Plus size={15} />}>
                <form onSubmit={createSkill} className="space-y-3">
                  <div className="space-y-1.5">
                    <label className="text-[11px] font-medium uppercase tracking-[0.12em] text-zinc-400">
                      Name
                    </label>
                    <input
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="e.g. summarize-pdf"
                      aria-label="Skill name"
                      autoComplete="off"
                      autoFocus
                      className="field text-sm"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-[11px] font-medium uppercase tracking-[0.12em] text-zinc-400">
                      Description
                    </label>
                    <input
                      type="text"
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      placeholder="One line on when to use it"
                      aria-label="Skill description"
                      autoComplete="off"
                      className="field text-sm"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-[11px] font-medium uppercase tracking-[0.12em] text-zinc-400">
                      Instructions
                    </label>
                    <textarea
                      value={instructions}
                      onChange={(e) => setInstructions(e.target.value)}
                      placeholder={"# How to…\n\nStep-by-step guidance the agent follows."}
                      aria-label="Skill instructions"
                      rows={8}
                      className="field font-mono text-xs leading-relaxed"
                    />
                    <p className="text-[11px] leading-relaxed text-zinc-500">
                      Instructions are what an agent reads when it uses this skill — write
                      them like a how-to.
                    </p>
                  </div>
                  {formError && <ErrorNote>{formError}</ErrorNote>}
                  <div className="flex items-center gap-2">
                    <button
                      type="submit"
                      disabled={!canSubmit}
                      className="btn-accent flex-1 py-1.5 text-xs"
                    >
                      {busy ? (
                        <LoaderInline label="Creating…" />
                      ) : (
                        <>
                          <Save size={14} /> Create skill
                        </>
                      )}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setShowForm(false);
                        resetForm();
                      }}
                      className="btn-ghost py-1.5 text-xs"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              </Card>
            )}

            <Card title={`Available · ${skills.length}`} icon={<Sparkles size={15} />}>
              {loading && !data ? (
                <SkeletonRows rows={5} />
              ) : skills.length === 0 ? (
                <Empty icon={<Sparkles size={22} />}>No skills.</Empty>
              ) : (
                <ul className="space-y-1">
                  {skills.map((s) => (
                    <li key={s.name}>
                      <button
                        onClick={() => setSelected(s.name)}
                        className={`w-full rounded-xl border px-3 py-2.5 text-left text-sm transition-colors ${
                          selected === s.name
                            ? "border-accent/30 bg-accent/[0.08] text-accent-soft"
                            : "border-transparent text-zinc-300 hover:border-white/10 hover:bg-white/[0.04]"
                        }`}
                      >
                        <div className="font-medium">{s.name}</div>
                        <div className="truncate text-xs text-zinc-500">{s.description}</div>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          <div className="lg:col-span-2">
            <Card title={selected ?? "Instructions"} icon={<BookOpen size={15} />}>
              {!selected ? (
                <Empty icon={<BookOpen size={22} />}>Select a skill to view its instructions.</Empty>
              ) : detail.loading && !detail.data ? (
                <Spinner />
              ) : detail.data ? (
                <div className="space-y-3">
                  <p className="text-sm text-zinc-400">{detail.data.description}</p>
                  <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-xl border border-white/[0.06] bg-ink-950 p-4 text-xs leading-relaxed text-zinc-300">
                    {detail.data.instructions}
                  </pre>
                </div>
              ) : (
                <Empty>Could not load skill.</Empty>
              )}
            </Card>
          </div>
        </div>
      </Reveal>
    </PageShell>
  );
}
