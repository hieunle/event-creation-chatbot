"""REST endpoints to register and list events."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.models.event import EventCreate
from app.models.filters import EventQueryFilter
from app.services.memory import EventMemory
from app.services.repository import DuplicateEventError, EventRepository

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/events")
async def list_events(
    request: Request,
    limit: int = Query(default=50, ge=1, le=50),
) -> dict:
    repo: EventRepository = request.app.state.repository
    events = await repo.query(EventQueryFilter(latest=True, limit=limit))
    return {"events": [e.model_dump(mode="json") for e in events]}


@router.post("/api/register-event")
async def register_event(payload: EventCreate, request: Request) -> dict:
    repo: EventRepository = request.app.state.repository
    memory: EventMemory = request.app.state.memory
    try:
        saved = await repo.insert(payload)
    except DuplicateEventError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"status": "error", "message": str(e)},
        ) from e
    except Exception as e:  # noqa: BLE001
        log.exception("register-event failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "message": f"database error: {e}"},
        ) from e

    memory.index(saved)

    return {
        "status": "success",
        "message": f"Event {saved.name!r} registered successfully.",
        "event_id": saved.id,
    }
