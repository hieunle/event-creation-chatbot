"""Session-state REST endpoints.

- GET /api/session/{id}/state   — full state for one session (draft + messages).
- GET /api/sessions              — list of past sessions for the history drawer.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.agent.engine import ConversationEngine

log = logging.getLogger(__name__)
router = APIRouter()

# Latest checkpoint per thread, ordered by recency. ts is stored as ISO string
# in the checkpoint JSONB by langgraph.
_LIST_SESSIONS_SQL = text(
    """
    SELECT thread_id, ts FROM (
        SELECT DISTINCT ON (thread_id)
            thread_id,
            (checkpoint->>'ts')::timestamptz AS ts
        FROM checkpoints
        WHERE checkpoint_ns = ''
        ORDER BY thread_id, checkpoint_id DESC
    ) latest
    ORDER BY ts DESC NULLS LAST
    LIMIT :limit
    """
)


@router.get("/api/session/{session_id}/state")
async def get_session_state(session_id: str, request: Request) -> dict:
    engine: ConversationEngine = request.app.state.engine
    state = await engine.get_state(session_id)
    return {
        "session_id": session_id,
        "draft": state["draft"].model_dump(mode="json"),
        "messages": state["messages"],
    }


@router.get("/api/sessions")
async def list_sessions(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    """List past sessions for the history drawer.

    Each entry: { session_id, updated_at, title, message_count, has_draft }.
    Title comes from the first user message (or "(empty)" for sessions
    that only contain a system message). N+1 reads via engine.get_state
    are acceptable here — this endpoint is paged and used interactively.
    """
    sessionmaker = request.app.state.sessionmaker
    engine: ConversationEngine = request.app.state.engine

    try:
        async with sessionmaker() as session:
            rows = (await session.execute(_LIST_SESSIONS_SQL, {"limit": limit})).all()
    except SQLAlchemyError as e:
        # checkpoints table not present (e.g. tests against sqlite, or a fresh DB
        # before the first chat turn). Treat as "no history yet".
        log.warning("list_sessions: checkpoint query failed: %s", e)
        return {"sessions": []}

    sessions: list[dict[str, Any]] = []
    for row in rows:
        thread_id = row[0]
        ts = row[1]
        state = await engine.get_state(thread_id)
        messages = state["messages"]
        title = _derive_title(messages)
        sessions.append(
            {
                "session_id": thread_id,
                "updated_at": ts.isoformat() if ts is not None else None,
                "title": title,
                "message_count": sum(
                    1 for m in messages if m["role"] in ("user", "assistant")
                ),
                "has_draft": state["draft"].model_dump(exclude_none=True) != {},
            }
        )
    return {"sessions": sessions}


def _derive_title(messages: list[dict[str, Any]], max_len: int = 60) -> str:
    for m in messages:
        if m.get("role") == "user":
            content = (m.get("content") or "").strip()
            if content:
                return content if len(content) <= max_len else content[: max_len - 1] + "…"
    return "(empty)"
