from __future__ import annotations

import logging
from typing import Protocol

import chromadb
from chromadb.api.types import EmbeddingFunction
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

from app.models.event import EventRead

log = logging.getLogger(__name__)


def compose_event_summary(event: EventRead) -> str:
    """Build the natural-language summary that gets embedded.

    Captures the searchable surface: name, description, category, language,
    when, where, organizer. Kept as a single string so a single vector covers
    fuzzy queries across all fields.
    """
    parts = [event.name]
    if event.description:
        parts.append(event.description)
    parts.append(f"Category: {event.category}. Language: {event.language}.")
    parts.append(f"On {event.date} at {event.time}.")
    parts.append(f"Venue: {event.venue_name}, {event.venue_address}.")
    parts.append(f"Organized by {event.organizer_name}.")
    parts.append("Online event." if event.is_online else "Offline event.")
    return " ".join(parts)


class EventMemory:
    """Chroma-backed semantic recall for previously-saved events.

    Best-effort: index() swallows exceptions; search() returns event ids that
    callers should re-hydrate from the repository.
    """

    def __init__(
        self,
        persist_path: str,
        collection_name: str,
        embedding_function: EmbeddingFunction,
    ):
        self._client = chromadb.PersistentClient(path=persist_path)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding_function,
        )

    def index(self, event: EventRead, user_id: str = "default") -> None:
        try:
            self._collection.upsert(
                ids=[str(event.id)],
                documents=[compose_event_summary(event)],
                metadatas=[{
                    "event_id": event.id,
                    "name": event.name,
                    "date": event.date.isoformat(),
                    "category": event.category,
                    "venue_name": event.venue_name,
                    "user_id": user_id,
                    "created_at": event.created_at.isoformat(),
                }],
            )
        except Exception as exc:  # best-effort
            log.warning("chroma index failed for event_id=%s: %s", event.id, exc)

    def search(self, query: str, k: int = 3, user_id: str = "default") -> list[int]:
        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=k,
                where={"user_id": user_id},
            )
        except Exception as exc:
            log.warning("chroma search failed: %s", exc)
            return []
        metadatas = results.get("metadatas") or []
        if not metadatas or not metadatas[0]:
            return []
        return [int(m["event_id"]) for m in metadatas[0]]

    def delete(self, event_id: int) -> None:
        try:
            self._collection.delete(ids=[str(event_id)])
        except Exception as exc:
            log.warning("chroma delete failed for event_id=%s: %s", event_id, exc)


class _EmbeddingFunctionProtocol(Protocol):
    def __call__(self, input: list[str]) -> list[list[float]]: ...


def build_openai_embedding_function(api_key: str, model: str) -> EmbeddingFunction:
    return OpenAIEmbeddingFunction(api_key=api_key, model_name=model)
