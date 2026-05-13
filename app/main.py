"""FastAPI app entry point. Wires deep modules together in lifespan."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.agent.engine import ConversationEngine
from app.api.chat import router as chat_router
from app.api.events import router as events_router
from app.api.session import router as session_router
from app.config import get_settings
from app.services.db import build_engine, build_sessionmaker
from app.services.memory import EventMemory, build_openai_embedding_function
from app.services.repository import EventRepository

log = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    engine = build_engine(settings.database_url)
    sessionmaker = build_sessionmaker(engine)
    repository = EventRepository(sessionmaker)

    embedding_fn = build_openai_embedding_function(
        api_key=settings.openai_api_key,
        model=settings.openai_embedding_model,
    )
    memory = EventMemory(
        persist_path=settings.chroma_persist_path,
        collection_name=settings.chroma_collection,
        embedding_function=embedding_fn,
    )

    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )

    async with AsyncPostgresSaver.from_conn_string(
        settings.checkpoint_database_url
    ) as checkpointer:
        await checkpointer.setup()
        conversation = ConversationEngine(llm, repository, memory, checkpointer)

        app.state.repository = repository
        app.state.memory = memory
        app.state.engine = conversation
        app.state.sessionmaker = sessionmaker

        log.info("app ready")
        try:
            yield
        finally:
            await engine.dispose()


app = FastAPI(title="Event Creation Chatbot", lifespan=lifespan)

app.include_router(chat_router)
app.include_router(events_router)
app.include_router(session_router)


@app.get("/")
async def index() -> JSONResponse:
    # Primary UI is the Next.js app on :3000. The legacy plain-JS UI remains
    # available at /legacy for local fallback.
    return JSONResponse({
        "service": "event-creation-chatbot API",
        "ui": "http://localhost:3000",
        "legacy_ui": "/legacy",
        "docs": "/docs",
    })


@app.get("/legacy")
async def legacy() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
