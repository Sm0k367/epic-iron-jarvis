"use client";

import { useRef, useState, type ReactNode } from "react";
import {
  Wrench,
  Plus,
  Terminal,
  Braces,
  Clock,
  User,
  X,
  Info,
  Boxes,
  Check,
  Globe,
  Radio,
  Search,
  FolderOpen,
  FileText,
  HardDrive,
  GitBranch,
  FileArchive,
  ExternalLink,
} from "lucide-react";
import { post, del, ApiError } from "@/lib/api";
import { usePolledApi } from "@/lib/useApi";
import {
  Card,
  Badge,
  OfflineHint,
  Empty,
  SkeletonRows,
  ErrorNote,
  SuccessNote,
  LoaderInline,
  ConfirmButton,
} from "@/components/ui";
import { PageHeader } from "@/components/PageHeader";
import { PageShell, Reveal } from "@/components/motion";
import { timeAgo } from "@/lib/format";

/* -------------------------------------------------------------------------- */
/*  Types (local — lib/types.ts is intentionally untouched)                    */
/* -------------------------------------------------------------------------- */

type ParamType = "string" | "integer" | "number" | "boolean";

const PARAM_TYPES: ParamType[] = ["string", "integer", "number", "boolean"];

/** A typed parameter that fills a {placeholder} in the command template. */
interface ToolParam {
  name: string;
  type: ParamType;
  required: boolean;
  description: string;
}

/** A custom (agent/user-authored) reusable tool, as returned by the daemon. */
interface CustomTool {
  name: string;
  description: string;
  parameters: ToolParam[];
  command: string[];
  timeout_seconds: number;
  created_by: string;
  created_at: string;
}

/** A parameter row in the create form (carries a stable key id). */
interface ParamRow extends ToolParam {
  id: number;
}

/** Split a space-separated argv string into a clean string[] (drops empties). */
function tokenize(command: string): string[] {
  return command
    .split(/\s+/)
    .map((t) => t.trim())
    .filter(Boolean);
}

/* -------------------------------------------------------------------------- */
/*  Tool suite — curated, one-click, Windows-friendly prebuilt tools           */
/* -------------------------------------------------------------------------- */

/** A ready-made tool template posted verbatim to POST /tools/custom. */
interface SuiteTool {
  name: string;
  description: string;
  parameters: ToolParam[];
  command: string[];
  timeout_seconds: number;
  icon: ReactNode;
}

/** Shorthand for a required string parameter (the only kind the suite needs). */
function strParam(name: string, description: string): ToolParam {
  return { name, type: "string", required: true, description };
}

/**
 * The curated gallery. Commands are argv (no shell), so {placeholder} tokens —
 * which the daemon fills from the declared parameters — are injection-safe.
 * Everything here targets Windows (PowerShell / cmd built-ins).
 */
const TOOL_SUITE: SuiteTool[] = [
  {
    name: "http_get",
    description: "Fetch a URL and print the response.",
    parameters: [strParam("url", "The URL to fetch.")],
    command: ["curl", "-s", "{url}"],
    timeout_seconds: 30,
    icon: <Globe size={14} className="text-accent-soft" />,
  },
  {
    name: "ping_host",
    description: "Ping a host 4 times.",
    parameters: [strParam("host", "Hostname or IP address to ping.")],
    command: ["ping", "-n", "4", "{host}"],
    timeout_seconds: 30,
    icon: <Radio size={14} className="text-accent-soft" />,
  },
  {
    name: "dns_lookup",
    description: "DNS lookup for a hostname.",
    parameters: [strParam("host", "Hostname to resolve.")],
    command: ["nslookup", "{host}"],
    timeout_seconds: 20,
    icon: <Search size={14} className="text-accent-soft" />,
  },
  {
    name: "list_dir",
    description: "List a directory.",
    parameters: [strParam("path", "Directory path to list.")],
    command: ["powershell", "-NoProfile", "-Command", "Get-ChildItem -Force '{path}'"],
    timeout_seconds: 20,
    icon: <FolderOpen size={14} className="text-accent-soft" />,
  },
  {
    name: "word_count",
    description: "Count words in a text file.",
    parameters: [strParam("file", "Path to the text file.")],
    command: [
      "powershell",
      "-NoProfile",
      "-Command",
      "(Get-Content '{file}' -Raw | Measure-Object -Word).Words",
    ],
    timeout_seconds: 30,
    icon: <FileText size={14} className="text-accent-soft" />,
  },
  {
    name: "disk_free",
    description: "Show free disk space.",
    parameters: [],
    command: [
      "powershell",
      "-NoProfile",
      "-Command",
      "Get-PSDrive -PSProvider FileSystem | Select-Object Name,Used,Free",
    ],
    timeout_seconds: 20,
    icon: <HardDrive size={14} className="text-accent-soft" />,
  },
  {
    name: "git_status",
    description: "git status of a repo.",
    parameters: [strParam("repo", "Path to the git repository.")],
    command: ["git", "-C", "{repo}", "status", "--short"],
    timeout_seconds: 30,
    icon: <GitBranch size={14} className="text-accent-soft" />,
  },
  {
    name: "zip_folder",
    description: "Zip a folder.",
    parameters: [
      strParam("source", "Folder (or path) to compress."),
      strParam("dest", "Destination .zip path."),
    ],
    command: [
      "powershell",
      "-NoProfile",
      "-Command",
      "Compress-Archive -Path '{source}' -DestinationPath '{dest}' -Force",
    ],
    timeout_seconds: 120,
    icon: <FileArchive size={14} className="text-accent-soft" />,
  },
  {
    name: "open_url",
    description: "Open a URL in the default browser.",
    parameters: [strParam("url", "The URL to open.")],
    command: ["powershell", "-NoProfile", "-Command", "Start-Process '{url}'"],
    timeout_seconds: 15,
    icon: <ExternalLink size={14} className="text-accent-soft" />,
  },
];

export default function ToolsPage() {
  const { data, error, loading, reload } = usePolledApi<{ tools: CustomTool[] }>(
    "/tools/custom",
    8000,
  );
  const offline = error && error.status === 0;
  const tools = data?.tools ?? [];

  // Create form ------------------------------------------------------------
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [timeout, setTimeoutSecs] = useState("60");
  const [command, setCommand] = useState("");
  const [rows, setRows] = useState<ParamRow[]>([]);
  const nextId = useRef(1);

  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  const argv = tokenize(command);

  function addRow() {
    setRows((r) => [
      ...r,
      { id: nextId.current++, name: "", type: "string", required: false, description: "" },
    ]);
  }
  function updateRow(id: number, patch: Partial<ParamRow>) {
    setRows((r) => r.map((x) => (x.id === id ? { ...x, ...patch } : x)));
  }
  function removeRow(id: number) {
    setRows((r) => r.filter((x) => x.id !== id));
  }

  function resetForm() {
    setName("");
    setDescription("");
    setTimeoutSecs("60");
    setCommand("");
    setRows([]);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || argv.length === 0) return;
    setBusy(true);
    setFormError(null);
    setOk(null);

    const parameters: ToolParam[] = rows
      .filter((r) => r.name.trim())
      .map((r) => ({
        name: r.name.trim(),
        type: r.type,
        required: r.required,
        description: r.description.trim(),
      }));

    const body = {
      name: name.trim(),
      description: description.trim(),
      parameters,
      command: argv,
      timeout_seconds: Number(timeout) || 60,
    };

    try {
      await post<{ name: string }>("/tools/custom", body);
      setOk(`Tool "${name.trim()}" created.`);
      resetForm();
      reload();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(toolName: string) {
    setOk(null);
    setFormError(null);
    try {
      await del(`/tools/custom/${encodeURIComponent(toolName)}`);
      reload();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : String(err));
    }
  }

  // Tool suite (one-click add) --------------------------------------------
  const installed = new Set(tools.map((t) => t.name));
  const [adding, setAdding] = useState<string | null>(null);
  const [suiteError, setSuiteError] = useState<string | null>(null);
  const [suiteOk, setSuiteOk] = useState<string | null>(null);

  async function addFromSuite(t: SuiteTool) {
    setAdding(t.name);
    setSuiteError(null);
    setSuiteOk(null);
    try {
      await post<{ name: string }>("/tools/custom", {
        name: t.name,
        description: t.description,
        parameters: t.parameters,
        command: t.command,
        timeout_seconds: t.timeout_seconds,
      });
      setSuiteOk(`Tool "${t.name}" added.`);
      reload();
    } catch (err) {
      setSuiteError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setAdding(null);
    }
  }

  return (
    <PageShell>
      <Reveal>
        <PageHeader
          title="Tools"
          subtitle="Reusable command-line tools that you — and any agent — can create. Once a tool is registered, every future agent can call it by name."
        />
      </Reveal>
      {offline && (
        <Reveal>
          <OfflineHint />
        </Reveal>
      )}

      <Reveal>
        <div className="flex items-start gap-3 rounded-2xl border border-accent/20 bg-accent/[0.05] px-4 py-3.5">
          <Info size={18} className="mt-0.5 shrink-0 text-accent-soft" />
          <div className="text-sm text-zinc-400">
            <span className="font-semibold text-zinc-200">How it works.</span> A tool
            runs an <span className="text-zinc-200">argv command template</span> with
            no shell, so it&apos;s injection-safe. Typed{" "}
            <code className="rounded bg-black/40 px-1 py-0.5 font-mono text-[12px] text-accent-soft">
              {"{param}"}
            </code>{" "}
            placeholders get filled from the parameters you declare. For example, the
            command{" "}
            <code className="rounded bg-black/40 px-1.5 py-0.5 font-mono text-[12px] text-zinc-200">
              wc -l {"{file}"}
            </code>{" "}
            with a required string parameter{" "}
            <code className="rounded bg-black/40 px-1 py-0.5 font-mono text-[12px] text-accent-soft">
              file
            </code>{" "}
            counts the lines in whatever path the agent passes.
          </div>
        </div>
      </Reveal>

      <Reveal>
        <div className="grid gap-6 lg:grid-cols-3">
          {/* ---------------------------------------------------------------- */}
          {/*  Create form                                                     */}
          {/* ---------------------------------------------------------------- */}
          <div className="lg:col-span-1">
            <Card title="New tool" icon={<Plus size={15} />}>
              <form onSubmit={submit} className="space-y-3.5">
                <div>
                  <label className="mb-1.5 block text-[11px] uppercase tracking-[0.1em] text-zinc-400">
                    Name
                  </label>
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="count_lines"
                    className="field font-mono"
                  />
                  <div className="mt-1 text-[11px] text-zinc-600">
                    A unique identifier. Can&apos;t collide with a built-in tool.
                  </div>
                </div>

                <div>
                  <label className="mb-1.5 block text-[11px] uppercase tracking-[0.1em] text-zinc-400">
                    Description
                  </label>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={2}
                    placeholder="Count the number of lines in a file."
                    className="field resize-y"
                  />
                </div>

                <div>
                  <label className="mb-1.5 flex items-center gap-1.5 text-[11px] uppercase tracking-[0.1em] text-zinc-400">
                    <Terminal size={12} /> Command (argv)
                  </label>
                  <input
                    value={command}
                    onChange={(e) => setCommand(e.target.value)}
                    placeholder="wc -l {file}"
                    className="field font-mono"
                  />
                  <div className="mt-1 text-[11px] text-zinc-600">
                    Space-separated tokens. Use{" "}
                    <code className="font-mono text-accent-soft/80">{"{param}"}</code> to
                    inject a parameter below.
                  </div>
                  {argv.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {argv.map((tok, i) => {
                        const isPh = /^\{.+\}$/.test(tok);
                        return (
                          <span
                            key={i}
                            className={`rounded-md border px-1.5 py-0.5 font-mono text-[11px] ${
                              isPh
                                ? "border-accent/30 bg-accent/[0.08] text-accent-soft"
                                : "border-white/[0.06] bg-white/[0.03] text-zinc-300"
                            }`}
                          >
                            {tok}
                          </span>
                        );
                      })}
                    </div>
                  )}
                </div>

                <div>
                  <div className="mb-1.5 flex items-center justify-between">
                    <label className="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.1em] text-zinc-400">
                      <Braces size={12} /> Parameters
                      {rows.length ? ` · ${rows.length}` : ""}
                    </label>
                    <button
                      type="button"
                      onClick={addRow}
                      className="inline-flex items-center gap-1 rounded-lg border border-white/10 px-2 py-1 text-[11px] font-medium text-zinc-400 transition-colors hover:border-accent/40 hover:text-accent-soft"
                    >
                      <Plus size={12} /> Add
                    </button>
                  </div>
                  <div className="space-y-2 rounded-xl border border-white/[0.06] bg-ink-900/40 p-2.5">
                    {rows.length === 0 ? (
                      <p className="px-0.5 py-1 text-[11px] text-zinc-600">
                        No parameters. Add one for each{" "}
                        <code className="font-mono text-accent-soft/70">
                          {"{placeholder}"}
                        </code>{" "}
                        in the command.
                      </p>
                    ) : (
                      rows.map((row) => (
                        <div
                          key={row.id}
                          className="flex flex-wrap items-center gap-2 rounded-lg border border-white/[0.05] bg-white/[0.015] p-2"
                        >
                          <input
                            value={row.name}
                            onChange={(e) =>
                              updateRow(row.id, { name: e.target.value })
                            }
                            placeholder="file"
                            className="field min-w-[6rem] flex-1 px-2 py-1.5 font-mono text-xs"
                          />
                          <select
                            aria-label="Parameter type"
                            value={row.type}
                            onChange={(e) =>
                              updateRow(row.id, { type: e.target.value as ParamType })
                            }
                            className="field w-auto px-2 py-1.5 text-xs"
                          >
                            {PARAM_TYPES.map((t) => (
                              <option key={t} value={t}>
                                {t}
                              </option>
                            ))}
                          </select>
                          <label
                            className={`flex cursor-pointer select-none items-center gap-1 rounded-lg border px-2 py-1.5 text-[11px] font-medium transition-colors ${
                              row.required
                                ? "border-rose-500/40 bg-rose-500/[0.1] text-rose-200"
                                : "border-white/10 text-zinc-400 hover:bg-white/[0.04]"
                            }`}
                            title="Is this parameter required?"
                          >
                            <input
                              type="checkbox"
                              checked={row.required}
                              onChange={(e) =>
                                updateRow(row.id, { required: e.target.checked })
                              }
                              className="h-3 w-3 accent-rose-400"
                            />
                            req
                          </label>
                          <button
                            type="button"
                            onClick={() => removeRow(row.id)}
                            title="Remove parameter"
                            className="grid h-7 w-7 shrink-0 place-items-center rounded-lg border border-white/10 text-zinc-500 transition-colors hover:border-rose-500/40 hover:text-rose-300"
                          >
                            <X size={13} />
                          </button>
                          <input
                            value={row.description}
                            onChange={(e) =>
                              updateRow(row.id, { description: e.target.value })
                            }
                            placeholder="description (optional)"
                            className="field min-w-[8rem] flex-1 basis-full px-2 py-1.5 text-xs"
                          />
                        </div>
                      ))
                    )}
                  </div>
                </div>

                <div>
                  <label className="mb-1.5 flex items-center gap-1.5 text-[11px] uppercase tracking-[0.1em] text-zinc-400">
                    <Clock size={12} /> Timeout (seconds)
                  </label>
                  <input
                    type="number"
                    min={1}
                    value={timeout}
                    onChange={(e) => setTimeoutSecs(e.target.value)}
                    placeholder="60"
                    className="field"
                  />
                </div>

                <button
                  type="submit"
                  disabled={busy || !name.trim() || argv.length === 0}
                  className="btn-accent w-full"
                >
                  {busy ? (
                    <LoaderInline label="Creating…" />
                  ) : (
                    <>
                      <Plus size={14} /> Create tool
                    </>
                  )}
                </button>
                {ok && <SuccessNote>{ok}</SuccessNote>}
                {formError && <ErrorNote>{formError}</ErrorNote>}
              </form>
            </Card>
          </div>

          {/* ---------------------------------------------------------------- */}
          {/*  Existing tools                                                  */}
          {/* ---------------------------------------------------------------- */}
          <div className="lg:col-span-2">
            <Card
              title={`Custom tools${tools.length ? ` · ${tools.length}` : ""}`}
              icon={<Wrench size={15} />}
            >
              {loading && !data ? (
                <SkeletonRows rows={4} />
              ) : tools.length === 0 ? (
                <Empty icon={<Wrench size={24} />}>
                  No custom tools yet. Create one on the left — every agent will be able
                  to call it.
                </Empty>
              ) : (
                <div className="space-y-3">
                  {tools.map((tool) => (
                    <div
                      key={tool.name}
                      className="rounded-xl border border-white/[0.06] bg-white/[0.015] px-4 py-3.5 transition-colors hover:border-white/10 hover:bg-white/[0.03]"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <Wrench size={14} className="text-accent-soft" />
                            <span className="font-mono text-sm font-semibold text-zinc-100">
                              {tool.name}
                            </span>
                            <span className="inline-flex items-center gap-1 text-[11px] text-zinc-500">
                              <Clock size={11} /> {tool.timeout_seconds}s
                            </span>
                          </div>
                          {tool.description && (
                            <p className="mt-1.5 text-sm text-zinc-400">
                              {tool.description}
                            </p>
                          )}
                        </div>
                        <ConfirmButton
                          onConfirm={() => remove(tool.name)}
                          label="Delete"
                          title={`Delete tool "${tool.name}"`}
                        />
                      </div>

                      {/* argv command preview */}
                      <div className="mt-3 overflow-x-auto rounded-lg border border-white/[0.06] bg-ink-900/60 px-3 py-2">
                        <code className="whitespace-pre font-mono text-[12px]">
                          {tool.command.map((tok, i) => {
                            const isPh = /^\{.+\}$/.test(tok);
                            return (
                              <span
                                key={i}
                                className={isPh ? "text-accent-soft" : "text-zinc-300"}
                              >
                                {tok}
                                {i < tool.command.length - 1 ? " " : ""}
                              </span>
                            );
                          })}
                        </code>
                      </div>

                      {/* parameter chips */}
                      {tool.parameters.length > 0 && (
                        <div className="mt-2.5 flex flex-wrap gap-1.5">
                          {tool.parameters.map((p) => (
                            <span
                              key={p.name}
                              title={p.description || undefined}
                              className="inline-flex items-center gap-1 rounded-md border border-white/[0.07] bg-white/[0.03] px-1.5 py-0.5 font-mono text-[11px] text-zinc-300"
                            >
                              {p.name}
                              {p.required && (
                                <span className="text-rose-300" title="required">
                                  *
                                </span>
                              )}
                              <span className="text-zinc-600">{p.type}</span>
                            </span>
                          ))}
                        </div>
                      )}

                      <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-zinc-600">
                        <span className="inline-flex items-center gap-1">
                          <User size={11} />
                          {tool.created_by || "unknown"}
                        </span>
                        <span>·</span>
                        <span>{timeAgo(tool.created_at)}</span>
                        {tool.parameters.length > 0 && (
                          <>
                            <span>·</span>
                            <Badge
                              value={`${tool.parameters.length} param${
                                tool.parameters.length === 1 ? "" : "s"
                              }`}
                              tone="violet"
                            />
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        </div>
      </Reveal>

      {/* ------------------------------------------------------------------ */}
      {/*  Tool suite — curated, one-click ready-made tools                  */}
      {/* ------------------------------------------------------------------ */}
      <Reveal>
        <Card
          title={`Tool suite · ${TOOL_SUITE.length}`}
          icon={<Boxes size={15} />}
        >
          <p className="mb-4 text-sm text-zinc-400">
            Ready-made, Windows-friendly tools. Click{" "}
            <span className="font-medium text-accent-soft">Add</span> and every agent
            can call it by name — no setup required.
          </p>
          {suiteOk && (
            <div className="mb-3">
              <SuccessNote>{suiteOk}</SuccessNote>
            </div>
          )}
          {suiteError && (
            <div className="mb-3">
              <ErrorNote>{suiteError}</ErrorNote>
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {TOOL_SUITE.map((t) => {
              const added = installed.has(t.name);
              const isAdding = adding === t.name;
              return (
                <div
                  key={t.name}
                  className="flex flex-col rounded-xl border border-white/[0.06] bg-white/[0.015] p-4 transition-colors hover:border-white/10 hover:bg-white/[0.03]"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      {t.icon}
                      <span className="truncate font-mono text-sm font-semibold text-zinc-100">
                        {t.name}
                      </span>
                    </div>
                    {added ? (
                      <span className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-emerald-500/30 bg-emerald-500/[0.1] px-2 py-1 text-[11px] font-medium text-emerald-300">
                        <Check size={12} /> Added
                      </span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => addFromSuite(t)}
                        disabled={isAdding}
                        title={`Add "${t.name}"`}
                        className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-accent/30 bg-accent/[0.08] px-2 py-1 text-[11px] font-medium text-accent-soft transition-colors hover:bg-accent/[0.14] disabled:opacity-50"
                      >
                        {isAdding ? (
                          <LoaderInline label="Adding…" />
                        ) : (
                          <>
                            <Plus size={12} /> Add
                          </>
                        )}
                      </button>
                    )}
                  </div>

                  <p className="mt-2 text-[13px] text-zinc-400">{t.description}</p>

                  {/* argv command preview */}
                  <div className="mt-3 flex flex-wrap gap-1">
                    {t.command.map((tok, i) => {
                      const isPh = /^\{.+\}$/.test(tok);
                      return (
                        <span
                          key={i}
                          className={`rounded-md border px-1.5 py-0.5 font-mono text-[11px] ${
                            isPh
                              ? "border-accent/30 bg-accent/[0.08] text-accent-soft"
                              : "border-white/[0.06] bg-white/[0.03] text-zinc-300"
                          }`}
                        >
                          {tok}
                        </span>
                      );
                    })}
                  </div>

                  {/* parameter chips */}
                  {t.parameters.length > 0 && (
                    <div className="mt-2.5 flex flex-wrap gap-1.5">
                      {t.parameters.map((p) => (
                        <span
                          key={p.name}
                          title={p.description || undefined}
                          className="inline-flex items-center gap-1 rounded-md border border-white/[0.07] bg-white/[0.03] px-1.5 py-0.5 font-mono text-[11px] text-zinc-300"
                        >
                          {p.name}
                          {p.required && (
                            <span className="text-rose-300" title="required">
                              *
                            </span>
                          )}
                          <span className="text-zinc-600">{p.type}</span>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </Card>
      </Reveal>
    </PageShell>
  );
}
