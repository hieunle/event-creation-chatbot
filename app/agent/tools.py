"""Agent tools — thin wrappers over the deep modules.

Tools take only LLM-facing arguments. Dependencies (repository, memory) are
captured via a closure built once at app startup. Session state is injected
by LangGraph via `InjectedState`; state updates flow back via `Command`.
Because update_event_draft returns a Command, it also must emit its own
ToolMessage with the right tool_call_id (via `InjectedToolCallId`).

`DraftInput` is the LLM-facing schema for update_event_draft. It mirrors
EventDraft but is hand-shaped to satisfy OpenAI's strict tool-schema rules
(every property listed in `required`, `additionalProperties: false`, no
free-form dict types). The tool converts DraftInput → EventDraft at the
boundary.
"""
from __future__ import annotations

import asyncio
import json
import threading
from datetime import date as date_type, time as time_type
from typing import Annotated, Any, Optional

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.models.event import EventCreate, EventDraft, EventRead
from app.models.filters import EventQueryFilter
from app.services.memory import EventMemory
from app.services.repository import DuplicateEventError, EventRepository


def _run_sync(coro: Any) -> Any:
    """Drive an async coroutine from a sync tool body.

    Tools may be invoked from inside an already-running event loop (FastAPI
    handler → agent.ainvoke → sync ToolNode → this tool). Calling
    asyncio.run() from inside a running loop raises; running a fresh loop in
    a worker thread avoids the deadlock without requiring the whole stack to
    be async-aware.
    """
    result: dict[str, Any] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001
            result["error"] = exc

    t = threading.Thread(target=runner)
    t.start()
    t.join()
    if "error" in result:
        raise result["error"]
    return result["value"]


def _json_safe(value: Any) -> Any:
    if isinstance(value, (date_type, time_type)):
        return value.isoformat()
    return value


def _strict_schema(core_schema: Any, handler: Any) -> dict:
    """Pydantic JSON-schema customizer: list every property in `required` and
    set `additionalProperties: false` — what OpenAI strict mode demands.

    Must receive the core schema and pass it (not the class) to `handler`.
    """
    schema = handler(core_schema)
    if "properties" in schema:
        schema["required"] = list(schema["properties"].keys())
        schema["additionalProperties"] = False
    return schema


class SeatTypeEntry(BaseModel):
    """One seat tier (label + price). Strict-mode friendly: structured object
    instead of a free-form dict. The tool converts a list[SeatTypeEntry] into
    the internal {label: price} dict."""

    model_config = ConfigDict(extra="forbid")
    label: str = Field(description="Seat tier label, e.g., 'VIP'")
    price: int = Field(description="Price in the event's currency, e.g., 10000")

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict:
        return _strict_schema(core_schema, handler)


class DraftInput(BaseModel):
    """LLM-facing input shape for update_event_draft. Strict-mode compliant.

    Every field is sent on every call (strict mode requires it); the LLM
    fills `null` for fields the user didn't mention. Dates/times are ISO
    strings to keep the schema flat and primitive-typed. Seat types are a
    list of {label, price} objects rather than a dict.
    """

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None)
    date: Optional[str] = Field(default=None, description="Event date, YYYY-MM-DD")
    time: Optional[str] = Field(default=None, description="Event time, HH:MM (24h)")
    description: Optional[str] = Field(default=None)
    seat_types: Optional[list[SeatTypeEntry]] = Field(default=None)
    purchase_start: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    purchase_end: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    ticket_limit: Optional[int] = Field(default=None)
    venue_name: Optional[str] = Field(default=None)
    venue_address: Optional[str] = Field(default=None)
    capacity: Optional[int] = Field(default=None)
    organizer_name: Optional[str] = Field(default=None)
    organizer_email: Optional[str] = Field(default=None)
    category: Optional[str] = Field(default=None)
    language: Optional[str] = Field(default=None)
    is_recurring: Optional[bool] = Field(default=None)
    recurrence_frequency: Optional[str] = Field(default=None)
    is_online: Optional[bool] = Field(default=None)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict:
        return _strict_schema(core_schema, handler)


_DATE_FIELDS = {"date", "purchase_start", "purchase_end"}
_TIME_FIELDS = {"time"}


def _parse_field(field_name: str, value: Any) -> Any:
    """Convert one DraftInput field value into its EventDraft-compatible
    Python type. Raises ValueError on bad date/time/seat formats."""
    if field_name in _DATE_FIELDS and isinstance(value, str):
        return date_type.fromisoformat(value)
    if field_name in _TIME_FIELDS and isinstance(value, str):
        return time_type.fromisoformat(value)
    if field_name == "seat_types" and isinstance(value, list):
        return {entry.label: entry.price for entry in value}
    return value


_FIELD_FORMAT_HINTS: dict[str, str] = {
    "date": "expected YYYY-MM-DD, e.g., 2026-03-10",
    "purchase_start": "expected YYYY-MM-DD",
    "purchase_end": "expected YYYY-MM-DD",
    "time": "expected HH:MM in 24-hour format, e.g., 19:00",
    "organizer_email": "expected a valid email address, e.g., name@example.com",
    "ticket_limit": "expected a positive integer (>= 1)",
    "capacity": "expected a positive integer (>= 1)",
}


def _format_parse_error(field_name: str, exc: Exception) -> str:
    hint = _FIELD_FORMAT_HINTS.get(field_name)
    base = str(exc) or exc.__class__.__name__
    return f"{base} — {hint}" if hint else base


def _check_draft_invariants(
    merged: dict[str, Any],
    current: EventDraft,
    fields_result: dict[str, dict[str, Any]],
) -> None:
    """Apply EventCreate-style cross-field rules to the partial draft.

    Each rule fires only when its inputs are present in `merged`. Offending
    fields are tagged `invalid` and reverted to the current draft's value so
    the agent can re-ask just that field. Mutates `merged` and `fields_result`
    in place.
    """
    today = date_type.today()

    def _invalidate(field: str, reason: str) -> None:
        fields_result[field] = {
            "status": "invalid",
            "value": _json_safe(merged.get(field)),
            "reason": reason,
        }
        merged[field] = getattr(current, field, None)

    date = merged.get("date")
    if date is not None and date < today:
        _invalidate("date", f"event date must not be in the past (today is {today.isoformat()})")

    p_start = merged.get("purchase_start")
    p_end = merged.get("purchase_end")
    date = merged.get("date")  # re-read in case _invalidate reverted it
    if p_start is not None and p_end is not None and p_end < p_start:
        _invalidate("purchase_end", "purchase_end must be on or after purchase_start")
    elif p_end is not None and date is not None and p_end > date:
        _invalidate("purchase_end", "purchase_end must be on or before the event date")

    ticket_limit = merged.get("ticket_limit")
    capacity = merged.get("capacity")
    if ticket_limit is not None and capacity is not None and ticket_limit > capacity:
        _invalidate("ticket_limit", "ticket_limit must be <= capacity")


def _build_draft_with_validation(
    merged: dict[str, Any],
    current: EventDraft,
    fields_result: dict[str, dict[str, Any]],
) -> EventDraft:
    """Construct EventDraft from merged values. If Pydantic raises, mark the
    offending fields invalid in fields_result, revert them to the current
    draft's values, and retry. Returns a fully-valid EventDraft."""
    try:
        return EventDraft(**{k: v for k, v in merged.items() if v is not None})
    except ValidationError as e:
        for err in e.errors():
            loc = err.get("loc") or ()
            if not loc:
                continue
            bad = loc[0]
            if not isinstance(bad, str) or bad not in merged:
                continue
            fields_result[bad] = {
                "status": "invalid",
                "value": _json_safe(merged[bad]),
                "reason": _format_parse_error(bad, Exception(err.get("msg", "invalid value"))),
            }
            merged[bad] = getattr(current, bad, None)
        return EventDraft(**{k: v for k, v in merged.items() if v is not None})


def _event_summary(event: EventRead) -> dict:
    return {
        "event_id": event.id,
        "name": event.name,
        "date": event.date.isoformat(),
        "time": event.time.isoformat(),
        "category": event.category,
        "venue_name": event.venue_name,
        "is_online": event.is_online,
        "description": event.description,
    }


def build_tools(repository: EventRepository, memory: EventMemory) -> list[BaseTool]:
    """Construct the four agent tools with deps captured in closure."""

    @tool
    def update_event_draft(
        draft: DraftInput,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """Extract event fields from the user's latest message and merge them into the draft.

        Send every field on every call (strict mode). Use `null` for fields
        the user did NOT mention; fields with real values are merged into the
        draft. The tool checks for duplicate (name, date), replaces seat_types
        wholesale when present, and reports per-field outcomes.

        Per-field statuses: `set` (new value accepted), `unchanged` (same as
        before), `invalid` (parse / validation failure — LLM should ask the
        user to correct), `duplicate` (rejected, conflicts with an existing
        event). A `previous` value on a `set` entry signals the user revised
        an earlier answer.
        """
        current: EventDraft = state.get("draft") or EventDraft()
        merged = current.model_dump()
        fields_result: dict[str, dict[str, Any]] = {}
        accepted: list[str] = []

        # Phase 1: parse each provided field (date/time/seat-types conversion).
        # Per-field try/except so a bad value on one field doesn't fail the others.
        parsed: dict[str, Any] = {}
        for field_name in draft.model_fields_set:
            raw = getattr(draft, field_name)
            if raw is None:
                continue  # strict-mode filler — treat as "not mentioned"
            try:
                parsed[field_name] = _parse_field(field_name, raw)
            except (ValueError, TypeError) as exc:
                fields_result[field_name] = {
                    "status": "invalid",
                    "value": raw if not hasattr(raw, "model_dump") else raw.model_dump(),
                    "reason": _format_parse_error(field_name, exc),
                }

        # Phase 2: detect unchanged vs set, stage into merged.
        for field_name, new_value in parsed.items():
            old_value = getattr(current, field_name)
            if new_value == old_value:
                fields_result[field_name] = {"status": "unchanged"}
                continue
            entry: dict[str, Any] = {"status": "set", "value": _json_safe(new_value)}
            if old_value is not None:
                entry["previous"] = _json_safe(old_value)
            fields_result[field_name] = entry
            merged[field_name] = new_value
            accepted.append(field_name)

        # Phase 3: duplicate check (only when both name and date are known).
        name = merged.get("name")
        date = merged.get("date")
        if name and date:
            existing = _run_sync(repository.find_duplicate(name, date))
            if existing is not None:
                target = (
                    "name" if "name" in accepted
                    else "date" if "date" in accepted
                    else "name"
                )
                fields_result[target] = {
                    "status": "duplicate",
                    "value": _json_safe(merged[target]),
                    "reason": (
                        f"An event named {name!r} on {date} already exists. "
                        "Choose a different name or date."
                    ),
                }
                merged[target] = getattr(current, target)

        # Phase 3.5: cross-field domain checks (past date, purchase window,
        # ticket_limit <= capacity). Fires whenever the relevant fields are
        # present so the agent can correct issues mid-conversation instead of
        # only at save time.
        _check_draft_invariants(merged, current, fields_result)

        # Phase 4: build the new draft. If a field violates EventDraft's
        # constraints (bad email, negative ticket_limit, etc.), Pydantic
        # raises — mark those fields invalid and revert.
        new_draft = _build_draft_with_validation(merged, current, fields_result)
        payload = {
            "fields": fields_result,
            "missing_required": new_draft.missing_required(),
            "all_required_filled": new_draft.is_complete(),
        }
        return Command(
            update={
                "draft": new_draft,
                "messages": [
                    ToolMessage(content=json.dumps(payload), tool_call_id=tool_call_id)
                ],
            }
        )

    @tool
    def save_event(state: Annotated[dict, InjectedState]) -> dict:
        """Commit the current event draft to the database. Call ONLY after the
        user has explicitly confirmed the summary."""
        current: EventDraft = state.get("draft") or EventDraft()
        try:
            event = EventCreate.model_validate(current.model_dump(exclude_none=True))
        except ValidationError as e:
            return {
                "status": "error_validation",
                "reason": "draft is not yet complete or has invalid fields",
                "errors": [
                    {"loc": ".".join(str(p) for p in err["loc"]), "msg": err["msg"]}
                    for err in e.errors()
                ],
            }
        try:
            saved = _run_sync(repository.insert(event))
        except DuplicateEventError as e:
            return {"status": "error_db", "reason": str(e)}
        except Exception as e:  # noqa: BLE001
            return {"status": "error_db", "reason": f"database error: {e}"}

        memory.index(saved)  # best-effort; never raises

        return {
            "status": "success",
            "event_id": saved.id,
            "name": saved.name,
            "date": saved.date.isoformat(),
        }

    @tool
    def query_events(filter: EventQueryFilter) -> list[dict]:
        """Structured query for past events. Use for 'latest', 'most recent',
        events in a date range, by category, or counts."""
        results = _run_sync(repository.query(filter))
        return [_event_summary(e) for e in results]

    @tool
    def search_events(query: str, k: int = 3) -> list[dict]:
        """Semantic search over previously-saved events. Use for fuzzy
        questions like 'find my jazz events' or 'that thing in Kyoto'."""
        ids = memory.search(query, k=k)
        if not ids:
            return []
        rehydrated = _run_sync(repository.get_many(ids))
        return [_event_summary(e) for e in rehydrated]

    return [update_event_draft, save_event, query_events, search_events]
