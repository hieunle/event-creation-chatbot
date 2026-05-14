"""Conversation engine tests — drive the agent with a fake chat model that
emits scripted tool calls.

With LangChain's `create_agent` and a Pydantic `response_format`, the agent
wraps it in an AutoStrategy / ToolStrategy: the schema is exposed to the LLM
as a synthetic tool whose name is `schema.__name__` (here, `ChatResponse`).
When the LLM emits a tool_call to that tool, its args become the structured
response and the loop terminates.

Each test scripts the chat-model output: domain tool calls plus a final
`ChatResponse` tool call. We assert on the engine's externally-visible
behaviour (returned ChatResponse, persisted draft) — not on internal LangGraph
plumbing.
"""
from __future__ import annotations

from typing import Any, Sequence

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolCall
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver
from pydantic import PrivateAttr

from app.agent.engine import ConversationEngine


pytestmark = pytest.mark.asyncio


class ScriptedChatModel(BaseChatModel):
    """Pops one pre-baked AIMessage per `_generate` call."""

    _script: list[AIMessage] = PrivateAttr(default_factory=list)

    def __init__(self, script: Sequence[AIMessage]) -> None:
        super().__init__()
        self._script = list(script)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        if not self._script:
            raise RuntimeError("script exhausted")
        msg = self._script.pop(0)
        return ChatResult(generations=[ChatGeneration(message=msg)])

    async def _agenerate(self, *args: Any, **kwargs: Any) -> ChatResult:
        return self._generate(*args, **kwargs)


def _tool_call(name: str, args: dict, tc_id: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[ToolCall(name=name, args=args, id=tc_id)])


def _final_response(scenario: str, message: str, tc_id: str = "resp") -> AIMessage:
    """The final scripted message: a tool_call to the synthetic ChatResponse tool."""
    return AIMessage(
        content="",
        tool_calls=[ToolCall(
            name="ChatResponse",
            args={"role": "assistant", "scenario": scenario, "message": message},
            id=tc_id,
        )],
    )


def _make_engine(repository, memory, script: Sequence[AIMessage]) -> ConversationEngine:
    return ConversationEngine(
        ScriptedChatModel(script),
        repository,
        memory,
        MemorySaver(),
    )


class TestEngineFlow:
    async def test_missing_field_scenario(self, repository, memory):
        engine = _make_engine(repository, memory, script=[
            _tool_call("update_event_draft", {"draft": {}}, "tc1"),
            _final_response("missing_field", "Great! What's the name of your event?"),
        ])
        result = await engine.handle("sess-1", "I want to create an event.")
        assert result["response"].scenario == "missing_field"
        assert "name" in result["response"].message.lower()
        assert result["draft"].name is None

    async def test_field_set_and_missing_others(self, repository, memory):
        engine = _make_engine(repository, memory, script=[
            _tool_call("update_event_draft",
                       {"draft": {"name": "Kyoto Jazz Night"}}, "tc1"),
            _final_response("missing_field",
                            "Got it — 'Kyoto Jazz Night'. When is it?"),
        ])
        result = await engine.handle("sess-2", "Kyoto Jazz Night")
        assert result["draft"].name == "Kyoto Jazz Night"
        assert result["response"].scenario == "missing_field"

    async def test_update_previous_field_persists_revision(self, repository, memory):
        engine = _make_engine(repository, memory, script=[
            _tool_call("update_event_draft",
                       {"draft": {"name": "Kyoto Jazz Night",
                                  "date": "2026-10-10"}}, "tc1"),
            _final_response("missing_field", "Got it. What time?"),
            _tool_call("update_event_draft",
                       {"draft": {"date": "2026-10-12"}}, "tc2"),
            _final_response("update_previous_field",
                            "Updated the date to 2026-10-12. What time?"),
        ])
        await engine.handle("sess-3", "Kyoto Jazz Night on October 10")
        r2 = await engine.handle("sess-3", "actually, change the date to October 12")
        assert r2["draft"].date.isoformat() == "2026-10-12"
        assert r2["response"].scenario == "update_previous_field"

    async def test_success_save_scenario(self, repository, memory, sample_event_kwargs):
        from datetime import date, time

        draft_arg: dict[str, Any] = {}
        for k, v in sample_event_kwargs.items():
            if isinstance(v, (date, time)):
                draft_arg[k] = v.isoformat()
            elif k == "seat_types" and isinstance(v, dict):
                draft_arg[k] = [{"label": l, "price": p} for l, p in v.items()]
            else:
                draft_arg[k] = v

        engine = _make_engine(repository, memory, script=[
            _tool_call("update_event_draft", {"draft": draft_arg}, "tc1"),
            _final_response("confirmation",
                            "All fields filled. Shall I save this event?"),
            _tool_call("save_event", {}, "tc2"),
            _final_response("success_save", "Event saved successfully."),
        ])
        r1 = await engine.handle(
            "sess-4",
            "Create Kyoto Jazz Night with all the details.",
        )
        assert r1["response"].scenario == "confirmation"

        r2 = await engine.handle("sess-4", "Yes, please save.")
        assert r2["response"].scenario == "success_save"

        existing = await repository.find_duplicate(
            sample_event_kwargs["name"], sample_event_kwargs["date"]
        )
        assert existing is not None

    async def test_get_state_returns_draft_after_turn(self, repository, memory):
        engine = _make_engine(repository, memory, script=[
            _tool_call("update_event_draft",
                       {"draft": {"name": "Persisted"}}, "tc1"),
            _final_response("missing_field", "Got 'Persisted'. When?"),
        ])
        await engine.handle("sess-5", "Persisted")
        state = await engine.get_state("sess-5")
        assert state["draft"].name == "Persisted"
