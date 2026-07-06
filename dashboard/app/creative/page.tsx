"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import Link from "next/link";
import {
  Sparkles,
  Image as ImageIcon,
  Film,
  Music,
  Upload,
  Download,
  Globe,
  Copy,
  Check,
  X,
  ArrowRight,
} from "lucide-react";
import { API_BASE, ApiError, ijToken, post } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useEvents } from "@/lib/useEvents";
import { timeAgo } from "@/lib/format";
import {
  Card,
  Empty,
  ErrorNote,
  SuccessNote,
  LoaderInline,
  OfflineHint,
  Skeleton,
} from "@/components/ui";
import { PageHeader } from "@/components/PageHeader";
import { PageShell, Reveal } from "@/components/motion";

/* ---- API shapes (mirror the daemon's /creative routes) -------------------- */

type MediaKind = "image" | "video" | "audio";

interface CreativeItem {
  name: string;
  version: number;
  media: MediaKind;
  kind: string;
  filename: string;
  size: number;
  session_id: string | null;
  created_at: string;
  url: string; // "/creative/file/<name>"
}

interface UploadResult {
  name: string;
  version: number;
  media: MediaKind;
  size: number;
  url?: string;
  publish_error?: string;
}

/* ---- helpers --------------------------------------------------------------- */

const MAX_UPLOAD_BYTES = 100 * 1024 * 1024; // client-side sanity guard (~100 MB)

/** Media tags can't send the Authorization header — the token rides as ?token=. */
function fileSrc(item: CreativeItem): string {
  const token = ijToken();
  return `${API_BASE}${item.url}${token ? `?token=${encodeURIComponent(token)}` : ""}`;
}

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${bytes} B`;
}

function mediaIcon(media: MediaKind, size = 13): ReactNode {
  if (media === "image") return <ImageIcon size={size} />;
  if (media === "video") return <Film size={size} />;
  return <Music size={size} />;
}

function readAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result ?? "");
      const comma = result.indexOf(",");
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.onerror = () => reject(new Error(`Could not read ${file.name}`));
    reader.readAsDataURL(file);
  });
}

/* ---- Public URL box --------------------------------------------------------- */

function PublicUrlBox({ url, autoCopy = false }: { url: string; autoCopy?: boolean }) {
  const [copied, setCopied] = useState(false);
  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      /* clipboard unavailable — the button stays available */
    }
  }, [url]);
  useEffect(() => {
    if (autoCopy) void copy();
  }, [autoCopy, copy]);
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2 rounded-xl border border-white/[0.08] bg-ink-950 px-3 py-2">
        <code className="min-w-0 flex-1 truncate font-mono text-xs text-zinc-300">{url}</code>
        <button
          type="button"
          onClick={copy}
          aria-label="Copy URL"
          title="Copy URL"
          className="shrink-0 rounded-lg border border-transparent p-1 text-zinc-400 transition-colors hover:border-white/10 hover:bg-white/[0.04] hover:text-zinc-200"
        >
          {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
        </button>
      </div>
      <p className="text-[11px] text-zinc-500">
        {copied ? "Copied to clipboard ✓ — " : ""}clean, permanent, public — paste it into any
        generation param.
      </p>
    </div>
  );
}

/* ---- Grid tile --------------------------------------------------------------- */

function MediaTile({ item, onOpen }: { item: CreativeItem; onOpen: () => void }) {
  const src = fileSrc(item);
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
      className="card-surface group cursor-pointer overflow-hidden text-left transition-all duration-300 hover:-translate-y-0.5 hover:shadow-card-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
    >
      <div className="relative aspect-video w-full overflow-hidden bg-ink-950">
        {item.media === "image" ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={src}
            alt={item.filename}
            loading="lazy"
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
          />
        ) : item.media === "video" ? (
          <video
            src={src}
            muted
            playsInline
            preload="metadata"
            className="h-full w-full object-cover"
            onMouseEnter={(e) => {
              e.currentTarget.play().catch(() => {});
            }}
            onMouseLeave={(e) => {
              e.currentTarget.pause();
              e.currentTarget.currentTime = 0;
            }}
          />
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center gap-3 px-4">
            <Music size={22} className="text-accent-soft/70" />
            <audio
              src={src}
              controls
              preload="metadata"
              className="h-8 w-full"
              onClick={(e) => e.stopPropagation()}
              onKeyDown={(e) => e.stopPropagation()}
            />
          </div>
        )}
        <span className="absolute right-2 top-2 inline-flex items-center gap-1 rounded-full border border-white/10 bg-black/50 px-2 py-0.5 text-[10px] font-medium capitalize text-zinc-300 backdrop-blur">
          {mediaIcon(item.media, 10)} {item.media}
        </span>
      </div>
      <div className="flex items-center justify-between gap-2 px-3 py-2.5">
        <span className="min-w-0 truncate text-xs text-zinc-300" title={item.filename}>
          {item.filename}
        </span>
        <span className="shrink-0 text-[11px] text-zinc-500">{timeAgo(item.created_at)}</span>
      </div>
    </div>
  );
}

/* ---- Lightbox ----------------------------------------------------------------- */

function Lightbox({ item, onClose }: { item: CreativeItem; onClose: () => void }) {
  const src = fileSrc(item);
  const [pubBusy, setPubBusy] = useState(false);
  const [pubUrl, setPubUrl] = useState<string | null>(null);
  const [pubErr, setPubErr] = useState<{ detail: string; notConnected: boolean } | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const publish = async () => {
    setPubBusy(true);
    setPubErr(null);
    try {
      const res = await post<{ url: string }>("/creative/publish", { name: item.name });
      setPubUrl(res.url);
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e), 0);
      setPubErr({ detail: err.message, notConnected: err.status === 424 });
    } finally {
      setPubBusy(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={item.filename}
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="card-surface flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden"
      >
        <header className="flex items-center justify-between gap-3 border-b hairline px-5 py-3.5">
          <h2 className="flex min-w-0 items-center gap-2 text-[13px] font-semibold tracking-wide text-zinc-200">
            <span className="shrink-0 text-accent-soft/80">{mediaIcon(item.media, 15)}</span>
            <span className="truncate">{item.filename}</span>
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 rounded-lg border border-transparent p-1.5 text-zinc-400 transition-colors hover:border-white/10 hover:bg-white/[0.04] hover:text-zinc-200"
          >
            <X size={16} />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="flex items-center justify-center bg-ink-950">
            {item.media === "image" ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={src}
                alt={item.filename}
                className="max-h-[55vh] w-auto max-w-full object-contain"
              />
            ) : item.media === "video" ? (
              <video src={src} controls autoPlay playsInline className="max-h-[55vh] w-full" />
            ) : (
              <div className="w-full px-6 py-10">
                <audio src={src} controls autoPlay className="w-full" />
              </div>
            )}
          </div>

          <div className="space-y-4 p-5">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-zinc-500">
              <span className="font-mono">{formatSize(item.size)}</span>
              <span>{timeAgo(item.created_at)}</span>
              <span className="font-mono">v{item.version}</span>
              {item.session_id && (
                <Link
                  href={`/sessions/${item.session_id}`}
                  className="inline-flex items-center gap-1 text-accent-soft transition-colors hover:text-accent"
                >
                  from session <ArrowRight size={12} />
                </Link>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={publish}
                disabled={pubBusy}
                className="inline-flex items-center gap-1.5 rounded-xl border border-accent/30 bg-accent/[0.08] px-3 py-1.5 text-xs font-medium text-accent-soft transition-colors hover:bg-accent/[0.14] disabled:opacity-50"
              >
                {pubBusy ? (
                  <LoaderInline label="Publishing…" />
                ) : (
                  <>
                    <Globe size={13} /> Get public URL
                  </>
                )}
              </button>
              <a
                href={src}
                download={item.filename}
                className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 px-3 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:border-white/20 hover:bg-white/[0.04]"
              >
                <Download size={13} /> Download
              </a>
            </div>

            {pubUrl && <PublicUrlBox url={pubUrl} autoCopy />}
            {pubErr && (
              <ErrorNote>
                {pubErr.detail}
                {pubErr.notConnected && (
                  <>
                    {" "}
                    <Link
                      href="/connections"
                      className="font-medium text-accent-soft underline underline-offset-2 hover:text-accent"
                    >
                      Connect Pixio →
                    </Link>
                  </>
                )}
              </ErrorNote>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ---- Page ---------------------------------------------------------------------- */

type Filter = "all" | MediaKind;

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "image", label: "Images" },
  { key: "video", label: "Video" },
  { key: "audio", label: "Audio" },
];

export default function CreativePage() {
  const { data, error, loading, reload } = useApi<{ items: CreativeItem[]; count: number }>(
    "/creative/items?limit=200",
  );
  const [filter, setFilter] = useState<Filter>("all");
  const [selected, setSelected] = useState<CreativeItem | null>(null);
  const closeLightbox = useCallback(() => setSelected(null), []);

  // Live: refetch the moment the daemon emits artifact.generated (dedupe by event id).
  const { events } = useEvents(50);
  const lastGeneratedId = events.find((e) => e.type === "artifact.generated")?.id;
  const [flash, setFlash] = useState(false);
  useEffect(() => {
    if (!lastGeneratedId) return;
    reload();
    setFlash(true);
    const t = setTimeout(() => setFlash(false), 4000);
    return () => clearTimeout(t);
  }, [lastGeneratedId, reload]);

  // Upload affordance.
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [alsoPublish, setAlsoPublish] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadOk, setUploadOk] = useState<string | null>(null);
  const [uploadErr, setUploadErr] = useState<string | null>(null);
  const [uploadUrl, setUploadUrl] = useState<string | null>(null);

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-picking the same file
    if (!file) return;
    setUploadOk(null);
    setUploadErr(null);
    setUploadUrl(null);
    if (file.size > MAX_UPLOAD_BYTES) {
      setUploadErr(
        `"${file.name}" is ${formatSize(file.size)} — uploads are capped around 100 MB. Try a smaller file.`,
      );
      return;
    }
    setUploading(true);
    try {
      const content_b64 = await readAsBase64(file);
      const res = await post<UploadResult>("/creative/upload", {
        filename: file.name,
        content_b64,
        ...(alsoPublish ? { publish: true } : {}),
      });
      setUploadOk(`Uploaded ${file.name} (${formatSize(res.size)}).`);
      if (res.url) setUploadUrl(res.url);
      if (res.publish_error) setUploadErr(`Upload saved, but publishing failed: ${res.publish_error}`);
      reload();
    } catch (err) {
      const ae = err instanceof ApiError ? err : new ApiError(String(err), 0);
      setUploadErr(ae.status === 0 ? "Daemon offline — could not upload." : ae.message);
    } finally {
      setUploading(false);
    }
  };

  const items = data?.items ?? [];
  const counts = useMemo(() => {
    const c: Record<Filter, number> = { all: items.length, image: 0, video: 0, audio: 0 };
    for (const it of items) c[it.media] = (c[it.media] ?? 0) + 1;
    return c;
  }, [items]);
  const visible = filter === "all" ? items : items.filter((i) => i.media === filter);

  const offline = error !== null && error.status === 0;

  return (
    <PageShell>
      <Reveal>
        <PageHeader
          title="Creative"
          subtitle="Everything Iron Jarvis has made — generations land here automatically. Ask for media in Chat (arm the pixio tools with the + menu) or in an agent session."
          actions={
            <div className="flex flex-wrap items-center gap-3">
              <label className="flex cursor-pointer select-none items-center gap-1.5 text-xs text-zinc-400">
                <input
                  type="checkbox"
                  checked={alsoPublish}
                  onChange={(e) => setAlsoPublish(e.target.checked)}
                  className="h-3.5 w-3.5 accent-cyan-400"
                />
                also get a public URL
              </label>
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                disabled={uploading}
                className="inline-flex items-center gap-1.5 rounded-xl border border-accent/30 bg-accent/[0.08] px-3 py-1.5 text-xs font-medium text-accent-soft transition-colors hover:bg-accent/[0.14] disabled:opacity-50"
              >
                {uploading ? (
                  <LoaderInline label="Uploading…" />
                ) : (
                  <>
                    <Upload size={13} /> Upload media
                  </>
                )}
              </button>
              <input
                ref={fileRef}
                type="file"
                accept="image/*,video/*,audio/*"
                className="hidden"
                onChange={onFile}
              />
            </div>
          }
        />
      </Reveal>

      {offline && (
        <Reveal>
          <OfflineHint />
        </Reveal>
      )}
      {error && !offline && (
        <Reveal>
          <ErrorNote>Couldn’t load creations: {error.message}</ErrorNote>
        </Reveal>
      )}

      {(uploadOk || uploadErr || uploadUrl) && (
        <Reveal className="space-y-2">
          {uploadOk && <SuccessNote>{uploadOk}</SuccessNote>}
          {uploadErr && <ErrorNote>{uploadErr}</ErrorNote>}
          {uploadUrl && <PublicUrlBox url={uploadUrl} />}
        </Reveal>
      )}

      <Reveal>
        <div className="flex flex-wrap items-center gap-2">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              onClick={() => setFilter(f.key)}
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                filter === f.key
                  ? "border-accent/30 bg-accent/[0.08] text-accent-soft"
                  : "border-white/10 text-zinc-400 hover:border-white/20 hover:bg-white/[0.04] hover:text-zinc-200"
              }`}
            >
              {f.label}
              <span className="font-mono text-[10px] opacity-70">{counts[f.key]}</span>
            </button>
          ))}
          {flash && (
            <span className="inline-flex animate-pulse items-center gap-1.5 rounded-full border border-accent/30 bg-accent/[0.1] px-3 py-1.5 text-xs font-medium text-accent-soft">
              <Sparkles size={12} /> new creation ✨
            </span>
          )}
        </div>
      </Reveal>

      <Reveal>
        {loading && !data ? (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="card-surface overflow-hidden">
                <Skeleton className="aspect-video w-full" />
                <div className="px-3 py-2.5">
                  <Skeleton className="h-3.5 w-2/3" />
                </div>
              </div>
            ))}
          </div>
        ) : items.length === 0 ? (
          <Card>
            <Empty
              icon={<Sparkles size={22} />}
              action={{ label: "Open Chat", href: "/chat" }}
            >
              Nothing here yet — ask Iron Jarvis to make something, or upload media to use in
              generations.
            </Empty>
          </Card>
        ) : visible.length === 0 ? (
          <Card>
            <Empty icon={mediaIcon(filter === "all" ? "image" : filter, 22)}>
              No {filter} creations yet — try another filter.
            </Empty>
          </Card>
        ) : (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-4">
            {visible.map((item) => (
              <MediaTile
                key={`${item.name}:${item.version}`}
                item={item}
                onOpen={() => setSelected(item)}
              />
            ))}
          </div>
        )}
      </Reveal>

      {selected && (
        <Lightbox
          key={`${selected.name}:${selected.version}`}
          item={selected}
          onClose={closeLightbox}
        />
      )}
    </PageShell>
  );
}
