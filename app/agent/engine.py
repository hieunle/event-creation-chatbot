"""Conversation engine — single entry point that wraps the LangChain agent."""
from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.responses import ChatResponse
from app.agent.state import SessionState
from app.agent.tools import build_tools
from app.models.event import EventDraft
from app.services.memory import EventMemory
from app.services.repository import EventRepository


class ConversationEngine:
    """Wraps the LangChain `create_agent` graph behind a single async method.

    The agent runs the ReAct tool loop, then emits a structured `ChatResponse`
    via response_format. SessionState (messages + draft) is checkpointed by
    the provided saver, keyed by `session_id` (thread_id).
    """

    def __init__(
        self,
        llm: BaseChatModel,
        repository: EventRepository,
        memory: EventMemory,
        checkpointer: BaseCheckpointSaver,
    ) -> None:
        self._repository = repository
        tools = build_tools(repository, memory)
        self._agent = create_agent(
            llm,
            tools=tools,
            system_prompt=SYSTEM_PROMPT,
            state_schema=SessionState,
            response_format=ChatResponse,
            checkpointer=checkpointer,
        )

    async def handle(self, session_id: str, user_text: str) -> dict[str, Any]:
        config = {"configurable": {"thread_id": session_id}}
        result = await self._agent.ainvoke(
            {"messages": [HumanMessage(content=user_text)]},
            config=config,
        )
        response: ChatResponse = result["structured_response"]
        draft: EventDraft = result.get("draft") or EventDraft()
        return {
            "response": response,
            "draft": draft,
        }

    async def get_state(self, session_id: str) -> dict[str, Any]:
        config = {"configurable": {"thread_id": session_id}}
        snapshot = await self._agent.aget_state(config)
        values = snapshot.values if snapshot else {}
        draft: EventDraft = values.get("draft") or EventDraft()
        messages = values.get("messages") or []
        return {
            "draft": draft,
            "messages": [_serialize_message(m) for m in messages],
        }


def _serialize_message(m: Any) -> dict[str, Any]:
    role_map = {"human": "user", "ai": "assistant", "tool": "tool", "system": "system"}
    return {
        "role": role_map.get(getattr(m, "type", "assistant"), "assistant"),
        "content": getattr(m, "content", ""),
    }
