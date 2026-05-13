"""Eval-suite fixtures.

Evals hit a real LLM (default: ChatOpenAI with the app's configured model).
They are slow, cost money per run, and are inherently stochastic — treat
failures as signal, not as a hard gate. Run with `pytest evals/`.

Skipped automatically when no API key is set, so CI without secrets stays
green. The repository and ChromaDB memory used here are local/in-memory
clones of the production wiring — only the LLM is real.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.engine import ConversationEngine
from app.config import get_settings
from app.models.event import Base
from app.services.memory import EventMemory
from app.services.repository import EventRepository


pytestmark = pytest.mark.asyncio


def _api_key() -> str:
    return os.environ.get("OPENAI_API_KEY") or get_settings().openai_api_key


@pytest.fixture(scope="session", autouse=True)
def _require_api_key() -> None:
    if not _api_key():
        pytest.skip(
            "OPENAI_API_KEY not set — eval suite skipped. "
            "Export the key or set it in .env to run evals.",
            allow_module_level=True,
        )


@pytest_asyncio.fixture
async def async_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", echo=False, future=True
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture
async def repository(async_engine) -> EventRepository:
    sm = async_sessionmaker(async_engine, expire_on_commit=False)
    return EventRepository(sm)


class _FakeEmbeddingFunction(EmbeddingFunction[Documents]):
    """Cheap deterministic embedder. Routing evals don't exercise retrieval
    quality, so real OpenAI embeddings would just burn money."""

    DIM = 64

    def __init__(self) -> None:
        pass

    def __call__(self, input: Documents) -> Embeddings:
        import numpy as np

        vecs = []
        for text in input:
            v = [0.0] * self.DIM
            for word in text.lower().split():
                v[hash(word) % self.DIM] += 1.0
            norm = sum(x * x for x in v) ** 0.5 or 1.0
            vecs.append(np.array([x / norm for x in v], dtype=np.float32))
        return vecs

    @staticmethod
    def name() -> str:
        return "fake"

    def default_space(self) -> str:
        return "cosine"

    @staticmethod
    def build_from_config(config: dict) -> "_FakeEmbeddingFunction":
        return _FakeEmbeddingFunction()

    def get_config(self) -> dict:
        return {}

    @staticmethod
    def is_legacy() -> bool:
        return False


@pytest.fixture
def memory(tmp_path: Path) -> EventMemory:
    return EventMemory(
        persist_path=str(tmp_path / "chroma_eval"),
        collection_name="events_eval",
        embedding_function=_FakeEmbeddingFunction(),
    )


@pytest.fixture
def llm_model_name() -> str:
    # Override via EVAL_MODEL env var to A/B different models.
    return os.environ.get("EVAL_MODEL") or get_settings().openai_model


@pytest.fixture
def real_llm(llm_model_name: str) -> ChatOpenAI:
    return ChatOpenAI(
        model=llm_model_name,
        api_key=_api_key(),
        temperature=0,
    )


@pytest.fixture
def real_engine(real_llm, repository, memory) -> ConversationEngine:
    return ConversationEngine(real_llm, repository, memory, MemorySaver())


async def get_tool_calls(engine: ConversationEngine, session_id: str) -> list[str]:
    """Inspect the checkpointed agent state and pull every tool name that was
    invoked. Includes the synthetic `ChatResponse` tool — filter it out at
    call sites if you only care about domain tools."""
    config: dict[str, Any] = {"configurable": {"thread_id": session_id}}
    snapshot = await engine._agent.aget_state(config)
    if not snapshot:
        return []
    messages = snapshot.values.get("messages", []) or []
    names: list[str] = []
    for m in messages:
        for tc in getattr(m, "tool_calls", None) or []:
            name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
            if name:
                names.append(name)
    return names
