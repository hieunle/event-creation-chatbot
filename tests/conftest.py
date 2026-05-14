"""Pytest fixtures.

DB tests use an aiosqlite in-memory database with SQLAlchemy's compatible
schema (JSONB is variant-aliased to JSON for sqlite in the model). Real
PostgreSQL features (the unique constraint, check constraints) are mirrored
in the SQLAlchemy `__table_args__`, so the integrity errors raise on sqlite
too. For full Postgres fidelity, point CONFTEST_DATABASE_URL at a real PG.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import date, time
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.event import Base, EventCreate
from app.services.memory import EventMemory
from app.services.repository import EventRepository


DB_URL = os.environ.get("CONFTEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")


@pytest_asyncio.fixture
async def async_engine():
    engine = create_async_engine(DB_URL, echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture
async def sessionmaker_(async_engine):
    return async_sessionmaker(async_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def repository(sessionmaker_) -> EventRepository:
    return EventRepository(sessionmaker_)


@pytest.fixture
def sample_event_kwargs() -> dict[str, Any]:
    return dict(
        name="Kyoto Jazz Night",
        date=date(2026, 10, 10),
        time=time(19, 0),
        description="A live jazz performance in Kyoto.",
        seat_types={"VIP": 10000, "Regular": 5000},
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
    )


@pytest.fixture
def sample_event(sample_event_kwargs) -> EventCreate:
    return EventCreate(**sample_event_kwargs)


from chromadb.api.types import Documents, EmbeddingFunction, Embeddings


class _FakeEmbeddingFunction(EmbeddingFunction[Documents]):
    """Deterministic, dependency-free embedding for Chroma tests.

    Maps each input to a sparse vector based on lowercased word hash. Good
    enough to make semantically-overlapping documents cluster. Implements
    the modern (non-legacy) ChromaDB EmbeddingFunction protocol.
    """

    DIM = 64

    def __init__(self) -> None:
        pass

    def __call__(self, input: Documents) -> Embeddings:
        import numpy as np

        vecs: list = []
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
def fake_embedding_fn():
    return _FakeEmbeddingFunction()


@pytest.fixture
def chroma_persist_path(tmp_path: Path) -> str:
    return str(tmp_path / "chroma_test")


@pytest.fixture
def memory(chroma_persist_path: str, fake_embedding_fn) -> EventMemory:
    return EventMemory(
        persist_path=chroma_persist_path,
        collection_name="events_test",
        embedding_function=fake_embedding_fn,
    )
