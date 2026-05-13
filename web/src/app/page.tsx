"use client";

import { useCallback, useEffect, useState } from "react";

import { Chat } from "@/components/Chat";
import { DraftPanel } from "@/components/DraftPanel";
import { EventsPanel } from "@/components/EventsPanel";
import { HistoryDrawer } from "@/components/HistoryDrawer";
import { getSessionId, setStoredSessionId } from "@/lib/session";
import type { EventDraft } from "@/lib/types";

type Tab = "draft" | "events";

export default function HomePage() {
  const [sessionId, setSessionId] = useState<string>("");
  const [draft, setDraft] = useState<EventDraft>({});
  const [tab, setTab] = useState<Tab>("draft");
  const [eventsRefreshKey, setEventsRefreshKey] = useState<number>(0);
  const [historyOpen, setHistoryOpen] = useState<boolean>(false);

  useEffect(() => {
    setSessionId(getSessionId());
  }, []);

  const switchSession = useCallback((id: string) => {
    setStoredSessionId(id);
    setSessionId(id);
  }, []);

  const handleNewChat = useCallback(() => {
    switchSession(crypto.randomUUID());
  }, [switchSession]);

  const handlePickFromHistory = useCallback(
    (id: string) => {
      switchSession(id);
      setHistoryOpen(false);
    },
    [switchSession],
  );

  const handleEventSaved = useCallback(() => {
    setEventsRefreshKey((k) => k + 1);
    setTab("events");
  }, []);

  return (
    <main className="grid h-dvh w-full grid-cols-1 overflow-hidden md:grid-cols-[1fr_360px]">
      <div className="flex h-dvh min-h-0 flex-col overflow-hidden">
        <Chat
          sessionId={sessionId}
          onDraftUpdate={setDraft}
          onEventSaved={handleEventSaved}
          onNewChat={handleNewChat}
          onOpenHistory={() => setHistoryOpen(true)}
        />
      </div>
      <aside className="flex h-dvh min-h-0 flex-col overflow-hidden border-l border-slate-200 bg-slate-50">
        <div className="flex shrink-0 border-b border-slate-200 bg-white">
          <TabButton active={tab === "draft"} onClick={() => setTab("draft")}>
            Draft
          </TabButton>
          <TabButton active={tab === "events"} onClick={() => setTab("events")}>
            Events
          </TabButton>
        </div>
        <div className="min-h-0 flex-1 overflow-hidden">
          {tab === "draft" ? (
            <DraftPanel draft={draft} />
          ) : (
            <EventsPanel refreshKey={eventsRefreshKey} />
          )}
        </div>
      </aside>

      <HistoryDrawer
        open={historyOpen}
        currentSessionId={sessionId}
        onClose={() => setHistoryOpen(false)}
        onPick={handlePickFromHistory}
      />
    </main>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        active
          ? "flex-1 border-b-2 border-blue-600 px-4 py-3 text-sm font-semibold text-blue-700"
          : "flex-1 border-b-2 border-transparent px-4 py-3 text-sm font-medium text-slate-600 hover:text-slate-900"
      }
    >
      {children}
    </button>
  );
}
