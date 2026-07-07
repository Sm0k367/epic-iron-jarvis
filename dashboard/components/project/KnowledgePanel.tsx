"use client";

// The project's knowledge base. Every item here grounds every chat and task in
// the project (the daemon injects it into prompts). Two ways to add: paste a
// note (name + text) or upload a file (base64 → the daemon extracts its text).

import { useRef, useState } from "react";
import {
  BookOpen,
  Check,
  FileText,
  Plus,
  StickyNote,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useApi } from "@/lib/useApi";
import { post, del, ApiError } from "@/lib/api";
import { Card, Empty, ErrorNote, LoaderInline, SkeletonRows } from "@/components/ui";
import { timeAgo } from "@/lib/format";

interface KnowledgeItem {
  id: string;
  name: string;
  kind: string; // "note" | "file"
  size: number;
  created_at: string;
}

const MAX_FILE_BYTES = 20 * 1024 * 1024; // 20 MB

function errText(err: unknown): string {
  return err instanceof ApiError ? err.message : String(err);
}

/** Read a File as raw base64 (FileReader gives a data: URL — strip the prefix). */
function readAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("could not read file"));
    reader.onload = () => {
      const res = String(reader.result);
      const comma = res.indexOf(",");
      resolve(comma >= 0 ? res.slice(comma + 1) : res);
    };
    reader.readAsDataURL(file);
  });
}

/** Whole KB in KB, rounded (min 1 for any non-empty item). */
function kb(bytes: number): number {
  return Math.max(1, Math.round((bytes || 0) / 1024));
}

export function KnowledgePanel({ projectId }: { projectId: string }) {
  const { data, loading, error, reload } = useApi<{
    knowledge: KnowledgeItem[];
    count: number;
  }>(`/projects/${encodeURIComponent(projectId)}/knowledge`);
  const items = data?.knowledge ?? [];
  const totalBytes = items.reduce((s, i) => s + (i.size || 0), 0);

  const [noteOpen, setNoteOpen] = useState(false);
  const [noteName, setNoteName] = useState("");
  const [noteText, setNoteText] = useState("");
  const [saving, setSaving] = useState(false);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const base = `/projects/${encodeURIComponent(projectId)}/knowledge`;

  async function addNote() {
    if (!noteText.trim()) return;
    setSaving(true);
    setErr(null);
    try {
      await post(base, {
        ...(noteName.trim() ? { name: noteName.trim() } : {}),
        text: noteText.trim(),
      });
      setNoteName("");
      setNoteText("");
      setNoteOpen(false);
      reload();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setSaving(false);
    }
  }

  async function addFiles(files: File[]) {
    if (!files.length) return;
    setUploadBusy(true);
    setErr(null);
    try {
      let added = false;
      for (const f of files) {
        if (f.size > MAX_FILE_BYTES) {
          setErr(`${f.name} is too large (max 20 MB).`);
          continue;
        }
        const content_b64 = await readAsBase64(f);
        await post(base, { filename: f.name, content_b64 });
        added = true;
      }
      if (added) reload();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setUploadBusy(false);
    }
  }

  function onPickFiles(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files ? Array.from(e.target.files) : [];
    e.target.value = "";
    if (files.length) void addFiles(files);
  }

  async function remove(id: string) {
    setErr(null);
    try {
      await del(`${base}/${encodeURIComponent(id)}`);
      reload();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setPendingDelete(null);
    }
  }

  return (
    <Card
      title="Knowledge"
      icon={<BookOpen size={15} />}
      right={
        <span className="text-[11px] text-zinc-500">
          {items.length} item{items.length === 1 ? "" : "s"}
          {totalBytes > 0 ? ` · ${kb(totalBytes)} KB` : ""}
        </span>
      }
    >
      <p className="mb-3 text-[12px] text-zinc-500">
        Knowledge grounds every chat and task in this project.
      </p>

      <div className="mb-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => setNoteOpen((o) => !o)}
          className="btn-ghost !px-2.5 !py-1 text-xs"
        >
          <Plus size={13} /> Paste a note
        </button>
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={uploadBusy}
          className="btn-ghost !px-2.5 !py-1 text-xs"
        >
          {uploadBusy ? (
            <LoaderInline label="Uploading…" />
          ) : (
            <>
              <Upload size={13} /> Add file
            </>
          )}
        </button>
        <input ref={fileRef} type="file" multiple className="hidden" onChange={onPickFiles} />
      </div>

      {noteOpen && (
        <div className="mb-3 space-y-2 rounded-lg border hairline bg-white/[0.02] p-3">
          <input
            value={noteName}
            onChange={(e) => setNoteName(e.target.value)}
            placeholder="Note name (optional)"
            aria-label="Knowledge note name"
            className="field text-sm"
          />
          <textarea
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
            rows={4}
            placeholder="Paste facts, context, or guidelines the AI should always know…"
            aria-label="Knowledge note text"
            className="field resize-y text-sm"
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={addNote}
              disabled={saving || !noteText.trim()}
              className="btn-accent"
            >
              {saving ? <LoaderInline label="Saving…" /> : "Add note"}
            </button>
            <button
              type="button"
              onClick={() => {
                setNoteOpen(false);
                setNoteName("");
                setNoteText("");
              }}
              className="btn-ghost"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {err && (
        <div className="mb-3">
          <ErrorNote>{err}</ErrorNote>
        </div>
      )}

      {loading && !data ? (
        <SkeletonRows rows={3} />
      ) : error && error.status === 0 ? (
        <p className="py-2 text-sm text-zinc-500">
          Knowledge unavailable — the daemon looks offline.
        </p>
      ) : items.length === 0 ? (
        <Empty icon={<BookOpen size={22} />}>
          No knowledge yet — paste a note or add a file to ground this project.
        </Empty>
      ) : (
        <ul className="space-y-1.5">
          {items.map((it) => (
            <li
              key={it.id}
              className="group flex items-center gap-2 rounded-lg border border-white/[0.05] bg-white/[0.02] px-3 py-2"
            >
              <span className="shrink-0 text-zinc-500">
                {it.kind === "note" ? <StickyNote size={14} /> : <FileText size={14} />}
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs text-zinc-200">{it.name}</div>
                <div className="text-[10px] text-zinc-600">
                  {kb(it.size)} KB · {timeAgo(it.created_at)}
                </div>
              </div>
              {pendingDelete === it.id ? (
                <span className="flex shrink-0 items-center gap-1">
                  <button
                    type="button"
                    onClick={() => void remove(it.id)}
                    className="rounded p-1 text-rose-300"
                    title="Confirm delete"
                  >
                    <Check size={13} />
                  </button>
                  <button
                    type="button"
                    onClick={() => setPendingDelete(null)}
                    className="rounded p-1 text-zinc-500"
                    title="Cancel"
                  >
                    <X size={13} />
                  </button>
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => setPendingDelete(it.id)}
                  className="shrink-0 rounded p-1 text-zinc-600 opacity-0 transition-opacity hover:text-rose-300 group-hover:opacity-100"
                  title="Remove"
                >
                  <Trash2 size={13} />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
