"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  Bell,
  GitBranch,
  MonitorCog,
  Inbox,
  ArrowRight,
  MessageSquare,
  CalendarClock,
  type LucideIcon,
} from "lucide-react";
import { useEvents } from "@/lib/useEvents";
import { usePolledApi } from "@/lib/useApi";
import { useDesktopNotifications } from "@/lib/useDesktopNotifications";
import type { ComputerUseStatus, IJEvent } from "@/lib/types";
import { shortId, clockTime } from "@/lib/format";

/** Best-effort session id for a review event (top-level wins, then payload). */
function reviewKey(e: IJEvent): string {
  return String(e.session_id ?? (e.payload?.session_id as string | undefined) ?? e.id);
}

/** An informational, stream-driven notification (nothing waits on the user):
 *  an inbound comm message that spawned a session, a schedule that fired, or a
 *  computer-use run that finished. comm.rejected / webhook.received are
 *  deliberately NOT notified — they'd be pure noise; the event stream has them. */
interface ActivityItem {
  id: string;
  ts: string;
  href: string;
  icon: LucideIcon;
  title: string;
  body: string;
}

/** Map one live event to an activity notification (null = not a notified type). */
function toActivity(e: IJEvent): ActivityItem | null {
  const p = e.payload ?? {};
  if (e.type === "comm.received") {
    // Payload: {channel, sender, task} + session_id on the event (comm/inbound.py).
    const channel = typeof p.channel === "string" && p.channel ? p.channel : "a channel";
    const sender = typeof p.sender === "string" && p.sender ? ` (${p.sender})` : "";
    return {
      id: e.id,
      ts: e.ts,
      href: "/sessions",
      icon: MessageSquare,
      title: `Inbound message from ${channel}${sender} started a session`,
      body: typeof p.task === "string" ? p.task : "",
    };
  }
  if (e.type === "schedule.fired") {
    // Payload is the schedule's own payload dict — name/workflow when present.
    const name =
      (typeof p.name === "string" && p.name) ||
      (typeof p.workflow === "string" && p.workflow) ||
      (typeof p.type === "string" && p.type) ||
      "event";
    return {
      id: e.id,
      ts: e.ts,
      href: "/schedules",
      icon: CalendarClock,
      title: `Scheduled job ran: ${name}`,
      body: "",
    };
  }
  if (e.type === "computeruse.run_finished") {
    // Payload: {run_id, status, steps}; "completed" is the only good terminal
    // status (failed/blocked/awaiting_approval all mean the task didn't finish).
    const status = typeof p.status === "string" && p.status ? p.status : "finished";
    const ok = status === "completed";
    const steps =
      typeof p.steps === "number" ? `${p.steps} step${p.steps === 1 ? "" : "s"}` : "";
    const runId = typeof p.run_id === "string" ? p.run_id : "";
    return {
      id: e.id,
      ts: e.ts,
      href: "/computeruse",
      icon: MonitorCog,
      title: `Computer-use run finished — ${ok ? "ok" : "failed"}`,
      body: [status, steps, runId].filter(Boolean).join(" · "),
    };
  }
  return null;
}

/**
 * Notification center: a bell + unread badge counting work that needs a human —
 * unresolved review requests (from the live event stream) plus any pending
 * computer-use approvals (polled). Clicking opens a dropdown of deep links.
 * Self-contained; renders a calm "all clear" state when nothing is pending.
 */
export function NotificationBell() {
  const { events } = useEvents(100);
  // Computer-use approvals don't ride the event stream, so poll their count.
  const cu = usePolledApi<ComputerUseStatus>("/computeruse", 15000);
  const pendingApprovals = cu.data?.pending_approvals ?? 0;
  // The live event buffer is empty right after a page reload, so seed the pending
  // review count from /diagnostics (the authoritative current count) — otherwise
  // a reload silently hides reviews that are still waiting on the user.
  const diag = usePolledApi<{ pending_reviews?: number }>("/diagnostics", 15000);
  const polledReviews = diag.data?.pending_reviews ?? 0;

  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Unresolved review.requested events: dedupe by session and drop any whose
  // review later resolved/approved/rejected (defensive — those types may not
  // exist yet, in which case every requested review simply stays pending).
  const reviews = useMemo(() => {
    const resolved = new Set<string>();
    for (const e of events) {
      if (e.type.startsWith("review.") && e.type !== "review.requested") {
        resolved.add(reviewKey(e));
      }
    }
    const seen = new Set<string>();
    const out: IJEvent[] = [];
    for (const e of events) {
      if (e.type !== "review.requested") continue;
      const key = reviewKey(e);
      if (resolved.has(key) || seen.has(key)) continue;
      seen.add(key);
      out.push(e);
    }
    return out;
  }, [events]);

  // Informational activity (inbound comm / schedule fires / finished
  // computer-use runs): shown in the dropdown + pinged to the desktop, but NOT
  // counted as pending — nothing here waits on the user, so it must not
  // inflate the badge or the tab title. Dedupe by event id, keep the 6 newest
  // (the events buffer is already newest-first).
  const activity = useMemo(() => {
    const out: ActivityItem[] = [];
    const seen = new Set<string>();
    for (const e of events) {
      const item = toActivity(e);
      if (!item || seen.has(item.id)) continue;
      seen.add(item.id);
      out.push(item);
      if (out.length >= 6) break;
    }
    return out;
  }, [events]);

  // Use the larger of live-streamed vs polled reviews so neither a fresh reload
  // (no events yet) nor a just-arrived live event under-reports the badge/title.
  const count = Math.max(reviews.length, polledReviews) + pendingApprovals;

  // Desktop notifications + browser tab title are owned here, app-wide.
  const { permission, requestPermission, notify } = useDesktopNotifications();
  const prevCount = useRef(count);
  const askedPermission = useRef(false);

  // Reflect pending work in the tab title (so a backgrounded user notices) and
  // ping a desktop notification on each UPWARD transition of the count.
  useEffect(() => {
    const prev = prevCount.current;
    prevCount.current = count;

    if (count === 0) {
      document.title = "Epic Tech AI";
    } else {
      document.title = `(${count}) Epic Tech AI`;
    }

    if (count > prev) {
      const parts: string[] = [];
      if (reviews.length)
        parts.push(`${reviews.length} review${reviews.length === 1 ? "" : "s"} awaiting approval`);
      if (pendingApprovals)
        parts.push(
          `${pendingApprovals} computer-use approval${pendingApprovals === 1 ? "" : "s"}`,
        );
      const body = parts.join(" · ") || "Something needs your attention.";
      notify(`Epic Tech AI — ${count} pending`, body, () => setOpen(true));
    }
  }, [count, reviews.length, pendingApprovals, notify]);

  // Ping a desktop notification when a NEW activity event arrives. The event
  // buffer starts empty on load and /events only streams (never replays
  // history), so a page reload can't re-fire a backlog of old notifications.
  const prevActivityId = useRef<string | null>(null);
  useEffect(() => {
    const latest = activity[0];
    if (!latest || prevActivityId.current === latest.id) return;
    prevActivityId.current = latest.id;
    notify(latest.title, latest.body || "Open the dashboard for details.", () =>
      setOpen(true),
    );
  }, [activity, notify]);

  // Lazily request notification permission the first time the user opens the
  // bell — a real user gesture, so the browser actually shows the prompt.
  const toggleOpen = () => {
    setOpen((o) => !o);
    if (!askedPermission.current && permission === "default") {
      askedPermission.current = true;
      void requestPermission();
    }
  };

  // Close the dropdown on an outside click or Escape.
  useEffect(() => {
    if (!open) return;
    function onClick(ev: MouseEvent) {
      if (ref.current && !ref.current.contains(ev.target as Node)) setOpen(false);
    }
    function onKey(ev: KeyboardEvent) {
      if (ev.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={toggleOpen}
        aria-label={count ? `${count} notifications` : "Notifications"}
        className={`relative grid h-9 w-9 place-items-center rounded-xl border transition-colors ${
          open
            ? "border-accent/40 bg-accent/[0.1] text-accent-soft"
            : "border-white/10 bg-white/[0.02] text-zinc-400 hover:border-white/20 hover:text-zinc-100"
        }`}
      >
        <Bell size={17} strokeWidth={2} />
        {count > 0 && (
          <span className="absolute -right-1 -top-1 grid h-4 min-w-[1rem] place-items-center rounded-full bg-accent px-1 text-[10px] font-bold text-ink-950 shadow-glow-sm">
            {count > 99 ? "99+" : count}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-80 origin-top-right">
          <div className="card-surface overflow-hidden">
            <header className="flex items-center justify-between border-b hairline px-4 py-2.5">
              <span className="flex items-center gap-2 text-[13px] font-semibold text-zinc-200">
                <Bell size={14} className="text-accent-soft/80" />
                Notifications
              </span>
              {count > 0 && (
                <span className="rounded-full border border-accent/30 bg-accent/[0.1] px-2 py-0.5 text-[10px] font-medium text-accent-soft">
                  {count} pending
                </span>
              )}
            </header>

            <div className="max-h-[22rem] overflow-y-auto">
              {count === 0 && activity.length === 0 ? (
                <div className="flex flex-col items-center gap-2 px-4 py-8 text-center">
                  <Inbox size={22} className="text-zinc-600" />
                  <div className="text-sm text-zinc-500">You&apos;re all caught up.</div>
                  <div className="max-w-[15rem] text-[11px] text-zinc-600">
                    Reviews and approvals that need you will show up here.
                  </div>
                </div>
              ) : (
                <ul className="divide-y divide-white/[0.04]">
                  {pendingApprovals > 0 && (
                    <li>
                      <Link
                        href="/computeruse"
                        onClick={() => setOpen(false)}
                        className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-white/[0.04]"
                      >
                        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-amber-500/25 bg-amber-500/[0.08] text-amber-300">
                          <MonitorCog size={15} />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block text-sm font-medium text-zinc-100">
                            {pendingApprovals} computer-use approval
                            {pendingApprovals === 1 ? "" : "s"}
                          </span>
                          <span className="block text-[11px] text-zinc-500">
                            A sensitive action is waiting for your OK.
                          </span>
                        </span>
                        <ArrowRight size={13} className="shrink-0 text-zinc-600" />
                      </Link>
                    </li>
                  )}

                  {reviews.map((e) => {
                    const summary =
                      (e.payload?.summary as string | undefined) ||
                      (e.payload?.risk ? `risk: ${String(e.payload.risk)}` : "") ||
                      "Changes are ready for your review.";
                    return (
                      <li key={e.id}>
                        <Link
                          href="/kanban"
                          onClick={() => setOpen(false)}
                          className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-white/[0.04]"
                        >
                          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-accent/25 bg-accent/[0.08] text-accent-soft">
                            <GitBranch size={15} />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block text-sm font-medium text-zinc-100">
                              Review requested
                            </span>
                            <span className="block truncate text-[11px] text-zinc-500">
                              {summary}
                            </span>
                            <span className="mt-0.5 block font-mono text-[10px] text-zinc-600">
                              {e.session_id ? shortId(e.session_id) : "—"} · {clockTime(e.ts)}
                            </span>
                          </span>
                          <ArrowRight size={13} className="shrink-0 text-zinc-600" />
                        </Link>
                      </li>
                    );
                  })}

                  {/* Informational activity — same row pattern, neutral chrome,
                      never counted in the pending badge. */}
                  {activity.length > 0 && (
                    <li className="bg-white/[0.02] px-4 py-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-zinc-600">
                      Recent activity
                    </li>
                  )}
                  {activity.map((n) => {
                    const Icon = n.icon;
                    return (
                      <li key={n.id}>
                        <Link
                          href={n.href}
                          onClick={() => setOpen(false)}
                          className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-white/[0.04]"
                        >
                          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-white/10 bg-white/[0.03] text-zinc-300">
                            <Icon size={15} />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-sm font-medium text-zinc-100">
                              {n.title}
                            </span>
                            {n.body && (
                              <span className="block truncate text-[11px] text-zinc-500">
                                {n.body}
                              </span>
                            )}
                            <span className="mt-0.5 block font-mono text-[10px] text-zinc-600">
                              {clockTime(n.ts)}
                            </span>
                          </span>
                          <ArrowRight size={13} className="shrink-0 text-zinc-600" />
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>

            {count > 0 && (
              <footer className="border-t hairline px-4 py-2">
                <Link
                  href="/kanban"
                  onClick={() => setOpen(false)}
                  className="flex items-center justify-center gap-1.5 text-[11px] font-medium text-accent-soft transition-colors hover:text-accent"
                >
                  Open the review board <ArrowRight size={12} />
                </Link>
              </footer>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
