# Event Creation Chatbot

An AI-assisted chatbot that guides users through event creation in natural
language, persists validated events to PostgreSQL, and indexes them in
ChromaDB for semantic recall.

- **Backend**: FastAPI + LangGraph + OpenAI + PostgreSQL + ChromaDB (in `app/`)
- **Frontend**: Next.js 16 + Tailwind v4 + Vercel AI SDK (in `web/`)

The Python backend owns the agent and all business logic. The Next.js app
is a thin UI that proxies through `/api/chat` and `/api/state/{id}` to the
Python REST endpoints.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                  Browser (Next.js, Tailwind)                      │
│   ┌────────────────────────┐    ┌────────────────────────────┐    │
│   │       Chat panel        │    │   Draft progress panel     │    │
│   └────────────┬───────────┘    └────────────┬───────────────┘    │
└────────────────┼─────────────────────────────┼────────────────────┘
                 │                             │
                 ▼                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Next.js server (web/)                          │
│  /api/chat              → proxies to Python POST /api/chat/{id}   │
│  /api/state/{id}        → proxies to Python GET  /api/session/…   │
└────────────────┬─────────────────────────────────────────────────┘
                 │  HTTP
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                        FastAPI app                                │
│  Routes: POST /api/chat/{id} · WS /api/chat/{id}                  │
│          POST /api/register-event · GET /api/session/{id}/state   │
│          GET  /api/events       · GET /api/sessions               │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│            ConversationEngine (LangGraph create_react_agent)      │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ Tools:                                                    │    │
│  │   • update_event_draft  (validate, merge, dup-check)      │    │
│  │   • save_event          (commit + index)                  │    │
│  │   • query_events        (structured SQL)                  │    │
│  │   • search_events       (semantic Chroma)                 │    │
│  └──────────────────────────────────────────────────────────┘    │
│  response_format = ChatResponse{scenario, message}                │
│  state           = SessionState{messages, draft: EventDraft}      │
│  checkpointer    = AsyncPostgresSaver (thread_id=session_id)      │
└────┬───────────────────────────┬─────────────────────────────────┘
     │                           │
     ▼                           ▼
┌─────────────────┐      ┌─────────────────────┐
│   PostgreSQL    │      │     ChromaDB        │
│  events table   │      │ (PersistentClient)  │
│  + checkpoints  │      │  events collection  │
└─────────────────┘      └─────────────────────┘
```

The four agent tools wrap four deep modules:

| Tool                  | Deep module        | Purpose                              |
|-----------------------|--------------------|--------------------------------------|
| `update_event_draft`  | `EventDraft` model | per-field validate + merge into state |
| `save_event`          | `EventRepository`  | commit `EventCreate` to PG           |
| `query_events`        | `EventRepository`  | structured filters (latest, date, category) |
| `search_events`       | `EventMemory`      | semantic recall via Chroma           |

The LLM owns scenario classification (constrained by `Literal` enum +
rubric in the system prompt). Confirmation before save is enforced via
prompt instructions.

## Setup

The full stack — Postgres, Python backend, Next.js frontend — runs from one
command via Docker Compose.

```bash
cp .env.example .env   # fill in OPENAI_API_KEY
docker compose up --build
```

That brings up four containers:

- `postgres` — Postgres 16, schema auto-applied from `migrations/`, port `5432`
- `app` — FastAPI backend on `:8000`
- `web` — Next.js frontend on `:3000`

Open <http://localhost:3000>.

### Local dev (without Docker)

If you want hot-reload on either side, run that side outside the container.

**Python backend** (requires [uv](https://docs.astral.sh/uv/)):

```bash
docker compose up postgres -d        # or createdb events && psql events < migrations/001_create_events.sql
uv sync
cp .env.example .env                 # fill OPENAI_API_KEY
uv run uvicorn app.main:app --reload # → http://localhost:8000
```

Python 3.11 or 3.12 (constrained in `pyproject.toml`).

**Next.js frontend** (Node 20+, pnpm):

```bash
cd web
pnpm install
cp .env.local.example .env.local     # PYTHON_BACKEND_URL defaults to localhost:8000
pnpm dev                             # → http://localhost:3000
```

## Running tests

```bash
uv sync
uv run pytest tests       # unit tests — fast, no API key needed
uv run pytest evals       # LLM behavioral evals — slow, needs OPENAI_API_KEY
```

`uv run pytest` with no path picks up both suites; specify `tests/` while
iterating so you don't burn API credits on every run.

Default unit-test database is in-memory sqlite (via aiosqlite); the schema
is created from `Base.metadata`. To run unit tests against a real Postgres
set `CONFTEST_DATABASE_URL`:

```bash
CONFTEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/events_test pytest tests
```

Chroma tests use a temp directory with a deterministic fake embedding
function — no API key required.

The `evals/` suite (parametrised agent-routing cases under
`evals/test_agent_routing.py`) calls the real LLM and is automatically
skipped when `OPENAI_API_KEY` is unset.

## Response envelope

Every chat turn returns a structured response:

```json
{
  "role": "assistant",
  "scenario": "missing_field",
  "message": "Got it. What's the venue name?"
}
```

`scenario` is one of:

- `missing_field` — asking for a required field
- `invalid_input` — last input was malformed or duplicated
- `confirmation` — all fields filled; awaiting yes/no
- `success_save` — event committed
- `error_db` — save failed
- `update_previous_field` — user revised an earlier answer
- `lookup` — answering a question about a past event (via `query_events` / `search_events`)
- `small_talk` — greeting / thanks / off-topic, no field being collected

## Sample conversations

See `docs/sample-conversations.md` for full transcripts:

- Successful end-to-end event creation
- Error-handling case (invalid input + duplicate detection)

## Project layout

```
app/                              # Python backend
├── api/                          # FastAPI routes
├── agent/                        # LangGraph engine, tools, prompts, state
├── models/                       # Pydantic + SQLAlchemy
└── services/                     # db engine, EventRepository, EventMemory

web/                              # Next.js frontend
├── src/
│   ├── app/
│   │   ├── api/chat/route.ts     # proxies to Python POST /api/chat/{id}
│   │   ├── api/state/[…]         # proxies to Python GET  /api/session/{id}
│   │   └── page.tsx              # two-panel layout
│   ├── components/Chat.tsx
│   ├── components/DraftPanel.tsx
│   └── lib/                      # types, fields, session helpers
└── package.json

static/                           # Legacy plain-JS UI (kept as fallback)
migrations/                       # SQL migrations
tests/                            # pytest unit suite (no API key)
evals/                            # pytest LLM-behavior evals (needs OPENAI_API_KEY)
```

## Decisions worth knowing

- **`seat_types` replace semantics.** Sending a new `seat_types` dict
  overwrites the existing one. Add/remove of individual seat types is
  not a separate operation in this build.
- **Confirmation gate is prompt-only.** The system prompt instructs the
  LLM to only call `save_event` after explicit user confirmation. There
  is no hard Python gate. Trade-off: simpler code, accepts some LLM
  reliability risk on the save action.
- **Chroma is best-effort.** Index failures on `save_event` are logged
  but never block the save. Source of truth is always PostgreSQL.
- **Session state lives in Postgres** via `langgraph-checkpoint-postgres`.
  Survives process restarts; keyed by `session_id` (= `thread_id`).
- **One unified database** for events and LangGraph checkpoints. Two
  logical concerns, one connection target.
