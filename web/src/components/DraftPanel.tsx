"use client";

import { REQUIRED_COUNT, SECTIONS } from "@/lib/fields";
import type { EventDraft } from "@/lib/types";

function formatValue(key: keyof EventDraft, value: unknown): string {
  if (value === null || value === undefined || value === "") return "";
  if (key === "seat_types" && typeof value === "object") {
    return Object.entries(value as Record<string, number>)
      .map(([k, v]) => `${k}: ${v}`)
      .join(", ");
  }
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

function isFilled(value: unknown): boolean {
  if (value === null || value === undefined || value === "") return false;
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    return Object.keys(value as object).length > 0;
  }
  return true;
}

export function DraftPanel({ draft }: { draft: EventDraft }) {
  let filledRequired = 0;
  for (const section of SECTIONS) {
    for (const f of section.fields) {
      if (f.required && isFilled(draft[f.key])) filledRequired += 1;
    }
  }

  return (
    <aside className="flex h-full min-h-0 w-full flex-col border-l border-slate-200 bg-slate-50">
      <header className="flex shrink-0 items-center justify-between border-b border-slate-200 bg-white px-5 py-4">
        <h2 className="text-sm font-semibold text-slate-900">Draft progress</h2>
        <span className="text-xs text-slate-500">
          {filledRequired} / {REQUIRED_COUNT} required
        </span>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {SECTIONS.map((section) => (
          <div key={section.title} className="mb-4">
            <h3 className="mb-2 ml-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              {section.title}
            </h3>
            <ul className="space-y-0.5">
              {section.fields.map((f) => {
                const raw = draft[f.key];
                const filled = isFilled(raw);
                return (
                  <li
                    key={f.key}
                    className={
                      filled
                        ? "flex items-start gap-2 rounded-md border border-emerald-200 bg-white px-3 py-2"
                        : "flex items-start gap-2 px-3 py-2 text-slate-400"
                    }
                  >
                    <span
                      className={`mt-0.5 text-base leading-none ${
                        filled ? "text-emerald-500" : "text-slate-300"
                      }`}
                    >
                      {filled ? "●" : "○"}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-medium text-slate-700">
                        {f.label}
                        {!f.required && (
                          <span className="ml-1 text-[10px] font-normal text-slate-400">
                            (optional)
                          </span>
                        )}
                      </div>
                      {filled && (
                        <div className="mt-0.5 break-words text-[13px] text-slate-800">
                          {formatValue(f.key, raw)}
                        </div>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
    </aside>
  );
}
