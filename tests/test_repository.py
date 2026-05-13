"""Repository tests — round-trip insert, duplicate detection, queries."""
from __future__ import annotations

from datetime import date

import pytest

from app.models.event import EventCreate
from app.models.filters import EventQueryFilter
from app.services.repository import DuplicateEventError


pytestmark = pytest.mark.asyncio


class TestInsert:
    async def test_round_trip_preserves_fields(self, repository, sample_event):
        saved = await repository.insert(sample_event)
        fetched = await repository.get_by_id(saved.id)
        assert fetched is not None
        assert fetched.name == sample_event.name
        assert fetched.seat_types == sample_event.seat_types
        assert fetched.organizer_email == sample_event.organizer_email

    async def test_duplicate_name_date_raises(self, repository, sample_event):
        await repository.insert(sample_event)
        with pytest.raises(DuplicateEventError):
            await repository.insert(sample_event)

    async def test_same_name_different_date_allowed(
        self, repository, sample_event_kwargs
    ):
        await repository.insert(EventCreate(**sample_event_kwargs))
        sample_event_kwargs["date"] = date(2026, 4, 10)
        sample_event_kwargs["purchase_end"] = date(2026, 4, 9)
        # Second insert must NOT raise
        await repository.insert(EventCreate(**sample_event_kwargs))

    async def test_duplicate_rollback_leaves_table_consistent(
        self, repository, sample_event
    ):
        await repository.insert(sample_event)
        with pytest.raises(DuplicateEventError):
            await repository.insert(sample_event)
        # Original still retrievable, no orphan row
        existing = await repository.find_duplicate(sample_event.name, sample_event.date)
        assert existing is not None


class TestQuery:
    async def test_find_duplicate_by_name_date(self, repository, sample_event):
        saved = await repository.insert(sample_event)
        found = await repository.find_duplicate(saved.name, saved.date)
        assert found is not None and found.id == saved.id

    async def test_find_duplicate_returns_none_when_absent(self, repository):
        assert await repository.find_duplicate("Nothing", date(2026, 3, 10)) is None

    async def test_query_by_category(self, repository, sample_event_kwargs):
        sample_event_kwargs["category"] = "Concert"
        await repository.insert(EventCreate(**sample_event_kwargs))

        kw2 = {**sample_event_kwargs, "name": "Tech Meetup",
               "date": date(2026, 4, 1), "purchase_end": date(2026, 3, 31),
               "category": "Meetup"}
        await repository.insert(EventCreate(**kw2))

        concerts = await repository.query(EventQueryFilter(category="Concert"))
        assert len(concerts) == 1
        assert concerts[0].category == "Concert"

    async def test_query_by_date_range(self, repository, sample_event_kwargs):
        await repository.insert(EventCreate(**sample_event_kwargs))
        kw2 = {**sample_event_kwargs, "name": "Other",
               "date": date(2026, 6, 1), "purchase_end": date(2026, 5, 1)}
        await repository.insert(EventCreate(**kw2))

        march = await repository.query(
            EventQueryFilter(date_from=date(2026, 3, 1), date_to=date(2026, 3, 31))
        )
        assert len(march) == 1
        assert march[0].date == date(2026, 3, 10)

    async def test_get_many_preserves_order(self, repository, sample_event_kwargs):
        a = await repository.insert(EventCreate(**sample_event_kwargs))
        kw2 = {**sample_event_kwargs, "name": "Second",
               "date": date(2026, 4, 1), "purchase_end": date(2026, 3, 31)}
        b = await repository.insert(EventCreate(**kw2))
        got = await repository.get_many([b.id, a.id])
        assert [e.id for e in got] == [b.id, a.id]
