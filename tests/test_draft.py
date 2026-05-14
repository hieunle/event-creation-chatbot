"""Validation tests for EventDraft and EventCreate.

External behavior under test: which inputs Pydantic accepts vs rejects, what
the `missing_required` list contains for partial drafts, and what cross-field
rules fire on EventCreate.
"""
from __future__ import annotations

from datetime import date, time

import pytest
from pydantic import ValidationError

from app.models.event import REQUIRED_FIELDS, EventCreate, EventDraft


class TestEventDraft:
    def test_empty_draft_has_all_required_missing(self):
        draft = EventDraft()
        assert set(draft.missing_required()) == set(REQUIRED_FIELDS)
        assert not draft.is_complete()

    def test_partial_draft_tracks_missing(self):
        draft = EventDraft(name="Kyoto Jazz Night", date=date(2026, 3, 10))
        missing = draft.missing_required()
        assert "name" not in missing
        assert "date" not in missing
        assert "time" in missing
        assert "venue_name" in missing

    def test_invalid_date_format_rejected(self):
        with pytest.raises(ValidationError):
            EventDraft(date="March 10th")  # type: ignore[arg-type]

    def test_invalid_email_rejected(self):
        with pytest.raises(ValidationError):
            EventDraft(organizer_email="not-an-email")  # type: ignore[arg-type]

    def test_ticket_limit_must_be_positive(self):
        with pytest.raises(ValidationError):
            EventDraft(ticket_limit=0)

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            EventDraft(name="X", unknown_field="oops")  # type: ignore[call-arg]

    def test_seat_types_accepts_dict(self):
        draft = EventDraft(seat_types={"VIP": 10000, "Regular": 5000})
        assert draft.seat_types == {"VIP": 10000, "Regular": 5000}


class TestEventCreate:
    def test_valid_event_accepted(self, sample_event_kwargs):
        EventCreate(**sample_event_kwargs)

    def test_purchase_end_after_event_date_rejected(self, sample_event_kwargs):
        sample_event_kwargs["purchase_end"] = date(2026, 10, 15)  # after event
        with pytest.raises(ValidationError) as exc:
            EventCreate(**sample_event_kwargs)
        assert "purchase_end" in str(exc.value)

    def test_purchase_end_before_purchase_start_rejected(self, sample_event_kwargs):
        sample_event_kwargs["purchase_start"] = date(2026, 3, 1)
        sample_event_kwargs["purchase_end"] = date(2026, 2, 1)
        with pytest.raises(ValidationError):
            EventCreate(**sample_event_kwargs)

    def test_recurring_without_frequency_rejected(self, sample_event_kwargs):
        sample_event_kwargs["is_recurring"] = True
        sample_event_kwargs["recurrence_frequency"] = None
        with pytest.raises(ValidationError) as exc:
            EventCreate(**sample_event_kwargs)
        assert "recurrence_frequency" in str(exc.value)

    def test_recurring_with_frequency_accepted(self, sample_event_kwargs):
        sample_event_kwargs["is_recurring"] = True
        sample_event_kwargs["recurrence_frequency"] = "monthly"
        EventCreate(**sample_event_kwargs)

    def test_negative_seat_price_rejected(self, sample_event_kwargs):
        sample_event_kwargs["seat_types"] = {"VIP": -1}
        with pytest.raises(ValidationError):
            EventCreate(**sample_event_kwargs)

    def test_empty_seat_types_rejected(self, sample_event_kwargs):
        sample_event_kwargs["seat_types"] = {}
        with pytest.raises(ValidationError):
            EventCreate(**sample_event_kwargs)

    def test_missing_required_field_rejected(self, sample_event_kwargs):
        del sample_event_kwargs["venue_name"]
        with pytest.raises(ValidationError) as exc:
            EventCreate(**sample_event_kwargs)
        assert "venue_name" in str(exc.value)

    def test_past_event_date_rejected(self, sample_event_kwargs):
        sample_event_kwargs["date"] = date(2020, 1, 1)
        sample_event_kwargs["purchase_start"] = date(2019, 12, 1)
        sample_event_kwargs["purchase_end"] = date(2019, 12, 31)
        with pytest.raises(ValidationError) as exc:
            EventCreate(**sample_event_kwargs)
        assert "past" in str(exc.value)

    def test_ticket_limit_exceeding_capacity_rejected(self, sample_event_kwargs):
        sample_event_kwargs["ticket_limit"] = 10
        sample_event_kwargs["capacity"] = 5
        with pytest.raises(ValidationError) as exc:
            EventCreate(**sample_event_kwargs)
        assert "capacity" in str(exc.value)

    def test_whitespace_only_name_rejected(self, sample_event_kwargs):
        sample_event_kwargs["name"] = "   "
        with pytest.raises(ValidationError):
            EventCreate(**sample_event_kwargs)

    def test_name_is_trimmed(self, sample_event_kwargs):
        sample_event_kwargs["name"] = "  Kyoto Jazz Night  "
        event = EventCreate(**sample_event_kwargs)
        assert event.name == "Kyoto Jazz Night"


class TestDraftToCreate:
    def test_complete_draft_validates_to_create(self, sample_event_kwargs):
        draft = EventDraft(**sample_event_kwargs)
        assert draft.is_complete()
        event = EventCreate.model_validate(draft.model_dump(exclude_none=True))
        assert event.name == "Kyoto Jazz Night"

    def test_partial_draft_to_create_raises_with_missing_fields(self):
        draft = EventDraft(name="Test", date=date(2026, 3, 10), time=time(19, 0))
        with pytest.raises(ValidationError) as exc:
            EventCreate.model_validate(draft.model_dump(exclude_none=True))
        msg = str(exc.value)
        # At least a couple required fields should be flagged
        assert "venue_name" in msg or "seat_types" in msg or "ticket_limit" in msg
