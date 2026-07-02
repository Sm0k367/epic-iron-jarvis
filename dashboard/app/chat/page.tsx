"use client";

// The friendly front door under "Work": the user types what they want and a real
// Iron Jarvis agent replies. It either answers conversationally or uses whatever
// tools it needs — all server-side, so this page just relays messages to a session
// and shows the reply. The first message opens a session; every later message in the
// same chat continues it.

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Bot, Loader2, MessageSquare, Plus, Send, Sparkles, User } from "lucide-react";
import { get, post, ApiError } from "@/lib/api";
import type { ModelOption, SessionView } from "@/lib/types";
import { Card, Empty, ErrorNote, LoaderInline, OfflineHint } from "@/components/ui";
import { PageHeader } from "@/components/PageHeader";
import { PageShell, Reveal } from "@/components/motion";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

// Prompts the user can click to prefill the composer on an empty chat.
const EXAMPLES = [
  "What can you do?",
  "Summarize the files in a folder",
  "Draft a follow-up email to a client",
];

// The model <select> encodes the choice as `${provider}::${model}` (empty => let the
// server pick its default). Split it back out only when it carries both halves.
function splitChoice(choice: string): { provider?: string; model?: string } {
  const i = choice.indexOf("::");
  if (i === -1) return {};
  const provider = choice.slice(0, i);
  const model = choice.slice(i + 2);
  return provider && model ? { provider, model } : {};
}

function Bubble({ role, children }: { role: ChatMessage["role"]; children: ReactNode }) {
  const isUser = role === "user";
  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      <span
        className={`grid h-8 w-8 shrink-0 place-items-center rounded-xl border ${
          isUser
            ? "border-accent/30 bg-accent/10 text-accent-soft"
            : "border-white/[0.08] bg-white/[0.03] text-zinc-300"
        }`}
      >
        {isUser ? <User size={15} /> : <Bot size={15} />}
      </span>
      <div
        className={`max-w-[80%] whitespace-pre-wrap rounded-2xl border px-4 py-2.5 text-sm leading-relaxed ${
          isUser
            ? "border-accent/25 bg-accent/[0.1] text-zinc-100"
            : "border-white/[0.06] bg-white/[0.03] text-zinc-200"
        }`}
      >
        {children}
      </div>
    </div>
  );
}

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [choice, setChoice] = useState(""); // "" => server default model
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Load the model catalog for the header picker (best-effort — stays on "default").
  useEffect(() => {
    let cancelled = false;
    get<{ models: ModelOption[] }>("/models")
      .then((d) => {
        if (!cancelled) setModels(d.models);
      })
      .catch(() => {
        /* picker just stays on the server default */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Keep the newest message (or the thinking bubble) in view.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    setError(null);
    setOffline(false);
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: message }]);
    setBusy(true);
    try {
      let session: SessionView;
      if (sessionId) {
        // Continue the same chat — the returned session's summary is the new reply.
        session = await post<SessionView>(`/sessions/${sessionId}/continue`, {
          message,
          wait: true,
        });
      } else {
        // First message opens a session; remember its id for follow-ups.
        const { provider, model } = splitChoice(choice);
        session = await post<SessionView>("/sessions", {
          task: message,
          agent_type: "builder",
          wait: true,
          ...(provider ? { provider } : {}),
          ...(model ? { model } : {}),
        });
        setSessionId(session.id);
      }
      const reply = session.summary || "(no response)";
      setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
    } catch (e) {
      // Keep the typed thread intact — only surface the failure.
      if (e instanceof ApiError && e.status === 0) setOffline(true);
      else setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function newChat() {
    setMessages([]);
    setSessionId(null);
    setInput("");
    setError(null);
    setOffline(false);
  }

  function prefill(text: string) {
    setInput(text);
    inputRef.current?.focus();
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends; Shift+Enter inserts a newline.
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send(input);
    }
  }

  const started = messages.length > 0 || sessionId !== null;

  return (
    <PageShell>
      <Reveal>
        <PageHeader
          title="Chat"
          subtitle="Talk to your Iron Jarvis agent. Ask anything — it answers conversationally, and reads files, searches, and uses tools on its own whenever that helps."
          actions={
            <div className="flex items-center gap-2">
              <select
                aria-label="Model"
                value={choice}
                onChange={(e) => setChoice(e.target.value)}
                disabled={busy || started}
                title={started ? "Start a new chat to switch models" : "Model for this chat"}
                className="field w-auto py-1.5 text-[13px]"
              >
                <option value="">default model</option>
                {models.map((m) => {
                  const v = `${m.provider}::${m.model}`;
                  return (
                    <option key={v} value={v}>
                      {m.provider} · {m.model}
                    </option>
                  );
                })}
              </select>
              <button
                onClick={newChat}
                disabled={busy || !started}
                className="btn-ghost py-1.5 text-[13px]"
              >
                <Plus size={14} /> New chat
              </button>
            </div>
          }
        />
      </Reveal>

      <Reveal>
        <p className="flex items-center gap-2 text-xs text-zinc-500">
          <Sparkles size={13} className="shrink-0 text-accent-soft/70" />
          Replies come from a real agent that can read files, search, and use tools — they may
          take a few seconds.
        </p>
      </Reveal>

      {offline && (
        <Reveal>
          <OfflineHint detail="Chat needs it running to reach your agent." />
        </Reveal>
      )}

      <Reveal>
        <Card pad={false} className="overflow-hidden">
          {/* Message thread */}
          <div className="flex max-h-[60vh] min-h-[24rem] flex-col gap-4 overflow-y-auto p-4 sm:p-5">
            {messages.length === 0 && !busy ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-4">
                <Empty icon={<MessageSquare size={28} />}>
                  Start a conversation. Ask a question or describe what you need — your agent
                  replies and reaches for tools on its own when they help.
                </Empty>
                <div className="flex flex-wrap justify-center gap-2">
                  {EXAMPLES.map((ex) => (
                    <button
                      key={ex}
                      onClick={() => prefill(ex)}
                      className="rounded-full border border-white/[0.08] bg-white/[0.02] px-3 py-1.5 text-xs text-zinc-400 transition-colors hover:border-accent/40 hover:text-accent-soft"
                    >
                      {ex}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <>
                {messages.map((m, i) => (
                  <Bubble key={i} role={m.role}>
                    {m.content}
                  </Bubble>
                ))}
                {busy && (
                  <Bubble role="assistant">
                    <span className="inline-flex items-center gap-2 text-zinc-400">
                      <Loader2 size={14} className="animate-spin" /> Thinking…
                    </span>
                  </Bubble>
                )}
              </>
            )}
            <div ref={bottomRef} />
          </div>

          {error && (
            <div className="border-t hairline p-3">
              <ErrorNote>{error}</ErrorNote>
            </div>
          )}

          {/* Composer */}
          <div className="flex items-end gap-2 border-t hairline p-3">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              disabled={busy}
              rows={1}
              aria-label="Message"
              placeholder="Message Iron Jarvis…  (Enter to send · Shift+Enter for a new line)"
              className="field max-h-40 min-h-[2.75rem] flex-1 resize-none disabled:opacity-60"
            />
            <button
              onClick={() => send(input)}
              disabled={busy || !input.trim()}
              className="btn-accent h-[2.75rem] px-4 py-0 text-[13px]"
            >
              {busy ? (
                <LoaderInline />
              ) : (
                <>
                  <Send size={16} /> Send
                </>
              )}
            </button>
          </div>
        </Card>
      </Reveal>
    </PageShell>
  );
}
