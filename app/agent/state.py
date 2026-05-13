from __future__ import annotations

from langchain.agents.middleware.types import AgentState
from typing_extensions import NotRequired

from app.agent.responses import ChatResponse
from app.models.event import EventDraft


class SessionState(AgentState[ChatResponse]):
    """Per-session graph state. Extends LangChain's AgentState (which provides
    `messages`, `jump_to`, `structured_response`) with the event draft."""

    draft: NotRequired[EventDraft]
