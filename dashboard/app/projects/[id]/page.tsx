"use client";

// The per-project WORKSPACE — a focused, Claude-Projects-style page. Layout:
//   header (editable name + model default + folder + activate)
//   → collapsible custom instructions + editable brief
//   → tab bar (Chat · Tasks · Board · Activity)
//   → on Chat/Tasks a Knowledge right-rail sits beside the content (knowledge
//     grounds every chat + task); Board/Activity get the full width.
// The Board tab is the ONLY thing that polls /sessions, and only while active.

import { use, useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Bot,
  Check,
  ChevronDown,
  ChevronRight,
  Folder,
  History,
  MessageSquare,
  Pencil,
  Sparkles,
  SquareKanban,
  Zap,
  ZapOff,
  X,
} from "lucide-react";
import { useApi, usePolledApi } from "@/lib/useApi";
import { patch, post, ApiError } from "@/lib/api";
import { useReviews } from "@/lib/useReviews";
import { KanbanBoard } from "@/components/kanban/KanbanBoard";
import { ProjectChat } from "@/components/project/ProjectChat";
import { ProjectTasks } from "@/components/project/ProjectTasks";
import { KnowledgePanel } from "@/components/project/KnowledgePanel";
import type { ModelOption, Project, SessionView } from "@/lib/types";
import {
  Card,
  Badge,
  OfflineHint,
  Empty,
  ErrorNote,
  LoaderInline,
  SkeletonRows,
} from "@/components/ui";
import { PageShell, Reveal } from "@/components/motion";
import { timeAgo } from "@/lib/format";

/** GET /projects/{id} → the project (plus workspace fields) and recent sessions. */
interface ProjectWorkspace extends Project {
  instructions?: string;
  default_provider?: string;
  default_model?: string;
}
interface ProjectDetail {
  project: ProjectWorkspace;
  sessions: SessionView[];
}

type TabId = "chat" | "tasks" | "board" | "activity";
const TABS: { id: TabId; label: string; icon: ReactNode }[] = [
  { id: "chat", label: "Chat", icon: <MessageSquare size={14} /> },
  { id: "tasks", label: "Tasks", icon: <Bot size={14} /> },
  { id: "board", label: "Board", icon: <SquareKanban size={14} /> },
  { id: "activity", label: "Activity", icon: <History size={14} /> },
];

const BTN_PILL =
  "inline-flex items-center gap-1.5 rounded-lg border border-accent/30 bg-accent/[0.08] px-2.5 py-1 text-xs font-medium text-accent-soft transition-colors hover:bg-accent/[0.14] disabled:opacity-50";
const BTN_GHOST =
  "inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1 text-xs font-medium text-zinc-400 transition-colors hover:border-white/20 hover:text-zinc-200 disabled:opacity-50";

function errText(err: unknown): string {
  return err instanceof ApiError ? err.message : String(err);
}

function splitChoice(choice: string): { provider?: string; model?: string } {
  const i = choice.indexOf("::");
  if (i === -1) return {};
  const provider = choice.slice(0, i);
  const model = choice.slice(i + 2);
  return provider && model ? { provider, model } : {};
}

/** The glowing "Active" badge — this project is the context spine right now. */
function ActiveBadge() {
  return (
    <span
      title="New chats, sessions, and workflows automatically carry this project's context"
      className="inline-flex items-center gap-1.5 rounded-full border border-accent/40 bg-accent/[0.12] px-2.5 py-0.5 text-[11px] font-medium text-accent-soft shadow-[0_0_14px_rgba(34,211,238,0.35)]"
    >
      <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse-glow shadow-[0_0_8px_2px_rgba(34,211,238,0.55)]" />
      Active
    </span>
  );
}

/** The per-project Kanban — mounted ONLY while the Board tab is active, so a
 * hidden tab never 4s-polls /sessions. */
function ProjectBoard({ projectId }: { projectId: string }) {
  const { data, error, reload } = usePolledApi<{ sessions: SessionView[] }>("/sessions", 4000);
  const sessions = data?.sessions;
  const reviewsState = useReviews(sessions);
  const list = sessions ?? [];
  const mine = list.filter((s) => s.project_id === projectId);
  const offline = error && error.status === 0;

  function refreshAll() {
    reload();
    reviewsState.reload();
  }

  if (offline && list.length === 0)
    return (
      <Card title="Board" icon={<SquareKanban size={15} />}>
        <p className="py-2 text-sm text-zinc-500">Board unavailable — the daemon looks offline.</p>
      </Card>
    );
  if (mine.length === 0)
    return (
      <Card title="Board" icon={<SquareKanban size={15} />}>
        <Empty icon={<SquareKanban size={22} />}>
          No sessions in this project yet — run a task, or start a chat.
        </Empty>
      </Card>
    );
  // KanbanBoard filters to projectId itself; pass the full list so its lane math
  // stays identical to the standalone page.
  return (
    <KanbanBoard
      sessions={list}
      reviews={reviewsState.reviews}
      reload={refreshAll}
      projectId={projectId}
    />
  );
}

function ActivityList({ sessions }: { sessions: SessionView[] }) {
  return (
    <Card
      title={sessions.length ? `Recent activity · ${sessions.length}` : "Recent activity"}
      icon={<History size={15} />}
    >
      {sessions.length === 0 ? (
        <Empty icon={<History size={22} />}>
          No sessions in this project yet — run a task or start a chat.
        </Empty>
      ) : (
        <ul className="space-y-1.5">
          {sessions.map((s) => (
            <li key={s.id}>
              <Link
                href={`/sessions/${encodeURIComponent(s.id)}`}
                className="flex items-center justify-between gap-3 rounded-lg border border-white/[0.05] bg-white/[0.02] px-3 py-2 transition-colors hover:border-accent/25 hover:bg-white/[0.04]"
              >
                <span className="min-w-0 truncate text-xs text-zinc-300">{s.task || s.id}</span>
                <span className="flex shrink-0 items-center gap-2">
                  <Badge value={s.status} />
                  <span className="text-[11px] text-zinc-600">{timeAgo(s.created_at)}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export default function ProjectWorkspacePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const detail = useApi<ProjectDetail>(`/projects/${encodeURIComponent(id)}`);
  const models = useApi<{ models: ModelOption[] }>("/models");

  const project = detail.data?.project;
  const sessions = detail.data?.sessions ?? [];
  const offline = detail.error && detail.error.status === 0;
  const notFound = detail.error && detail.error.status === 404;

  const availableModels = (models.data?.models ?? []).filter((m) => m.available !== false);

  /* --- Active tab (persisted per project) --------------------------------- */
  const TAB_KEY = `ij.project.${id}.tab`;
  const [tab, setTab] = useState<TabId>("chat");
  useEffect(() => {
    try {
      const s = window.localStorage.getItem(TAB_KEY);
      if (s && TABS.some((t) => t.id === s)) setTab(s as TabId);
    } catch {
      /* ignore */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);
  function chooseTab(t: TabId) {
    setTab(t);
    try {
      window.localStorage.setItem(TAB_KEY, t);
    } catch {
      /* ignore */
    }
  }

  /* --- Header / inline edits ---------------------------------------------- */
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [briefEditing, setBriefEditing] = useState(false);
  const [briefDraft, setBriefDraft] = useState("");
  const [instrOpen, setInstrOpen] = useState(false);
  const [instrDraft, setInstrDraft] = useState("");
  const [savingField, setSavingField] = useState<string | null>(null);
  const [headerError, setHeaderError] = useState<string | null>(null);

  // Seed drafts once per loaded project (display uses the live project fields
  // when not editing, so a post-save reload won't clobber an open editor).
  useEffect(() => {
    if (!project) return;
    setNameDraft(project.name);
    setBriefDraft(project.brief ?? "");
    setInstrDraft(project.instructions ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.id]);

  async function savePatch(body: Record<string, unknown>, field: string): Promise<boolean> {
    setSavingField(field);
    setHeaderError(null);
    try {
      await patch(`/projects/${encodeURIComponent(id)}`, body);
      detail.reload();
      return true;
    } catch (err) {
      setHeaderError(errText(err));
      return false;
    } finally {
      setSavingField(null);
    }
  }

  async function saveName() {
    const name = nameDraft.trim();
    if (!name || name === project?.name) {
      setEditingName(false);
      return;
    }
    if (await savePatch({ name }, "name")) setEditingName(false);
  }

  async function saveBrief() {
    if (await savePatch({ brief: briefDraft.trim() }, "brief")) setBriefEditing(false);
  }

  function chooseModel(v: string) {
    const { provider, model } = splitChoice(v);
    void savePatch(
      { default_provider: provider ?? "", default_model: model ?? "" },
      "model",
    );
  }

  async function activate() {
    setSavingField("active");
    setHeaderError(null);
    try {
      await post(`/projects/${encodeURIComponent(id)}/activate`);
      detail.reload();
    } catch (err) {
      setHeaderError(errText(err));
    } finally {
      setSavingField(null);
    }
  }
  async function deactivate() {
    setSavingField("active");
    setHeaderError(null);
    try {
      await post("/projects/deactivate");
      detail.reload();
    } catch (err) {
      setHeaderError(errText(err));
    } finally {
      setSavingField(null);
    }
  }

  const modelValue =
    project?.default_provider && project?.default_model
      ? `${project.default_provider}::${project.default_model}`
      : "";
  const archived = project?.status === "archived";
  const showRail = tab === "chat" || tab === "tasks";

  return (
    <PageShell>
      <Reveal>
        <Link
          href="/projects"
          className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1 text-xs text-zinc-300 transition-colors hover:border-white/20 hover:text-zinc-100"
        >
          <ArrowLeft size={13} /> Projects
        </Link>
      </Reveal>

      {offline && (
        <Reveal>
          <OfflineHint />
        </Reveal>
      )}
      {notFound && (
        <Reveal>
          <Card>
            <Empty icon={<Folder size={22} />}>Project not found.</Empty>
          </Card>
        </Reveal>
      )}

      {detail.loading && !detail.data ? (
        <Reveal>
          <Card>
            <SkeletonRows rows={5} />
          </Card>
        </Reveal>
      ) : project ? (
        <>
          {/* -------------------------------------------------- header */}
          <Reveal>
            <div className="flex flex-col gap-4">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  {editingName ? (
                    <div className="flex items-center gap-2">
                      <input
                        value={nameDraft}
                        onChange={(e) => setNameDraft(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            void saveName();
                          } else if (e.key === "Escape") {
                            setEditingName(false);
                            setNameDraft(project.name);
                          }
                        }}
                        aria-label="Project name"
                        autoFocus
                        className="field max-w-md text-lg font-semibold"
                      />
                      <button
                        type="button"
                        onClick={() => void saveName()}
                        disabled={savingField === "name"}
                        className="text-accent-soft hover:text-accent"
                        title="Save"
                      >
                        {savingField === "name" ? (
                          <LoaderInline label="" />
                        ) : (
                          <Check size={16} />
                        )}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setEditingName(false);
                          setNameDraft(project.name);
                        }}
                        className="text-zinc-500 hover:text-zinc-200"
                        title="Cancel"
                      >
                        <X size={16} />
                      </button>
                    </div>
                  ) : (
                    <div className="flex flex-wrap items-center gap-2">
                      <h1 className="min-w-0 truncate text-2xl font-semibold tracking-tight text-zinc-50">
                        {project.name}
                      </h1>
                      {project.active && <ActiveBadge />}
                      {archived && <Badge value="archived" tone="slate" />}
                      <button
                        type="button"
                        onClick={() => {
                          setNameDraft(project.name);
                          setEditingName(true);
                        }}
                        className="text-zinc-500 transition-colors hover:text-zinc-200"
                        title="Rename project"
                      >
                        <Pencil size={14} />
                      </button>
                    </div>
                  )}

                  {/* Brief line (click to edit) */}
                  {briefEditing ? (
                    <div className="mt-2 space-y-2">
                      <textarea
                        value={briefDraft}
                        onChange={(e) => setBriefDraft(e.target.value)}
                        rows={3}
                        aria-label="Project brief"
                        placeholder="The goal and key facts every chat and task should know…"
                        className="field max-w-2xl resize-y text-sm"
                      />
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => void saveBrief()}
                          disabled={savingField === "brief"}
                          className="btn-accent"
                        >
                          {savingField === "brief" ? <LoaderInline label="Saving…" /> : "Save"}
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setBriefEditing(false);
                            setBriefDraft(project.brief ?? "");
                          }}
                          className="btn-ghost"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        setBriefDraft(project.brief ?? "");
                        setBriefEditing(true);
                      }}
                      className="mt-1.5 block max-w-2xl text-left text-sm text-zinc-500 transition-colors hover:text-zinc-300"
                    >
                      {project.brief ? (
                        project.brief
                      ) : (
                        <span className="italic text-zinc-600">
                          Add a brief — the goal and key facts every chat and task should know…
                        </span>
                      )}
                    </button>
                  )}

                  {project.root && (
                    <div className="mt-2 flex items-center gap-1.5 text-[11px] text-zinc-500">
                      <Folder size={11} className="shrink-0" />
                      <span className="truncate font-mono" title={project.root}>
                        {project.root}
                      </span>
                    </div>
                  )}
                </div>

                {/* Controls */}
                <div className="flex flex-wrap items-center gap-2">
                  <select
                    value={modelValue}
                    onChange={(e) => chooseModel(e.target.value)}
                    disabled={savingField === "model"}
                    aria-label="Project default model"
                    title="Default model for this project's chats and tasks"
                    className="field text-sm"
                  >
                    <option value="">Project default</option>
                    {availableModels.map((m) => (
                      <option key={`${m.provider}::${m.model}`} value={`${m.provider}::${m.model}`}>
                        {m.provider} / {m.model}
                      </option>
                    ))}
                  </select>

                  {!archived &&
                    (project.active ? (
                      <button
                        type="button"
                        onClick={() => void deactivate()}
                        disabled={savingField === "active"}
                        title="Stop feeding this project's context into new sessions"
                        className={BTN_GHOST}
                      >
                        {savingField === "active" ? (
                          <LoaderInline label="…" />
                        ) : (
                          <>
                            <ZapOff size={13} /> Deactivate
                          </>
                        )}
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => void activate()}
                        disabled={savingField === "active"}
                        title="New chats, sessions, and workflows will carry this project's context"
                        className={BTN_PILL}
                      >
                        {savingField === "active" ? (
                          <LoaderInline label="…" />
                        ) : (
                          <>
                            <Zap size={13} /> Make active
                          </>
                        )}
                      </button>
                    ))}
                </div>
              </div>

              {headerError && <ErrorNote>{headerError}</ErrorNote>}

              {/* Custom instructions (collapsible) */}
              <div className="rounded-2xl border hairline bg-white/[0.02]">
                <button
                  type="button"
                  onClick={() => setInstrOpen((o) => !o)}
                  aria-expanded={instrOpen}
                  className="flex w-full items-center gap-2 px-4 py-3 text-sm font-medium text-zinc-200"
                >
                  {instrOpen ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                  <Sparkles size={14} className="text-accent-soft/80" />
                  Custom instructions
                  {project.instructions && !instrOpen && (
                    <span className="ml-1 text-[11px] font-normal text-zinc-500">· set</span>
                  )}
                </button>
                {instrOpen && (
                  <div className="space-y-2 border-t hairline px-4 py-3">
                    <p className="text-[12px] text-zinc-500">
                      Given to every chat and task in this project — set the tone, rules, and
                      preferences the AI should always follow.
                    </p>
                    <textarea
                      value={instrDraft}
                      onChange={(e) => setInstrDraft(e.target.value)}
                      rows={5}
                      aria-label="Custom instructions"
                      placeholder="e.g. Always cite sources. Prefer concise bullet points. Never touch files outside this folder."
                      className="field resize-y text-sm"
                    />
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => void savePatch({ instructions: instrDraft }, "instructions")}
                        disabled={savingField === "instructions"}
                        className="btn-accent"
                      >
                        {savingField === "instructions" ? (
                          <LoaderInline label="Saving…" />
                        ) : (
                          "Save instructions"
                        )}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </Reveal>

          {/* -------------------------------------------------- tab bar */}
          <Reveal>
            <div className="flex items-center gap-1 border-b hairline">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => chooseTab(t.id)}
                  aria-pressed={tab === t.id}
                  className={`-mb-px inline-flex items-center gap-1.5 border-b-2 px-3.5 py-2 text-sm font-medium transition-colors ${
                    tab === t.id
                      ? "border-accent text-accent-soft"
                      : "border-transparent text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  {t.icon}
                  {t.label}
                </button>
              ))}
            </div>
          </Reveal>

          {/* -------------------------------------------------- content */}
          <Reveal>
            <div className={showRail ? "grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]" : ""}>
              <div className="min-w-0">
                {tab === "chat" && (
                  <ProjectChat
                    projectId={id}
                    defaultProvider={project.default_provider}
                    defaultModel={project.default_model}
                  />
                )}
                {tab === "tasks" && <ProjectTasks projectId={id} hasRoot={!!project.root} />}
                {tab === "board" && <ProjectBoard projectId={id} />}
                {tab === "activity" && <ActivityList sessions={sessions} />}
              </div>
              {showRail && (
                <aside className="min-w-0">
                  <KnowledgePanel projectId={id} />
                </aside>
              )}
            </div>
          </Reveal>
        </>
      ) : null}
    </PageShell>
  );
}
