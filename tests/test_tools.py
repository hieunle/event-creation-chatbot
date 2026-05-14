"""Agent tools tested in isolation, with a fake session state and a real
repository (sqlite in-memory) + memory (Chroma temp dir)."""
from __future__ import annotations

from datetime import date, time
from typing import Any

import pytest

from app.agent.responses import ChatResponse
from app.agent.tools import DraftInput, SeatTypeEntry, build_tools
from app.models.event import EventDraft
from app.models.filters import EventQueryFilter


@pytest.fixture
def tools_(repository, memory):
    return build_tools(repository, memory)


def _by_name(tools_list, name):
    return next(t for t in tools_list if t.name == name)


def _to_draft_input(draft_kwargs: dict[str, Any]) -> dict[str, Any]:
    """Shape EventDraft-style kwargs into a DraftInput dict: dates as ISO
    strings, seat_types as list of {label, price}."""
    out: dict[str, Any] = {}
    for k, v in draft_kwargs.items():
        if isinstance(v, (date, time)):
            out[k] = v.isoformat()
        elif k == "seat_types" and isinstance(v, dict):
            out[k] = [{"label": label, "price": price} for label, price in v.items()]
        else:
            out[k] = v
    return out


def _invoke_update(tool, draft_kwargs, current_draft=None):
    """Drive the update_event_draft tool with a fake injected state and a
    deterministic tool_call_id. Returns the resulting Command.

    InjectedToolCallId requires the full ToolCall envelope shape; state is
    still passed in args because in unit-tests there's no LangGraph runtime
    to inject it from.
    """
    return tool.invoke({
        "name": tool.name,
        "args": {
            "draft": _to_draft_input(draft_kwargs),
            "state": {"draft": current_draft or EventDraft()},
        },
        "type": "tool_call",
        "id": "test_tc_1",
    })


class TestUpdateEventDraft:
    async def test_sets_fields_first_time(self, tools_):
        tool = _by_name(tools_, "update_event_draft")
        cmd = _invoke_update(tool, {"name": "Kyoto Jazz Night",
                                    "date": date(2026, 10, 10).isoformat(),
                                    "time": time(19, 0).isoformat()})
        updated_draft = cmd.update["draft"]
        assert updated_draft.name == "Kyoto Jazz Night"
        assert updated_draft.date == date(2026, 10, 10)
        # ToolMessage payload as JSON in the appended message
        msg = cmd.update["messages"][0]
        import json
        payload = json.loads(msg.content)
        assert payload["fields"]["name"]["status"] == "set"
        assert "venue_name" in payload["missing_required"]
        assert payload["all_required_filled"] is False

    async def test_revision_includes_previous(self, tools_):
        tool = _by_name(tools_, "update_event_draft")
        # First, set a draft with a date
        current = EventDraft(name="Kyoto Jazz Night", date=date(2026, 10, 10))
        cmd = _invoke_update(tool, {"date": date(2026, 10, 12).isoformat()},
                             current_draft=current)
        import json
        payload = json.loads(cmd.update["messages"][0].content)
        date_field = payload["fields"]["date"]
        assert date_field["status"] == "set"
        assert date_field["previous"] == "2026-10-10"
        assert cmd.update["draft"].date == date(2026, 10, 12)

    async def test_past_event_date_marked_invalid(self, tools_):
        tool = _by_name(tools_, "update_event_draft")
        cmd = _invoke_update(tool, {"date": date(2020, 1, 1).isoformat()})
        import json
        payload = json.loads(cmd.update["messages"][0].content)
        assert payload["fields"]["date"]["status"] == "invalid"
        assert "past" in payload["fields"]["date"]["reason"]
        # Draft is reverted — past date not stored
        assert cmd.update["draft"].date is None

    async def test_ticket_limit_over_capacity_marked_invalid(self, tools_):
        tool = _by_name(tools_, "update_event_draft")
        current = EventDraft(capacity=100)
        cmd = _invoke_update(tool, {"ticket_limit": 500}, current_draft=current)
        import json
        payload = json.loads(cmd.update["messages"][0].content)
        assert payload["fields"]["ticket_limit"]["status"] == "invalid"
        assert "capacity" in payload["fields"]["ticket_limit"]["reason"]
        assert cmd.update["draft"].ticket_limit is None
        assert cmd.update["draft"].capacity == 100

    async def test_unchanged_when_same_value(self, tools_):
        tool = _by_name(tools_, "update_event_draft")
        current = EventDraft(name="Kyoto Jazz Night")
        cmd = _invoke_update(tool, {"name": "Kyoto Jazz Night"},
                             current_draft=current)
        import json
        payload = json.loads(cmd.update["messages"][0].content)
        assert payload["fields"]["name"]["status"] == "unchanged"

    async def test_duplicate_flagged_when_name_date_exist(
        self, tools_, repository, sample_event
    ):
        tool = _by_name(tools_, "update_event_draft")
        await repository.insert(sample_event)

        cmd = _invoke_update(tool, {"name": sample_event.name,
                                    "date": sample_event.date.isoformat()})
        import json
        payload = json.loads(cmd.update["messages"][0].content)
        # Name (the field touched first in our impl preference) should be flagged
        assert payload["fields"]["name"]["status"] == "duplicate"
        # And the conflicting field is reverted in stored draft
        assert cmd.update["draft"].name is None or cmd.update["draft"].name != sample_event.name

    async def test_invalid_time_is_caught_and_reported(self, tools_):
        tool = _by_name(tools_, "update_event_draft")
        # "26:00" is parseable-looking but out of range — `time.fromisoformat`
        # raises ValueError. Must surface as invalid, not propagate as 500.
        cmd = tool.invoke({
            "name": tool.name,
            "args": {
                "draft": {"time": "26:00"},
                "state": {"draft": EventDraft()},
            },
            "type": "tool_call",
            "id": "test_tc_invalid_time",
        })
        import json
        payload = json.loads(cmd.update["messages"][0].content)
        assert payload["fields"]["time"]["status"] == "invalid"
        assert "24-hour" in payload["fields"]["time"]["reason"]
        # Draft should not have been corrupted
        assert cmd.update["draft"].time is None

    async def test_invalid_email_is_caught_and_reported(self, tools_):
        tool = _by_name(tools_, "update_event_draft")
        cmd = tool.invoke({
            "name": tool.name,
            "args": {
                "draft": {"organizer_email": "not-an-email"},
                "state": {"draft": EventDraft()},
            },
            "type": "tool_call",
            "id": "test_tc_invalid_email",
        })
        import json
        payload = json.loads(cmd.update["messages"][0].content)
        assert payload["fields"]["organizer_email"]["status"] == "invalid"
        assert cmd.update["draft"].organizer_email is None

    async def test_invalid_field_does_not_block_valid_field(self, tools_):
        """Mixed payload: name is good, time is bad. Name should still apply."""
        tool = _by_name(tools_, "update_event_draft")
        cmd = tool.invoke({
            "name": tool.name,
            "args": {
                "draft": {"name": "Workshop", "time": "26:00"},
                "state": {"draft": EventDraft()},
            },
            "type": "tool_call",
            "id": "test_tc_mixed",
        })
        import json
        payload = json.loads(cmd.update["messages"][0].content)
        assert payload["fields"]["name"]["status"] == "set"
        assert payload["fields"]["time"]["status"] == "invalid"
        assert cmd.update["draft"].name == "Workshop"
        assert cmd.update["draft"].time is None

    async def test_all_required_filled_when_complete(self, tools_, sample_event_kwargs):
        tool = _by_name(tools_, "update_event_draft")
        # Convert dates/times to ISO for the tool's JSON-shape input
        prepared = {}
        for k, v in sample_event_kwargs.items():
            if hasattr(v, "isoformat"):
                prepared[k] = v.isoformat()
            else:
                prepared[k] = v
        cmd = _invoke_update(tool, prepared)
        import json
        payload = json.loads(cmd.update["messages"][0].content)
        assert payload["all_required_filled"] is True
        assert payload["missing_required"] == []


class TestSaveEvent:
    async def test_rejects_incomplete_draft(self, tools_):
        save = _by_name(tools_, "save_event")
        partial = EventDraft(name="X")
        result = save.invoke({"state": {"draft": partial}})
        assert result["status"] == "error_validation"

    async def test_persists_complete_draft(self, tools_, sample_event_kwargs, repository):
        save = _by_name(tools_, "save_event")
        draft = EventDraft(**sample_event_kwargs)
        result = save.invoke({"state": {"draft": draft}})
        assert result["status"] == "success"
        assert "event_id" in result
        fetched = await repository.get_by_id(result["event_id"])
        assert fetched is not None
        assert fetched.name == sample_event_kwargs["name"]

    async def test_duplicate_returns_error_db(
        self, tools_, sample_event_kwargs, repository
    ):
        save = _by_name(tools_, "save_event")
        draft = EventDraft(**sample_event_kwargs)
        first = save.invoke({"state": {"draft": draft}})
        assert first["status"] == "success"
        second = save.invoke({"state": {"draft": draft}})
        assert second["status"] == "error_db"


class TestStrictSchemas:
    """OpenAI strict tool-schema mode requires:
      - every key in `properties` is listed in `required`
      - `additionalProperties: false` is set

    These schemas are consumed by `convert_to_openai_tool` at first model call.
    The agent's runtime tests don't exercise this path (the scripted model
    has a no-op bind_tools), so we lock the contract in directly.
    """

    def test_draft_input_schema_is_strict(self):
        schema = DraftInput.model_json_schema()
        props = list(schema.get("properties", {}).keys())
        assert sorted(schema.get("required", [])) == sorted(props)
        assert schema.get("additionalProperties") is False

    def test_seat_type_entry_schema_is_strict(self):
        schema = SeatTypeEntry.model_json_schema()
        props = list(schema.get("properties", {}).keys())
        assert sorted(schema.get("required", [])) == sorted(props)
        assert schema.get("additionalProperties") is False

    def test_query_filter_schema_is_strict(self):
        schema = EventQueryFilter.model_json_schema()
        props = list(schema.get("properties", {}).keys())
        assert sorted(schema.get("required", [])) == sorted(props)
        assert schema.get("additionalProperties") is False

    def test_chat_response_schema_is_strict(self):
        schema = ChatResponse.model_json_schema()
        props = list(schema.get("properties", {}).keys())
        assert sorted(schema.get("required", [])) == sorted(props)
        assert schema.get("additionalProperties") is False


class TestQueryAndSearch:
    async def test_query_filters_by_category(
        self, tools_, repository, sample_event_kwargs
    ):
        from app.models.event import EventCreate
        await repository.insert(EventCreate(**sample_event_kwargs))
        kw2 = {**sample_event_kwargs, "name": "Meetup",
               "date": date(2026, 11, 1), "purchase_end": date(2026, 10, 31),
               "category": "Meetup"}
        await repository.insert(EventCreate(**kw2))

        query_tool = _by_name(tools_, "query_events")
        results = query_tool.invoke({"filter": {"category": "Concert", "limit": 5}})
        assert len(results) == 1
        assert results[0]["category"] == "Concert"

    async def test_search_rehydrates_from_repository(
        self, tools_, repository, sample_event, memory
    ):
        saved = await repository.insert(sample_event)
        memory.index(saved)
        search_tool = _by_name(tools_, "search_events")
        results = search_tool.invoke({"query": "jazz Kyoto", "k": 3})
        assert len(results) >= 1
        assert results[0]["name"] == sample_event.name
