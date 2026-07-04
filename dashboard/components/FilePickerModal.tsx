"use client";

// Shared file/folder picker modal. Browses the machine one directory at a time
// via the daemon's filesystem endpoints (the same ones DirectoryTree uses):
//   GET /fs/drives                    -> { drives: [{ path, label }] }
//   GET /fs/list?path=..&dirs_only=.. -> { path, parent, entries: FsEntry[] }
// In file mode clicking a file picks it; in folder mode (`pickFolders`) a
// "Choose this folder" button picks the currently open directory.

import { useEffect, useState } from "react";
import {
  Check,
  ChevronRight,
  CornerLeftUp,
  File,
  Folder,
  FolderOpen,
  HardDrive,
  Loader2,
  TriangleAlert,
  X,
} from "lucide-react";
import { ApiError, get } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import type { Drive, FsEntry, FsListing } from "@/lib/types";

interface Crumb {
  label: string;
  path: string;
}

/** Split an absolute path into clickable breadcrumb segments. */
function crumbsFor(p: string): Crumb[] {
  const sep = p.includes("\\") ? "\\" : "/";
  const trimmed = p.replace(/[\\/]+$/, "");
  const parts = trimmed.split(/[\\/]/).filter(Boolean);
  const crumbs: Crumb[] = [];
  // POSIX paths start at "/"; Windows paths start at the drive segment ("C:\").
  if (sep === "/") crumbs.push({ label: "/", path: "/" });
  let acc = sep === "/" ? "/" : "";
  for (const part of parts) {
    if (acc === "") acc = `${part}${sep}`; // drive root, keep the trailing sep
    else acc = acc.endsWith(sep) ? `${acc}${part}` : `${acc}${sep}${part}`;
    crumbs.push({ label: part, path: acc });
  }
  return crumbs;
}

function fmtSize(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(1)} GB`;
}

export function FilePickerModal({
  open,
  onClose,
  onPick,
  pickFolders = false,
  title,
}: {
  open: boolean;
  onClose: () => void;
  /** Receives the absolute path of the chosen file (or folder in folder mode). */
  onPick: (path: string) => void;
  /** Folder mode: list directories only and pick the CURRENT folder. */
  pickFolders?: boolean;
  title?: string;
}) {
  const { data: drivesData, loading: drivesLoading } = useApi<{ drives: Drive[] }>(
    open ? "/fs/drives" : null,
  );
  const drives = drivesData?.drives ?? [];

  const [cur, setCur] = useState<string | null>(null);
  const [listing, setListing] = useState<FsListing | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Default to the first drive once drives load (remember the last folder
  // browsed across re-opens within the same page).
  useEffect(() => {
    if (open && cur === null && drives.length > 0) setCur(drives[0].path);
  }, [open, cur, drives]);

  // Load the current directory whenever it changes while the modal is open.
  useEffect(() => {
    if (!open || !cur) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    const qs = `path=${encodeURIComponent(cur)}${pickFolders ? "&dirs_only=true" : ""}`;
    get<FsListing>(`/fs/list?${qs}`)
      .then((d) => {
        if (!cancelled) setListing(d);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof ApiError ? e.message : String(e));
          setListing(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, cur, pickFolders]);

  // Escape closes.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const heading = title ?? (pickFolders ? "Pick a folder" : "Pick a file");
  const crumbs = cur ? crumbsFor(cur) : [];
  const parent = listing?.parent ?? null;
  // Directories first, stable within each group.
  const entries: FsEntry[] = listing
    ? [...listing.entries].sort((a, b) => Number(b.is_dir) - Number(a.is_dir))
    : [];

  function pickEntry(e: FsEntry) {
    if (e.is_dir) {
      setCur(e.path);
    } else {
      onPick(e.path);
      onClose();
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={heading}
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[70vh] w-full max-w-[34rem] flex-col overflow-hidden rounded-2xl border border-white/10 bg-ink-850/95 shadow-card-hover backdrop-blur-xl"
      >
        {/* Header ---------------------------------------------------------- */}
        <header className="flex shrink-0 items-center gap-2 border-b hairline px-4 py-3">
          <FolderOpen size={16} className="text-accent-soft/80" />
          <h2 className="text-[13px] font-semibold tracking-wide text-zinc-200">
            {heading}
          </h2>
          <button
            type="button"
            onClick={onClose}
            title="Close"
            className="ml-auto grid h-6 w-6 place-items-center rounded-md text-zinc-500 transition-colors hover:bg-white/[0.06] hover:text-zinc-200"
          >
            <X size={14} />
          </button>
        </header>

        {/* Drive selector row ---------------------------------------------- */}
        <div className="flex shrink-0 flex-wrap items-center gap-1.5 border-b hairline px-4 py-2.5">
          <HardDrive size={13} className="shrink-0 text-accent-soft/70" />
          {drivesLoading && drives.length === 0 && (
            <span className="text-[11px] text-zinc-500">loading drives…</span>
          )}
          {!drivesLoading && drives.length === 0 && (
            <span className="text-[11px] text-zinc-600">no drives</span>
          )}
          {drives.map((d) => {
            const active =
              cur !== null && cur.toLowerCase().startsWith(d.path.toLowerCase());
            return (
              <button
                key={d.path}
                type="button"
                onClick={() => setCur(d.path)}
                title={d.path}
                className={`rounded-lg border px-2.5 py-1 font-mono text-[11px] transition-colors ${
                  active
                    ? "border-accent/40 bg-accent/[0.1] text-accent-soft"
                    : "border-white/10 text-zinc-400 hover:border-white/20 hover:text-zinc-200"
                }`}
              >
                {d.label}
              </button>
            );
          })}
        </div>

        {/* Breadcrumb ------------------------------------------------------- */}
        <div className="flex shrink-0 flex-wrap items-center gap-0.5 border-b hairline px-4 py-2">
          {crumbs.length === 0 && (
            <span className="text-[11px] text-zinc-600">—</span>
          )}
          {crumbs.map((c, i) => (
            <span key={c.path} className="flex items-center gap-0.5">
              {i > 0 && <ChevronRight size={11} className="text-zinc-600" />}
              <button
                type="button"
                onClick={() => setCur(c.path)}
                title={c.path}
                className={`max-w-[9rem] truncate rounded px-1 py-0.5 font-mono text-[11.5px] transition-colors ${
                  i === crumbs.length - 1
                    ? "text-accent-soft"
                    : "text-zinc-400 hover:bg-white/[0.06] hover:text-zinc-200"
                }`}
              >
                {c.label}
              </button>
            </span>
          ))}
        </div>

        {/* Directory listing ------------------------------------------------ */}
        <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
          {loading && (
            <div className="flex items-center gap-2 px-2 py-3 text-[12px] text-zinc-500">
              <Loader2 size={13} className="animate-spin" /> loading…
            </div>
          )}
          {!loading && error && (
            <div className="flex items-start gap-2 px-2 py-3 text-[12px] text-rose-300/80">
              <TriangleAlert size={13} className="mt-0.5 shrink-0" /> {error}
            </div>
          )}
          {!loading && !error && listing && (
            <>
              {parent !== null && (
                <button
                  type="button"
                  onClick={() => setCur(parent)}
                  title={parent}
                  className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[12.5px] text-zinc-400 transition-colors hover:bg-white/[0.05] hover:text-zinc-200"
                >
                  <CornerLeftUp size={14} className="shrink-0 text-zinc-500" />
                  <span className="font-mono">..</span>
                </button>
              )}
              {entries.length === 0 && (
                <div className="px-2 py-3 text-[12px] text-zinc-600">
                  {pickFolders ? "no subfolders" : "empty folder"}
                </div>
              )}
              {entries.map((e) => (
                <button
                  key={e.path}
                  type="button"
                  onClick={() => pickEntry(e)}
                  title={e.path}
                  className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[12.5px] text-zinc-300 transition-colors hover:bg-white/[0.05] hover:text-zinc-100"
                >
                  {e.is_dir ? (
                    <Folder size={14} className="shrink-0 text-accent-soft/80" />
                  ) : (
                    <File size={14} className="shrink-0 text-zinc-500" />
                  )}
                  <span className="truncate">{e.name}</span>
                  {e.is_dir ? (
                    <ChevronRight
                      size={12}
                      className="ml-auto shrink-0 text-zinc-600"
                    />
                  ) : (
                    e.size !== null && (
                      <span className="ml-auto shrink-0 text-[10.5px] tabular-nums text-zinc-600">
                        {fmtSize(e.size)}
                      </span>
                    )
                  )}
                </button>
              ))}
            </>
          )}
        </div>

        {/* Footer ------------------------------------------------------------ */}
        <footer className="flex shrink-0 items-center gap-3 border-t hairline px-4 py-3">
          <div
            className="min-w-0 flex-1 truncate font-mono text-[12px] text-accent-soft"
            title={cur ?? undefined}
          >
            {cur ?? "—"}
          </div>
          {pickFolders ? (
            <button
              type="button"
              disabled={!cur}
              onClick={() => {
                if (cur) {
                  onPick(cur);
                  onClose();
                }
              }}
              className="btn-accent shrink-0 px-3 py-1.5 text-[12px]"
            >
              <Check size={13} /> Choose this folder
            </button>
          ) : (
            <span className="shrink-0 text-[11px] text-zinc-600">
              Click a file to select it
            </span>
          )}
        </footer>
      </div>
    </div>
  );
}
