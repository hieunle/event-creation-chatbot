"use client";

import { useCallback, useEffect, useState } from "react";

import type { EventRead } from "@/lib/types";

interface Props {
  /** Bumping this value triggers a refetch (e.g. after a successful save). */
  refreshKey?: number;
}

function formatSeatTypes(seatTypes: Record<string, number>): string {
  return Object.entries(seatTypes)
    .map(([k, v]) => `${k}: ${v}`)
    .join(", ");
}

export function EventsPanel({ refreshKey = 0 }: Props) {
  const [events, setEvents] = useState<EventRead[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/events", { cache: "no-store" });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { message?: string };
        throw new Error(body?.message ?? `request failed: ${res.status}`);
      }
      const data = (await res.json()) as { events: EventRead[] };
      setEvents(data.events ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center justify-between border-b border-slate-200 bg-white px-5 py-3">
        <span className="text-xs text-slate-500">
          {loading ? "Loading…" : `${events.length} event${events.length === 1 ? "" : "s"}`}
        </span>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:border-slate-400 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Refresh
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {error && (
          <div className="mb-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            {error}
          </div>
        )}
        {!loading && !error && events.length === 0 && (
          <p className="mt-4 text-center text-sm text-slate-400">
            No events yet. Save one through the chat to see it here.
          </p>
        )}
        <ul className="space-y-2">
          {events.map((ev) => (
            <li
              key={ev.id}
              className="rounded-md border border-slate-200 bg-white px-3 py-2.5 text-xs text-slate-800"
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-sm font-semibold text-slate-900">{ev.name}</span>
                <span className="shrink-0 font-mono text-[10px] text-slate-400">#{ev.id}</span>
              </div>
              <div className="mt-0.5 text-slate-600">
                {ev.date} · {ev.time}
                {ev.is_online ? " · Online" : ""}
              </div>
              <div className="mt-1 text-slate-700">
                <span className="text-slate-500">Venue: </span>
                {ev.venue_name}
                <span className="text-slate-400"> — {ev.venue_address}</span>
              </div>
              <div className="mt-1 text-slate-700">
                <span className="text-slate-500">Category: </span>
                {ev.category}
                <span className="text-slate-400"> · {ev.language}</span>
              </div>
              <div className="mt-1 text-slate-700">
                <span className="text-slate-500">Capacity: </span>
                {ev.capacity}
                <span className="text-slate-400"> · Limit/person: {ev.ticket_limit}</span>
              </div>
              <div className="mt-1 text-slate-700">
                <span className="text-slate-500">Seats: </span>
                {formatSeatTypes(ev.seat_types)}
              </div>
              <div className="mt-1 text-slate-700">
                <span className="text-slate-500">Sales: </span>
                {ev.purchase_start} → {ev.purchase_end}
              </div>
              <div className="mt-1 text-slate-700">
                <span className="text-slate-500">Organizer: </span>
                {ev.organizer_name}
                <span className="text-slate-400"> &lt;{ev.organizer_email}&gt;</span>
              </div>
              {ev.description && (
                <div className="mt-1.5 whitespace-pre-wrap text-slate-600">
                  {ev.description}
                </div>
              )}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
