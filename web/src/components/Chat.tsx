"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { TypingIndicator } from "@/components/TypingIndicator";
import type { ChatResponse, ChatTurnResult, EventDraft, Scenario } from "@/lib/types";

interface UIMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  scenario?: Scenario;
}

const SCENARIO_STYLES: Record<Scenario, string> = {
  missing_field: "border-slate-200 bg-slate-100 text-slate-900",
  invalid_input: "border-red-300 bg-red-50 text-red-900",
  confirmation: "border-indigo-300 bg-indigo-50 text-indigo-900",
  success_save: "border-emerald-300 bg-emerald-50 text-emerald-900",
  error_db: "border-amber-300 bg-amber-50 text-amber-900",
  update_previous_field: "border-sky-300 bg-sky-50 text-sky-900",
  lookup: "border-violet-300 bg-violet-50 text-violet-900",
  small_talk: "border-slate-200 bg-white text-slate-700",
};

/**
 * The backend stores assistant turns as the JSON-stringified ChatResponse
 * (because the agent emits its final answer via response_format=ChatResponse).
 * On hydrate we parse it back so the UI shows the message + scenario badge,
 * not the raw JSON.
 */
function tryParseChatResponse(content: string): ChatResponse | null {
  const trimmed = content.trim();
  if (!trimmed.startsWith("{")) return null;
  try {
    const obj = JSON.parse(trimmed) as Partial<ChatResponse>;
    if (typeof obj?.message === "string" && typeof obj?.scenario === "string") {
      return {
        role: "assistant",
        scenario: obj.scenario as Scenario,
        message: obj.message,
      };
    }
  } catch {
    /* fall through */
  }
  return null;
}

interface Props {
  sessionId: string;
  onDraftUpdate: (draft: EventDraft) => void;
  onEventSaved?: () => void;
  onNewChat: () => void;
  onOpenHistory: () => void;
}

export function Chat({
  sessionId,
  onDraftUpdate,
  onEventSaved,
  onNewChat,
  onOpenHistory,
}: Props) {
  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [input, setInput] = useState<string>("");
  const [sending, setSending] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Re-hydrate whenever the session id changes (new chat, switched via history,
  // first mount). Clears local UI state so a stale view never leaks across sessions.
  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    setMessages([]);
    setError(null);
    onDraftUpdate({});
    (async () => {
      try {
        const res = await fetch(`/api/state/${encodeURIComponent(sessionId)}`);
        if (!res.ok || cancelled) return;
        const data = (await res.json()) as {
          draft: EventDraft;
          messages: { role: string; content: string }[];
        };
        if (cancelled) return;
        onDraftUpdate(data.draft ?? {});
        const restored: UIMessage[] = (data.messages ?? [])
          .filter(
            (m) =>
              (m.role === "user" || m.role === "assistant") &&
              typeof m.content === "string" &&
              m.content.trim() !== "",
          )
          .map((m, i) => {
            const role = m.role as "user" | "assistant";
            if (role === "assistant") {
              const parsed = tryParseChatResponse(m.content);
              if (parsed) {
                return {
                  id: `restore-${i}`,
                  role,
                  content: parsed.message,
                  scenario: parsed.scenario,
                };
              }
            }
            return { id: `restore-${i}`, role, content: m.content };
          });
        if (restored.length > 0) setMessages(restored);
      } catch {
        /* non-fatal */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, onDraftUpdate]);

  // Auto-scroll: anchor the chat to the bottom whenever new content appears.
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, sending]);

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || !sessionId || sending) return;
      setSending(true);
      setError(null);
      setInput("");
      const userMsg: UIMessage = {
        id: `u-${Date.now()}`,
        role: "user",
        content: trimmed,
      };
      setMessages((prev) => [...prev, userMsg]);

      try {
        const res = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sessionId, message: trimmed }),
        });
        if (!res.ok) {
          const errBody = (await res.json().catch(() => ({}))) as { message?: string };
          throw new Error(errBody?.message ?? `request failed: ${res.status}`);
        }
        const data = (await res.json()) as ChatTurnResult;
        const cr: ChatResponse = data.response;
        setMessages((prev) => [
          ...prev,
          {
            id: `a-${Date.now()}`,
            role: "assistant",
            content: cr.message,
            scenario: cr.scenario,
          },
        ]);
        onDraftUpdate(data.draft ?? {});
        if (cr.scenario === "success_save") {
          onEventSaved?.();
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setError(msg);
        setMessages((prev) => [
          ...prev,
          {
            id: `err-${Date.now()}`,
            role: "assistant",
            content: `⚠ ${msg}`,
            scenario: "error_db",
          },
        ]);
      } finally {
        setSending(false);
        inputRef.current?.focus();
      }
    },
    [sessionId, sending, onDraftUpdate, onEventSaved],
  );

  return (
    <section className="flex h-full min-h-0 w-full flex-col bg-white">
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-200 px-5 py-3">
        <h1 className="text-sm font-semibold">Event Creation Chatbot</h1>
        <div className="flex items-center gap-3">
          {sessionId && (
            <span
              className="font-mono text-[10px] text-slate-400"
              title={sessionId}
            >
              {sessionId.slice(0, 8)}
            </span>
          )}
          <button
            type="button"
            onClick={onOpenHistory}
            disabled={sending}
            className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:border-slate-400 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            title="Browse past chats"
          >
            History
          </button>
          <button
            type="button"
            onClick={onNewChat}
            disabled={sending}
            className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:border-slate-400 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            title="Start a new chat (clears the current draft)"
          >
            + New chat
          </button>
        </div>
      </header>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-5 py-5">
        {messages.length === 0 && !sending && (
          <p className="mt-4 text-center text-sm text-slate-400">
            Start by describing your event — name, date, venue, anything.
          </p>
        )}
        {messages.map((m) => {
          if (m.role === "user") {
            return (
              <div key={m.id} className="flex justify-end">
                <div className="max-w-[75%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-blue-600 px-4 py-2.5 text-sm leading-relaxed text-white">
                  {m.content}
                </div>
              </div>
            );
          }
          const cls = m.scenario ? SCENARIO_STYLES[m.scenario] : SCENARIO_STYLES.missing_field;
          return (
            <div key={m.id} className="flex justify-start">
              <div
                className={`max-w-[75%] whitespace-pre-wrap rounded-2xl rounded-bl-md border px-4 py-2.5 text-sm leading-relaxed ${cls}`}
              >
                {m.scenario && (
                  <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider opacity-70">
                    {m.scenario.replace(/_/g, " ")}
                  </div>
                )}
                {m.content}
              </div>
            </div>
          );
        })}
        {sending && <TypingIndicator />}
        <div ref={endRef} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send(input);
        }}
        className="flex shrink-0 gap-2 border-t border-slate-200 bg-white px-4 py-3"
      >
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={sending ? "Waiting for assistant…" : "Describe your event or answer the assistant…"}
          disabled={sending || !sessionId}
          className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500 disabled:bg-slate-50"
        />
        <button
          type="submit"
          disabled={sending || !input.trim() || !sessionId}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {sending ? "…" : "Send"}
        </button>
      </form>

      {error && (
        <div className="shrink-0 border-t border-red-200 bg-red-50 px-4 py-2 text-xs text-red-700">
          {error}
        </div>
      )}
    </section>
  );
}
