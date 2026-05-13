"use client";

import { useCallback, useEffect, useState } from "react";

import type { SessionSummary } from "@/lib/types";

interface Props {
  open: boolean;
  currentSessionId: string;
  onClose: () => void;
  onPick: (sessionId: string) => void;
}

function formatTimestamp(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

export function HistoryDrawer({ open, currentSessionId, onClose, onPick }: Props) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/sessions", { cache: "no-store" });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { message?: string };
        throw new Error(body?.message ?? `request failed: ${res.status}`);
      }
      const data = (await res.json()) as { sessions: SessionSummary[] };
      setSessions(data.sessions ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  // Close on Escape.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex">
      <div
        className="absolute inset-0 bg-slate-900/30"
        onClick={onClose}
        aria-hidden
      />
      <aside className="relative ml-auto flex h-full w-full max-w-md flex-col border-l border-slate-200 bg-white shadow-xl">
        <header className="flex shrink-0 items-center justify-between border-b border-slate-200 px-5 py-3">
          <h2 className="text-sm font-semibold text-slate-900">Chat history</h2>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void load()}
              disabled={loading}
              className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:border-slate-400 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Refresh
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:border-slate-400 hover:bg-slate-50"
              aria-label="Close history"
            >
              Close
            </button>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {error && (
            <div className="mb-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              {error}
            </div>
          )}
          {loading && sessions.length === 0 && (
            <p className="mt-4 text-center text-sm text-slate-400">Loading…</p>
          )}
          {!loading && !error && sessions.length === 0 && (
            <p className="mt-4 text-center text-sm text-slate-400">
              No past chats yet.
            </p>
          )}
          <ul className="space-y-2">
            {sessions.map((s) => {
              const isCurrent = s.session_id === currentSessionId;
              return (
                <li key={s.session_id}>
                  <button
                    type="button"
                    onClick={() => onPick(s.session_id)}
                    className={
                      isCurrent
                        ? "w-full rounded-md border border-blue-300 bg-blue-50 px-3 py-2.5 text-left text-xs"
                        : "w-full rounded-md border border-slate-200 bg-white px-3 py-2.5 text-left text-xs hover:border-slate-400 hover:bg-slate-50"
                    }
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-sm font-medium text-slate-900">
                        {s.title}
                      </span>
                      {isCurrent && (
                        <span className="shrink-0 rounded bg-blue-600 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
                          Current
                        </span>
                      )}
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-slate-500">
                      <span className="font-mono text-[10px]" title={s.session_id}>
                        {s.session_id.slice(0, 8)}
                      </span>
                      <span>·</span>
                      <span>{formatTimestamp(s.updated_at)}</span>
                      <span>·</span>
                      <span>{s.message_count} msg{s.message_count === 1 ? "" : "s"}</span>
                      {s.has_draft && (
                        <>
                          <span>·</span>
                          <span className="text-amber-600">draft</span>
                        </>
                      )}
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      </aside>
    </div>
  );
}
