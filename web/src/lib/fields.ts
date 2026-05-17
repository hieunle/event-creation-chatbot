// Field layout for the draft progress panel.

export interface FieldSpec {
  key: keyof import("./types").EventDraft;
  label: string;
  required: boolean;
}

export interface Section {
  title: string;
  fields: FieldSpec[];
}

export const SECTIONS: Section[] = [
  {
    title: "Basic info",
    fields: [
      { key: "name", label: "Event name", required: true },
      { key: "date", label: "Date", required: true },
      { key: "time", label: "Time", required: true },
      { key: "description", label: "Description", required: false },
    ],
  },
  {
    title: "Tickets",
    fields: [
      { key: "seat_types", label: "Seat types & prices", required: true },
      { key: "ticket_limit", label: "Ticket limit / person", required: true },
      { key: "purchase_start", label: "Purchase start", required: true },
      { key: "purchase_end", label: "Purchase end", required: true },
    ],
  },
  {
    title: "Venue",
    fields: [
      { key: "venue_name", label: "Venue name", required: true },
      { key: "venue_address", label: "Venue address", required: true },
      { key: "capacity", label: "Capacity", required: true },
    ],
  },
  {
    title: "Organizer",
    fields: [
      { key: "organizer_name", label: "Organizer name", required: true },
      { key: "organizer_email", label: "Organizer email", required: true },
    ],
  },
  {
    title: "Other",
    fields: [
      { key: "category", label: "Category", required: true },
      { key: "language", label: "Language", required: true },
      { key: "is_recurring", label: "Recurring?", required: false },
      { key: "recurrence_frequency", label: "Frequency", required: false },
      { key: "is_online", label: "Online?", required: false },
    ],
  },
];

export const REQUIRED_COUNT = SECTIONS
  .flatMap((s) => s.fields)
  .filter((f) => f.required).length;
