"use client";

import {
  GraduationCap,
  Star,
  MessageSquare,
  Brain,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { useApi } from "@/lib/useApi";
import type { Lesson } from "@/lib/types";
import {
  Card,
  Badge,
  Empty,
  OfflineHint,
  SkeletonRows,
  type Tone,
} from "@/components/ui";
import { PageHeader } from "@/components/PageHeader";
import { PageShell, Reveal } from "@/components/motion";
import { timeAgo } from "@/lib/format";

interface SourceMeta {
  label: string;
  tone: Tone;
  Icon: LucideIcon;
  blurb: string;
}

const SOURCE_META: Record<string, SourceMeta> = {
  preference: {
    label: "preference",
    tone: "amber",
    Icon: Star,
    blurb: "something you told me you prefer",
  },
  feedback: {
    label: "feedback",
    tone: "cyan",
    Icon: MessageSquare,
    blurb: "learned from a thumbs up/down",
  },
  reflection: {
    label: "reflection",
    tone: "violet",
    Icon: Brain,
    blurb: "noticed while reflecting on a session",
  },
};

function metaFor(source: string): SourceMeta {
  return (
    SOURCE_META[source] ?? {
      label: source || "lesson",
      tone: "slate",
      Icon: Sparkles,
      blurb: "",
    }
  );
}

export default function LessonsPage() {
  const { data, error, loading } = useApi<{ lessons: Lesson[] }>(
    "/lessons?limit=50",
  );

  const offline = error && error.status === 0;
  const lessons = data?.lessons ?? [];

  return (
    <PageShell>
      <Reveal>
        <PageHeader
          title="What I've learned"
          subtitle="Iron Jarvis gets better every time you work with it — here's what it's picked up about how you like to work."
        />
      </Reveal>

      {offline && (
        <Reveal>
          <OfflineHint />
        </Reveal>
      )}

      <Reveal>
        <Card
          title={`Lessons${lessons.length ? ` · ${lessons.length}` : ""}`}
          icon={<GraduationCap size={15} />}
        >
          {loading && !data ? (
            <SkeletonRows rows={4} />
          ) : lessons.length === 0 ? (
            <Empty icon={<GraduationCap size={24} />}>
              Nothing yet — give a session a 👍/👎 and I&apos;ll start learning.
            </Empty>
          ) : (
            <ul className="space-y-3">
              {lessons.map((lesson, i) => {
                const m = metaFor(lesson.source);
                const Icon = m.Icon;
                return (
                  <li
                    key={lesson.id ?? `${lesson.source}/${i}`}
                    className="group flex items-start gap-3.5 rounded-xl border border-white/[0.05] bg-white/[0.02] px-4 py-3.5 transition-colors hover:border-white/[0.1]"
                  >
                    <span
                      className={`mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl border ${
                        m.tone === "amber"
                          ? "border-amber-500/25 bg-amber-500/10 text-amber-300"
                          : m.tone === "cyan"
                            ? "border-accent/30 bg-accent/10 text-accent-soft"
                            : m.tone === "violet"
                              ? "border-violet-500/25 bg-violet-500/10 text-violet-300"
                              : "border-white/10 bg-white/[0.04] text-zinc-400"
                      }`}
                    >
                      <Icon size={17} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-[15px] leading-relaxed text-zinc-100">
                        {lesson.text}
                      </p>
                      <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-zinc-500">
                        <Badge value={m.label} tone={m.tone} />
                        <span className="text-zinc-600">·</span>
                        <span title="injection priority">
                          weight {lesson.weight}
                        </span>
                        {lesson.scope && (
                          <>
                            <span className="text-zinc-600">·</span>
                            <span>{lesson.scope}</span>
                          </>
                        )}
                        {lesson.created_at && (
                          <>
                            <span className="text-zinc-600">·</span>
                            <span>{timeAgo(lesson.created_at)}</span>
                          </>
                        )}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
      </Reveal>

      {lessons.length > 0 && (
        <Reveal>
          <div className="flex items-center gap-2 px-1 text-xs text-zinc-600">
            <Sparkles size={13} className="text-accent-soft/60" />
            These lessons are quietly added to every future run, so I keep getting
            closer to how you like things done.
          </div>
        </Reveal>
      )}
    </PageShell>
  );
}
