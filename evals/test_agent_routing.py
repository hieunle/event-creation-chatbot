"""Agent routing evals.

For each user input we assert two things:
  1. The agent invoked the expected domain tool(s).
  2. The final `ChatResponse.scenario` tag matches the expected category.

These are *behavioural* tests against a real LLM, not unit tests:
  - Stochastic. Even with temperature=0, model upgrades / prompt edits can
    flip individual cases. Treat per-case failures as signal to investigate,
    not as a build break.
  - Slow + costly. Each parametrized case is a real API round-trip.
  - Skipped if no API key.

Run: `pytest evals/ -v`
Aggregate-only: `pytest evals/ --tb=no -q` to see pass/fail counts cleanly.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from evals.conftest import get_tool_calls


pytestmark = [pytest.mark.asyncio, pytest.mark.eval]


# (user_input, expected_domain_tools_called, expected_scenario)
ROUTING_CASES = [
    pytest.param(
        "I want to create an event.",
        ["update_event_draft"],
        "missing_field",
        id="open-intent",
    ),
    pytest.param(
        "Kyoto Jazz Night on March 10, 2026 at 7pm",
        ["update_event_draft"],
        "missing_field",
        id="multi-field-extraction",
    ),
    pytest.param(
        "The organizer email is not-an-email",
        ["update_event_draft"],
        "invalid_input",
        id="invalid-field-value",
    ),
    pytest.param(
        "show me concerts in March 2026",
        ["query_events"],
        "lookup",
        id="structured-query",
    ),
    pytest.param(
        "find my jazz events in Kyoto",
        ["search_events"],
        "lookup",
        id="semantic-search",
    ),
    pytest.param(
        "hello!",
        [],
        "small_talk",
        id="greeting",
    ),
]


@pytest.mark.parametrize(
    "user_input, expected_tools, expected_scenario", ROUTING_CASES
)
async def test_routing(real_engine, user_input, expected_tools, expected_scenario):
    session_id = f"eval-{uuid4()}"
    result = await real_engine.handle(session_id, user_input)

    all_calls = await get_tool_calls(real_engine, session_id)
    domain_calls = [t for t in all_calls if t != "ChatResponse"]

    assert set(expected_tools).issubset(set(domain_calls)), (
        f"expected tools {expected_tools} not called; observed {domain_calls}"
    )
    assert result["response"].scenario == expected_scenario, (
        f"scenario={result['response'].scenario!r}, "
        f"message={result['response'].message!r}"
    )


async def test_update_previous_field_across_turns(real_engine):
    """Two-turn flow: set the date, then revise it. The revision turn should
    surface a `previous` value from the tool and route to
    `update_previous_field`."""
    session_id = f"eval-update-{uuid4()}"
    await real_engine.handle(
        session_id, "Kyoto Jazz Night on March 10, 2026"
    )
    r2 = await real_engine.handle(
        session_id, "actually, change the date to March 12, 2026"
    )

    assert r2["draft"].date.isoformat() == "2026-03-12"
    assert r2["response"].scenario == "update_previous_field"


async def test_save_requires_explicit_confirmation(real_engine):
    """`save_event` must only fire after the user confirms — not from the
    same turn where the user dumps all fields. After the dump turn the agent
    should be in `confirmation`, not `success_save`."""
    session_id = f"eval-confirm-{uuid4()}"
    dump = (
        "Create 'Kyoto Jazz Night' on 2026-03-10 at 19:00. "
        "Description: live jazz in Kyoto. "
        "Seats: VIP 10000, Regular 5000. "
        "Sales window 2026-01-01 to 2026-03-09, ticket limit 4. "
        "Venue: Kyoto Concert Hall, 123 Sakyo-ku Kyoto, capacity 1000. "
        "Organizer: Fenix Entertainment, info@fenix.co.jp. "
        "Category Concert, Japanese, not recurring, in person."
    )
    r1 = await real_engine.handle(session_id, dump)
    calls = await get_tool_calls(real_engine, session_id)

    assert "save_event" not in calls, "save_event must wait for explicit confirmation"
    assert r1["response"].scenario == "confirmation"
