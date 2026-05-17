// Shared types mirroring the Python backend's response envelope.

export type Scenario =
  | "missing_field"
  | "invalid_input"
  | "confirmation"
  | "success_save"
  | "error_db"
  | "update_previous_field"
  | "lookup"
  | "small_talk";

export interface ChatResponse {
  role: "assistant";
  scenario: Scenario;
  message: string;
}

// EventDraft mirrors app/models/event.py. Every field optional during conversation.
export interface EventDraft {
  name?: string | null;
  date?: string | null;
  time?: string | null;
  description?: string | null;
  seat_types?: Record<string, number> | null;
  purchase_start?: string | null;
  purchase_end?: string | null;
  ticket_limit?: number | null;
  venue_name?: string | null;
  venue_address?: string | null;
  capacity?: number | null;
  organizer_name?: string | null;
  organizer_email?: string | null;
  category?: string | null;
  language?: string | null;
  is_recurring?: boolean | null;
  recurrence_frequency?: string | null;
  is_online?: boolean | null;
}

export interface ChatTurnResult {
  response: ChatResponse;
  draft: EventDraft;
}

export interface SessionSummary {
  session_id: string;
  updated_at: string | null;
  title: string;
  message_count: number;
  has_draft: boolean;
}

// EventRead mirrors app/models/event.py EventRead — a persisted event row.
export interface EventRead {
  id: number;
  name: string;
  date: string;
  time: string;
  description?: string | null;
  seat_types: Record<string, number>;
  purchase_start: string;
  purchase_end: string;
  ticket_limit: number;
  venue_name: string;
  venue_address: string;
  capacity: number;
  organizer_name: string;
  organizer_email: string;
  category: string;
  language: string;
  is_recurring: boolean;
  recurrence_frequency?: string | null;
  is_online: boolean;
  created_at: string;
  updated_at: string;
}
