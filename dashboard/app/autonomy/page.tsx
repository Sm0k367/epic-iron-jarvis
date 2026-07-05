"use client";

import { useState } from "react";
import {
  Activity,
  Target,
  Inbox,
  Plus,
  ShieldAlert,
  ShieldCheck,
  Power,
  Coins,
  Hash,
  Sun,
  CircleCheck,
  Sparkles,
  Send,
} from "lucide-react";
import { api, post, put, ApiError } from "@/lib/api";
import { useApi, usePolledApi } from "@/lib/useApi";
import {
  Card,
  Stat,
  Badge,
  OfflineHint,
  Empty,
  SkeletonRows,
  ErrorNote,
  SuccessNote,
  LoaderInline,
  ConfirmButton,
  statusTone,
} from "@/components/ui";
import { PageHeader } from "@/components/PageHeader";
import { PageShell, Reveal } from "@/components/motion";
import { timeAgo } from "@/lib/format";

/* -------------------------------------------------------------------------- */
/*  Local types (mirror the daemon's motivation endpoints)                     */
/* -------------------------------------------------------------------------- */

interface AutonomyStatus {
  enabled: boolean;
  level: string;
  dry_run: boolean;
  kill_switch: boolean;
  tick_seconds: number;
  max_actions_per_day: number;
  max_tokens_per_day: number;
  used_actions_24h: number;
  used_tokens_24h: number;
  active_goals: number;
  pending_proposals: number;
}

interface Goal {
  id: string;
  text: string;
  source: string;
  category: string;
  priority: number;
  autonomy_level: string;
  status: string;
  action_budget: number;
  spend_budget: number;
  actions_taken: number;
  tokens_spent: number;
  last_acted_at: string | null;
  created_at: string;
}

interface Proposal {
  id: string;
  goal_id: string | null;
  title: string;
  rationale: string;
  action: Record<string, unknown>;
  risk: string;
  source: string;
  status: string;
  session_id: string | null;
  tokens: number;
  created_at: string;
}

interface Briefing {
  text: string;
  active_goals: number;
  recent_actions: number;
  pending_proposals: number;
  /** POST only: per-channel send results ({channel: {ok, detail}}), null on GET. */
  pushed: unknown;
}

/** Shape of `pushed` when the POST actually fanned out to comm channels. */
type BriefingPushResults = Record<string, { ok?: boolean; detail?: string }>;

/* -------------------------------------------------------------------------- */
/*  Dials / option sets                                                        */
/* -------------------------------------------------------------------------- */

const AUTONOMY_LEVELS = ["suggest", "act_low", "act_all"] as const;
const GOAL_STATUSES = ["active", "paused", "done", "abandoned"] as const;
const PRIORITIES = [1, 2, 3, 4, 5] as const;

const LEVEL_LABEL: Record<string, string> = {
  suggest: "Suggest only",
  act_low: "Act (low-risk)",
  act_all: "Act (all)",
};

function count(v: number | null | undefined): string {
  const n = typeof v === "number" && !Number.isNaN(v) ? v : 0;
  return n.toLocaleString();
}

function errText(err: unknown): string {
  return err instanceof ApiError ? err.message : String(err);
}

/* -------------------------------------------------------------------------- */
/*  Page                                                                       */
/* -------------------------------------------------------------------------- */

export default function AutonomyPage() {
  const status = usePolledApi<AutonomyStatus>("/autonomy", 10000);
  const goals = useApi<{ goals: Goal[] }>("/goals");
  const proposals = useApi<{ proposals: Proposal[] }>("/proposals?status=pending");
  const briefing = useApi<Briefing>("/autonomy/briefing");

  const offline = status.error?.status === 0;
  const s = status.data;

  // Shared action feedback (kill switch, approve/reject, goal dials).
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionOk, setActionOk] = useState<string | null>(null);
  const [killBusy, setKillBusy] = useState(false);
  const [enableBusy, setEnableBusy] = useState(false);
  const [tickBusy, setTickBusy] = useState(false);
  const [briefBusy, setBriefBusy] = useState(false);

  function flash(ok: string | null, error: string | null = null) {
    setActionOk(ok);
    setActionError(error);
  }

  async function toggleEnabled(enabled: boolean) {
    setEnableBusy(true);
    flash(null);
    try {
      await put("/settings", { values: { autonomy_enabled: enabled } });
      flash(
        enabled
          ? 'Autonomy enabled. The background pulse arms on the next daemon restart — use "Run a tick" to deliberate right now.'
          : "Autonomy disabled.",
      );
      status.reload();
    } catch (err) {
      flash(null, errText(err));
    } finally {
      setEnableBusy(false);
    }
  }

  async function runTick() {
    setTickBusy(true);
    flash(null);
    try {
      const r = await post<{ ran: boolean; reason?: string; proposal_id?: string; deduped?: boolean }>(
        "/autonomy/tick",
      );
      flash(
        r.ran
          ? // The backend sets proposal_id even on a dedupe/backlog-full tick, so
            // only claim a NEW proposal when it wasn't deduped.
            r.proposal_id && !r.deduped
            ? "Deliberated — a new proposal is in the backlog below."
            : "Deliberated — nothing new to propose this tick."
          : `Tick didn't run (${r.reason ?? "unknown"}).`,
      );
      status.reload();
      proposals.reload();
    } catch (err) {
      flash(null, errText(err));
    } finally {
      setTickBusy(false);
    }
  }

  async function pushBriefing() {
    setBriefBusy(true);
    flash(null);
    try {
      // POST /autonomy/briefing re-summarises AND pushes to the configured
      // comm channel(s); `pushed` carries the per-channel send results.
      const r = await post<Briefing>("/autonomy/briefing");
      const pushed =
        r.pushed && typeof r.pushed === "object"
          ? (r.pushed as BriefingPushResults)
          : null;
      const entries = pushed ? Object.entries(pushed) : [];
      const failed = entries.filter(([, v]) => !v?.ok);
      if (entries.length === 0) {
        flash(
          null,
          "Briefing was summarised, but no comm channel is configured — nothing was sent. Connect Slack/Telegram/Discord first.",
        );
      } else if (failed.length === 0) {
        flash(`Briefing sent to ${entries.map(([name]) => name).join(", ")}.`);
      } else {
        const okCount = entries.length - failed.length;
        flash(
          null,
          `Briefing push failed on ${failed
            .map(([name, v]) => `${name} (${v?.detail || "unknown error"})`)
            .join(", ")}${okCount ? ` — ${okCount} other channel${okCount === 1 ? "" : "s"} succeeded` : ""}.`,
        );
      }
      briefing.reload(); // the POST re-summarised — keep the card in sync
    } catch (err) {
      flash(null, errText(err));
    } finally {
      setBriefBusy(false);
    }
  }

  async function toggleKill(enabled: boolean) {
    setKillBusy(true);
    flash(null);
    try {
      await post("/autonomy/kill", { enabled });
      flash(enabled ? "Kill switch engaged — all autonomy halted." : "Kill switch released.");
      status.reload();
    } catch (err) {
      flash(null, errText(err));
    } finally {
      setKillBusy(false);
    }
  }

  async function patchGoal(id: string, body: Record<string, unknown>) {
    flash(null);
    try {
      await api(`/goals/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      goals.reload();
      status.reload();
    } catch (err) {
      flash(null, errText(err));
    }
  }

  async function approve(p: Proposal) {
    flash(null);
    try {
      await post(`/proposals/${encodeURIComponent(p.id)}/approve`);
      flash(`Approved "${p.title}".`);
      proposals.reload();
      status.reload();
    } catch (err) {
      flash(null, errText(err));
    }
  }

  async function reject(p: Proposal) {
    flash(null);
    try {
      await post(`/proposals/${encodeURIComponent(p.id)}/reject`);
      flash(`Rejected "${p.title}".`);
      proposals.reload();
      status.reload();
    } catch (err) {
      flash(null, errText(err));
    }
  }

  const killed = !!s?.kill_switch;
  const goalList = goals.data?.goals ?? [];
  // Exact goal texts already on the books — lets starter recipes render as
  // "Added ✓" across visits so clicks stay idempotent.
  const goalTexts = new Set(goalList.map((g) => g.text.trim()));
  const pending = (proposals.data?.proposals ?? []).filter(
    (p) => p.status === "pending",
  );

  return (
    <PageShell>
      <Reveal>
        <PageHeader
          title="Autonomy"
          subtitle="The trust surface for the Motivation Layer — what Iron Jarvis wants to do on its own, what it's waiting to ask you, and the one switch that stops everything."
          actions={
            <div className="flex flex-wrap items-center gap-2">
              {/* Master enable (off by default) — writes autonomy_enabled via /settings. */}
              <button
                type="button"
                onClick={() => toggleEnabled(!s?.enabled)}
                disabled={enableBusy || !s}
                className={`inline-flex items-center gap-2 rounded-xl border px-3.5 py-2 text-sm font-medium transition-colors disabled:opacity-50 ${
                  s?.enabled
                    ? "border-emerald-500/40 bg-emerald-500/[0.1] text-emerald-300 hover:bg-emerald-500/[0.16]"
                    : "border-white/15 bg-white/[0.04] text-zinc-200 hover:bg-white/[0.08]"
                }`}
                title={s?.enabled ? "Disable autonomy" : "Enable autonomy (off by default)"}
              >
                {enableBusy ? (
                  <LoaderInline label="Saving…" />
                ) : (
                  <>
                    <Power size={15} /> {s?.enabled ? "Autonomy on" : "Enable autonomy"}
                  </>
                )}
              </button>
              {/* Deliberate once right now (works even before the background loop arms). */}
              <button
                type="button"
                onClick={runTick}
                disabled={tickBusy || !s}
                className="inline-flex items-center gap-2 rounded-xl border border-accent/30 bg-accent/[0.08] px-3.5 py-2 text-sm font-medium text-accent-soft transition-colors hover:bg-accent/[0.14] disabled:opacity-50"
                title="Deliberate once right now"
              >
                {tickBusy ? <LoaderInline label="Thinking…" /> : <><Activity size={15} /> Run a tick</>}
              </button>
              <button
                type="button"
                onClick={() => toggleKill(!killed)}
                disabled={killBusy || !s}
                className={`inline-flex items-center gap-2 rounded-xl border px-3.5 py-2 text-sm font-medium transition-colors disabled:opacity-50 ${
                  killed
                    ? "border-emerald-500/40 bg-emerald-500/[0.1] text-emerald-300 hover:bg-emerald-500/[0.16]"
                    : "border-rose-500/40 bg-rose-500/[0.1] text-rose-300 hover:bg-rose-500/[0.16]"
                }`}
                title={killed ? "Release the global kill switch" : "Halt all autonomy now"}
              >
                {killBusy ? (
                  <LoaderInline label={killed ? "Releasing…" : "Halting…"} />
                ) : killed ? (
                  <>
                    <ShieldCheck size={15} /> Release kill switch
                  </>
                ) : (
                  <>
                    <ShieldAlert size={15} /> Kill switch
                  </>
                )}
              </button>
            </div>
          }
        />
      </Reveal>

      {offline && (
        <Reveal>
          <OfflineHint />
        </Reveal>
      )}
      {status.error && !offline && (
        <Reveal>
          <ErrorNote>{status.error.message}</ErrorNote>
        </Reveal>
      )}

      {/* Kill-switch banner: loud, unmissable when engaged. */}
      {killed && (
        <Reveal>
          <div className="flex items-start gap-3 rounded-2xl border border-rose-500/30 bg-rose-500/[0.08] px-4 py-3.5">
            <ShieldAlert size={18} className="mt-0.5 shrink-0 text-rose-300" />
            <div className="text-sm text-rose-100/90">
              <div className="font-semibold text-rose-200">
                Kill switch engaged — autonomy is halted.
              </div>
              <div className="mt-1 text-rose-100/60">
                No deliberation tick runs and no goal can act. Release it above to
                resume the dials below.
              </div>
            </div>
          </div>
        </Reveal>
      )}

      {(actionOk || actionError) && (
        <Reveal>
          {actionOk ? (
            <SuccessNote>{actionOk}</SuccessNote>
          ) : (
            <ErrorNote>{actionError}</ErrorNote>
          )}
        </Reveal>
      )}

      {/* Status tiles */}
      <Reveal>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Stat
            label="Autonomy"
            value={s ? (s.enabled ? "Enabled" : "Disabled") : "—"}
            sub={
              s
                ? `${LEVEL_LABEL[s.level] ?? s.level}${s.dry_run ? " · dry-run" : ""}`
                : "loading…"
            }
            icon={<Activity size={16} />}
            accent={!!s?.enabled}
          />
          <Stat
            label="Actions (24h)"
            value={s ? `${count(s.used_actions_24h)} / ${count(s.max_actions_per_day)}` : "—"}
            sub="Self-initiated action budget"
            icon={<Hash size={16} />}
          />
          <Stat
            label="Tokens (24h)"
            value={s ? `${count(s.used_tokens_24h)} / ${count(s.max_tokens_per_day)}` : "—"}
            sub="Self-initiated token budget"
            icon={<Coins size={16} />}
          />
          <Stat
            label="Pending"
            value={s ? count(s.pending_proposals) : "—"}
            sub={`${s ? count(s.active_goals) : "—"} active goal${s?.active_goals === 1 ? "" : "s"}`}
            icon={<Inbox size={16} />}
            accent={!!s && s.pending_proposals > 0}
          />
        </div>
      </Reveal>

      {/* Morning briefing */}
      <Reveal>
        <Card
          title="Morning briefing"
          icon={<Sun size={15} />}
          right={
            <button
              type="button"
              onClick={pushBriefing}
              disabled={briefBusy}
              title="Summarise now and push to your connected channels"
              className="inline-flex items-center gap-1.5 rounded-lg border border-accent/30 bg-accent/[0.08] px-2.5 py-1 text-xs font-medium text-accent-soft transition-colors hover:bg-accent/[0.14] disabled:opacity-50"
            >
              {briefBusy ? (
                <LoaderInline label="Sending…" />
              ) : (
                <>
                  <Send size={13} /> Send briefing to channels
                </>
              )}
            </button>
          }
        >
          {briefing.loading && !briefing.data ? (
            <SkeletonRows rows={3} />
          ) : briefing.error && briefing.error.status !== 0 ? (
            <ErrorNote>{briefing.error.message}</ErrorNote>
          ) : briefing.data ? (
            <pre className="whitespace-pre-wrap font-mono text-[13px] leading-relaxed text-zinc-300">
              {briefing.data.text}
            </pre>
          ) : (
            <Empty icon={<Sun size={24} />}>No briefing available yet.</Empty>
          )}
        </Card>
      </Reveal>

      {/* Starter goals — one-click, suggest-only seeds for a fresh install */}
      <Reveal>
        <StarterGoalsCard
          existingTexts={goalTexts}
          onCreated={() => {
            goals.reload();
            status.reload();
          }}
          onError={(m) => flash(null, m)}
        />
      </Reveal>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Proposals queue */}
        <Reveal>
          <Card
            title={`Proposals${pending.length ? ` · ${pending.length}` : ""}`}
            icon={<Inbox size={15} />}
          >
            {proposals.loading && !proposals.data ? (
              <SkeletonRows rows={3} />
            ) : proposals.error && proposals.error.status !== 0 ? (
              <ErrorNote>{proposals.error.message}</ErrorNote>
            ) : pending.length === 0 ? (
              <Empty icon={<CircleCheck size={24} />}>
                Nothing awaiting your call. Proposals Iron Jarvis wants to act on
                will queue here for approval.
              </Empty>
            ) : (
              <div className="space-y-2.5">
                {pending.map((p) => (
                  <div
                    key={p.id}
                    className="rounded-xl border border-white/[0.06] bg-white/[0.015] px-4 py-3"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium text-zinc-100">{p.title}</span>
                          <Badge value={p.risk} tone={statusTone(p.risk)} />
                          <span className="text-[11px] text-zinc-600">{p.source}</span>
                        </div>
                        {p.rationale && (
                          <p className="mt-1.5 line-clamp-3 text-sm text-zinc-400">
                            {p.rationale}
                          </p>
                        )}
                        <div className="mt-1.5 text-[11px] text-zinc-600">
                          {timeAgo(p.created_at)}
                          {p.tokens ? ` · ~${count(p.tokens)} tokens` : ""}
                        </div>
                      </div>
                      <div className="flex shrink-0 items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => approve(p)}
                          title="Approve and execute this proposal"
                          className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/[0.08] px-2.5 py-1 text-xs font-medium text-emerald-300 transition-colors hover:bg-emerald-500/[0.14]"
                        >
                          <CircleCheck size={13} /> Approve
                        </button>
                        <ConfirmButton
                          onConfirm={() => reject(p)}
                          label="Reject"
                          title={`Reject "${p.title}"`}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </Reveal>

        {/* New goal */}
        <Reveal>
          <NewGoalCard
            onCreated={() => {
              goals.reload();
              status.reload();
            }}
            onError={(m) => flash(null, m)}
          />
        </Reveal>
      </div>

      {/* Standing goals */}
      <Reveal>
        <Card
          title={`Standing goals${goalList.length ? ` · ${goalList.length}` : ""}`}
          icon={<Target size={15} />}
        >
          {goals.loading && !goals.data ? (
            <SkeletonRows rows={4} />
          ) : goals.error && goals.error.status !== 0 ? (
            <ErrorNote>{goals.error.message}</ErrorNote>
          ) : goalList.length === 0 ? (
            <Empty icon={<Target size={24} />}>
              No standing goals yet. Add one above — Iron Jarvis will keep it in
              mind and (within its dial + budget) work toward it.
            </Empty>
          ) : (
            <div className="space-y-2.5">
              {goalList.map((g) => (
                <div
                  key={g.id}
                  className="rounded-xl border border-white/[0.06] bg-white/[0.015] px-4 py-3"
                >
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge value={g.status} tone={statusTone(g.status)} />
                        <span className="text-[11px] uppercase tracking-wide text-zinc-600">
                          {g.category} · P{g.priority}
                        </span>
                      </div>
                      <p className="mt-1.5 text-sm text-zinc-200">{g.text}</p>
                      <div className="mt-1.5 text-[11px] text-zinc-600">
                        {count(g.actions_taken)}/{count(g.action_budget)} actions ·{" "}
                        {count(g.tokens_spent)}/{count(g.spend_budget)} tokens
                        {g.last_acted_at ? ` · acted ${timeAgo(g.last_acted_at)}` : ""}
                      </div>
                    </div>
                    <div className="flex shrink-0 flex-wrap items-center gap-1.5">
                      {/* Per-goal autonomy dial */}
                      <select
                        value={g.autonomy_level}
                        onChange={(e) =>
                          patchGoal(g.id, { autonomy_level: e.target.value })
                        }
                        title="Per-goal autonomy dial"
                        className="field !w-auto !py-1 text-xs"
                      >
                        {AUTONOMY_LEVELS.map((lvl) => (
                          <option key={lvl} value={lvl}>
                            {LEVEL_LABEL[lvl]}
                          </option>
                        ))}
                      </select>
                      {/* Status */}
                      <select
                        value={g.status}
                        onChange={(e) => patchGoal(g.id, { status: e.target.value })}
                        title="Goal status"
                        className="field !w-auto !py-1 text-xs"
                      >
                        {GOAL_STATUSES.map((st) => (
                          <option key={st} value={st}>
                            {st}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </Reveal>
    </PageShell>
  );
}

/* -------------------------------------------------------------------------- */
/*  New-goal form (kept local so the page stays readable)                       */
/* -------------------------------------------------------------------------- */

function NewGoalCard({
  onCreated,
  onError,
}: {
  onCreated: () => void;
  onError: (msg: string) => void;
}) {
  const [text, setText] = useState("");
  const [category, setCategory] = useState("general");
  const [priority, setPriority] = useState(3);
  const [level, setLevel] = useState<string>("suggest");
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    setOk(null);
    try {
      await post("/goals", {
        text: text.trim(),
        category: category.trim() || "general",
        priority,
        autonomy_level: level,
        source: "user",
      });
      setOk(`Goal added.`);
      setText("");
      setCategory("general");
      setPriority(3);
      setLevel("suggest");
      onCreated();
    } catch (err) {
      onError(errText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="New goal" icon={<Plus size={15} />}>
      <form onSubmit={submit} className="space-y-3.5">
        <div>
          <label className="mb-1.5 flex items-center gap-1.5 text-[11px] uppercase tracking-[0.1em] text-zinc-400">
            <Sparkles size={12} /> What should I keep working toward?
          </label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Keep my inbox under 20 unread and draft replies to anything urgent…"
            rows={3}
            className="field resize-y"
          />
        </div>
        <div className="grid grid-cols-3 gap-2">
          <div>
            <label className="mb-1.5 block text-[11px] uppercase tracking-[0.1em] text-zinc-400">
              Category
            </label>
            <input
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              placeholder="general"
              className="field"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-[11px] uppercase tracking-[0.1em] text-zinc-400">
              Priority
            </label>
            <select
              aria-label="Priority"
              value={priority}
              onChange={(e) => setPriority(Number(e.target.value))}
              className="field"
            >
              {PRIORITIES.map((p) => (
                <option key={p} value={p}>
                  P{p}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1.5 block text-[11px] uppercase tracking-[0.1em] text-zinc-400">
              Dial
            </label>
            <select
              aria-label="Autonomy dial"
              value={level}
              onChange={(e) => setLevel(e.target.value)}
              className="field"
            >
              {AUTONOMY_LEVELS.map((lvl) => (
                <option key={lvl} value={lvl}>
                  {LEVEL_LABEL[lvl]}
                </option>
              ))}
            </select>
          </div>
        </div>
        <button
          type="submit"
          disabled={busy || !text.trim()}
          className="btn-accent w-full"
        >
          {busy ? (
            <LoaderInline label="Adding…" />
          ) : (
            <>
              <Plus size={14} /> Add goal
            </>
          )}
        </button>
        {ok && <SuccessNote>{ok}</SuccessNote>}
      </form>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/*  Starter goals (one-click, honest, suggest-only recipes for a fresh vault)  */
/* -------------------------------------------------------------------------- */

const STARTER_GOALS = [
  {
    id: "morning-briefing",
    title: "Morning briefing",
    description:
      "A short daily digest: new events, pending reviews, and the one thing worth your attention.",
    text: "Each deliberation tick in the morning, prepare a short briefing: new events, pending reviews and proposals since yesterday, and the one thing most worth my attention today.",
    category: "briefing",
    priority: 3,
  },
  {
    id: "watch-project",
    title: "Watch the active project",
    description:
      "When the active project's files change meaningfully, proposes a summary plus follow-ups.",
    text: "Keep an eye on the active project: when its files change meaningfully, propose a short summary of what changed and any follow-ups worth doing.",
    category: "project",
    priority: 3,
  },
  {
    id: "usage-recap",
    title: "Weekly usage recap",
    description:
      "A rough-weekly recap of token spend and big sessions, with one concrete cost-saving idea.",
    text: "Roughly weekly, compile a usage recap: token spend by provider and the largest sessions, and propose one concrete cost-saving change.",
    category: "ops",
    priority: 2,
  },
] as const;

function StarterGoalsCard({
  existingTexts,
  onCreated,
  onError,
}: {
  /** Trimmed texts of goals already on the books (for idempotent recipes). */
  existingTexts: Set<string>;
  onCreated: () => void;
  onError: (msg: string) => void;
}) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [added, setAdded] = useState<Record<string, boolean>>({});

  async function add(recipe: (typeof STARTER_GOALS)[number]) {
    setBusyId(recipe.id);
    try {
      await post("/goals", {
        text: recipe.text,
        category: recipe.category,
        priority: recipe.priority,
        autonomy_level: "suggest",
        source: "user",
      });
      setAdded((prev) => ({ ...prev, [recipe.id]: true }));
      onCreated();
    } catch (err) {
      onError(errText(err));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Card title="Starter goals" icon={<Sparkles size={15} />}>
      <p className="text-sm text-zinc-400">
        Not sure what to seed? Add one with a click. Starters only make Iron
        Jarvis PROPOSE things on its tick — nothing runs without your approval,
        and the pulse itself stays off until you enable Autonomy above.
      </p>
      <div className="mt-3.5 grid gap-2.5 sm:grid-cols-3">
        {STARTER_GOALS.map((r) => {
          const isAdded = !!added[r.id] || existingTexts.has(r.text);
          const isBusy = busyId === r.id;
          return (
            <div
              key={r.id}
              className="flex flex-col rounded-xl border border-white/[0.06] bg-white/[0.015] px-4 py-3"
            >
              <div className="text-sm font-medium text-zinc-100">{r.title}</div>
              <p className="mt-1 flex-1 text-sm text-zinc-400">{r.description}</p>
              <div className="mt-2.5 flex items-center justify-between gap-2">
                <span className="text-[11px] uppercase tracking-wide text-zinc-600">
                  {r.category} · P{r.priority} · suggest
                </span>
                <button
                  type="button"
                  onClick={() => add(r)}
                  disabled={isAdded || busyId !== null}
                  title={
                    isAdded
                      ? "Already in your standing goals"
                      : `Add "${r.title}" as a suggest-only goal`
                  }
                  className={`inline-flex shrink-0 items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors ${
                    isAdded
                      ? "border-emerald-500/30 bg-emerald-500/[0.08] text-emerald-300"
                      : "border-accent/30 bg-accent/[0.08] text-accent-soft hover:bg-accent/[0.14] disabled:opacity-50"
                  }`}
                >
                  {isBusy ? (
                    <LoaderInline label="Adding…" />
                  ) : isAdded ? (
                    <>
                      <CircleCheck size={13} /> Added ✓
                    </>
                  ) : (
                    <>
                      <Plus size={13} /> Add
                    </>
                  )}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
