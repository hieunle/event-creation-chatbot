from __future__ import annotations

from datetime import date as date_type
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.event import EventCreate, EventDB, EventRead
from app.models.filters import EventQueryFilter


class DuplicateEventError(Exception):
    """Raised when an event with the same name+date already exists."""


class EventRepository:
    """PostgreSQL access for events. Owns transactions and duplicate detection."""

    def __init__(self, sessionmaker: async_sessionmaker):
        self._sessionmaker = sessionmaker

    async def find_duplicate(self, name: str, date: date_type) -> Optional[EventRead]:
        async with self._sessionmaker() as session:
            stmt = select(EventDB).where(EventDB.name == name, EventDB.date == date)
            row = (await session.execute(stmt)).scalar_one_or_none()
            return row.to_read() if row else None

    async def insert(self, event: EventCreate) -> EventRead:
        # Pre-check shortcut: hit find_duplicate first so we raise a
        # typed error rather than relying on dialect-specific IntegrityError
        # messages. The unique constraint is still the ultimate safety net.
        existing = await self.find_duplicate(event.name, event.date)
        if existing is not None:
            raise DuplicateEventError(
                f"An event named {event.name!r} on {event.date} already exists"
            )

        async with self._sessionmaker() as session:
            db_event = EventDB(**event.model_dump())
            session.add(db_event)
            try:
                await session.commit()
            except IntegrityError as e:
                await session.rollback()
                msg = str(e.orig)
                if (
                    "events_name_date_unique" in msg
                    or "events.name, events.date" in msg
                    or "name, date" in msg
                ):
                    raise DuplicateEventError(
                        f"An event named {event.name!r} on {event.date} already exists"
                    ) from e
                raise
            await session.refresh(db_event)
            return db_event.to_read()

    async def get_by_id(self, event_id: int) -> Optional[EventRead]:
        async with self._sessionmaker() as session:
            row = await session.get(EventDB, event_id)
            return row.to_read() if row else None

    async def get_many(self, event_ids: list[int]) -> list[EventRead]:
        if not event_ids:
            return []
        async with self._sessionmaker() as session:
            stmt = select(EventDB).where(EventDB.id.in_(event_ids))
            rows = (await session.execute(stmt)).scalars().all()
            # preserve caller's order
            by_id = {r.id: r for r in rows}
            return [by_id[i].to_read() for i in event_ids if i in by_id]

    async def query(self, filter: EventQueryFilter) -> list[EventRead]:
        async with self._sessionmaker() as session:
            stmt = select(EventDB)
            if filter.date_from is not None:
                stmt = stmt.where(EventDB.date >= filter.date_from)
            if filter.date_to is not None:
                stmt = stmt.where(EventDB.date <= filter.date_to)
            if filter.category is not None:
                stmt = stmt.where(EventDB.category == filter.category)
            if filter.latest:
                stmt = stmt.order_by(EventDB.created_at.desc())
            else:
                stmt = stmt.order_by(EventDB.date.desc())
            stmt = stmt.limit(filter.limit or 5)
            rows = (await session.execute(stmt)).scalars().all()
            return [r.to_read() for r in rows]
