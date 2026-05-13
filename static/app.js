// Event Creation Chatbot — front-end
// Two panels: chat (left) + draft progress (right), both driven by a
// single WebSocket connection to /api/chat/{session_id}.

const SECTIONS = [
  {
    title: "Basic info",
    fields: [
      { key: "name",        label: "Event name",  required: true },
      { key: "date",        label: "Date",        required: true },
      { key: "time",        label: "Time",        required: true },
      { key: "description", label: "Description", required: false },
    ],
  },
  {
    title: "Tickets",
    fields: [
      { key: "seat_types",     label: "Seat types & prices", required: true },
      { key: "ticket_limit",   label: "Ticket limit / person", required: true },
      { key: "purchase_start", label: "Purchase start", required: true },
      { key: "purchase_end",   label: "Purchase end",   required: true },
    ],
  },
  {
    title: "Venue",
    fields: [
      { key: "venue_name",    label: "Venue name",    required: true },
      { key: "venue_address", label: "Venue address", required: true },
      { key: "capacity",      label: "Capacity",      required: true },
    ],
  },
  {
    title: "Organizer",
    fields: [
      { key: "organizer_name",  label: "Organizer name",  required: true },
      { key: "organizer_email", label: "Organizer email", required: true },
    ],
  },
  {
    title: "Other",
    fields: [
      { key: "category",             label: "Category",     required: true },
      { key: "language",             label: "Language",     required: true },
      { key: "is_recurring",         label: "Recurring?",   required: false },
      { key: "recurrence_frequency", label: "Frequency",    required: false },
      { key: "is_online",            label: "Online?",      required: false },
    ],
  },
];

const REQUIRED_COUNT = SECTIONS
  .flatMap((s) => s.fields)
  .filter((f) => f.required).length;

// ---------- session id ----------
function getSessionId() {
  let id = localStorage.getItem("session_id");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("session_id", id);
  }
  return id;
}

// ---------- DOM helpers ----------
const $messages = document.getElementById("messages");
const $composer = document.getElementById("composer");
const $input = document.getElementById("user-input");
const $sendBtn = $composer.querySelector("button");
const $conn = document.getElementById("conn-status");
const $draftFields = document.getElementById("draft-fields");
const $draftCount = document.getElementById("draft-count");

function appendMessage(role, text, scenario) {
  const div = document.createElement("div");
  div.className = `bubble ${role}` + (scenario ? ` ${scenario}` : "");
  if (role === "assistant" && scenario) {
    const tag = document.createElement("span");
    tag.className = "scenario-tag";
    tag.textContent = scenario.replace(/_/g, " ");
    div.appendChild(tag);
    div.appendChild(document.createElement("br"));
  }
  div.appendChild(document.createTextNode(text));
  $messages.appendChild(div);
  $messages.scrollTop = $messages.scrollHeight;
}

function formatValue(key, value) {
  if (value === null || value === undefined || value === "") return "";
  if (key === "seat_types" && typeof value === "object") {
    return Object.entries(value)
      .map(([k, v]) => `${k}: ${v}`)
      .join(", ");
  }
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

function renderDraft(draft) {
  $draftFields.innerHTML = "";
  let filledRequired = 0;
  for (const section of SECTIONS) {
    const sec = document.createElement("div");
    sec.className = "draft-section";
    const h = document.createElement("h3");
    h.textContent = section.title;
    sec.appendChild(h);

    for (const f of section.fields) {
      const raw = draft ? draft[f.key] : undefined;
      const filled =
        raw !== null && raw !== undefined && raw !== "" &&
        !(typeof raw === "object" && Object.keys(raw).length === 0);
      if (filled && f.required) filledRequired += 1;

      const row = document.createElement("div");
      row.className = `field ${filled ? "filled" : "empty"}`;

      const icon = document.createElement("span");
      icon.className = `field-icon ${filled ? "filled" : "empty"}`;
      icon.textContent = filled ? "●" : "○";
      row.appendChild(icon);

      const body = document.createElement("div");
      body.className = "field-body";
      const label = document.createElement("div");
      label.className = "field-label";
      label.textContent = f.label + (f.required ? "" : " (optional)");
      body.appendChild(label);
      if (filled) {
        const v = document.createElement("div");
        v.className = "field-value";
        v.textContent = formatValue(f.key, raw);
        body.appendChild(v);
      }
      row.appendChild(body);
      sec.appendChild(row);
    }
    $draftFields.appendChild(sec);
  }
  $draftCount.textContent = `${filledRequired} / ${REQUIRED_COUNT} required`;
}

// ---------- WebSocket ----------
const sessionId = getSessionId();
let ws = null;
let pendingSend = false;

function setConnStatus(label, cls) {
  $conn.textContent = label;
  $conn.className = "conn-status " + cls;
}

function connect() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${proto}//${location.host}/api/chat/${sessionId}`);

  ws.addEventListener("open", () => {
    setConnStatus("online", "online");
    $sendBtn.disabled = false;
  });
  ws.addEventListener("close", () => {
    setConnStatus("offline — reconnecting", "offline");
    $sendBtn.disabled = true;
    setTimeout(connect, 1500);
  });
  ws.addEventListener("error", () => {
    setConnStatus("offline", "offline");
  });
  ws.addEventListener("message", (e) => {
    let msg;
    try { msg = JSON.parse(e.data); } catch { return; }
    if (msg.type === "snapshot") {
      renderDraft(msg.draft);
      for (const m of msg.messages || []) {
        if (m.role === "user" || m.role === "assistant") {
          appendMessage(m.role, m.content || "");
        }
      }
    } else if (msg.type === "turn") {
      appendMessage("assistant", msg.response.message, msg.response.scenario);
      renderDraft(msg.draft);
    } else if (msg.type === "error") {
      appendMessage("assistant", "⚠ " + msg.message, "error_db");
    }
  });
}

$composer.addEventListener("submit", (e) => {
  e.preventDefault();
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  const text = $input.value.trim();
  if (!text) return;
  appendMessage("user", text);
  ws.send(JSON.stringify({ message: text }));
  $input.value = "";
});

// initial empty render
renderDraft({});
connect();
