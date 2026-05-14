"""Event memory tests — index + search round-trip via Chroma."""
from __future__ import annotations

from datetime import date, datetime, time

import pytest

from app.models.event import EventRead


def _event_read(**overrides) -> EventRead:
    defaults = dict(
        id=1,
        name="Kyoto Jazz Night",
        date=date(2026, 10, 10),
        time=time(19, 0),
        description="A live jazz performance in Kyoto.",
        seat_types={"VIP": 10000},
        purchase_start=date(2026, 6, 1),
        purchase_end=date(2026, 10, 9),
        ticket_limit=4,
        venue_name="Kyoto Concert Hall",
        venue_address="123 Sakyo-ku, Kyoto",
        capacity=1000,
        organizer_name="Fenix Entertainment",
        organizer_email="info@fenix.co.jp",
        category="Concert",
        language="Japanese",
        is_recurring=False,
        recurrence_frequency=None,
        is_online=False,
        created_at=datetime(2026, 1, 1, 12, 0, 0),
        updated_at=datetime(2026, 1, 1, 12, 0, 0),
    )
    defaults.update(overrides)
    return EventRead(**defaults)


class TestIndexAndSearch:
    def test_indexed_event_is_recoverable(self, memory):
        event = _event_read()
        memory.index(event)
        ids = memory.search("jazz Kyoto concert", k=3)
        assert event.id in ids

    def test_semantic_match_across_fields(self, memory):
        jazz = _event_read(id=1, name="Kyoto Jazz Night",
                           description="Live jazz performance")
        food = _event_read(id=2, name="Osaka Food Festival",
                           date=date(2026, 11, 1), purchase_end=date(2026, 10, 31),
                           description="Street food tasting",
                           venue_name="Osaka Park", category="Festival")
        memory.index(jazz)
        memory.index(food)

        jazz_results = memory.search("jazz performance", k=2)
        assert jazz_results[0] == jazz.id

        food_results = memory.search("food tasting festival", k=2)
        assert food_results[0] == food.id

    def test_search_with_no_data_returns_empty(self, memory):
        assert memory.search("anything", k=3) == []

    def test_index_is_best_effort(self, memory, monkeypatch):
        """Failures during index() must not raise."""
        def explode(*args, **kwargs):
            raise RuntimeError("chroma down")
        monkeypatch.setattr(memory._collection, "upsert", explode)
        memory.index(_event_read())  # must not raise

    def test_delete_removes_event(self, memory):
        event = _event_read()
        memory.index(event)
        assert event.id in memory.search("Kyoto jazz", k=3)
        memory.delete(event.id)
        assert event.id not in memory.search("Kyoto jazz", k=3)
