"""Chat endpoints — WebSocket (live) + REST (request/response).

WS frames:
  client → server: {"message": "...user text..."}
  server → client: {"type": "turn", "response": ChatResponse, "draft": EventDraft}
                   {"type": "snapshot", "draft": ..., "messages": [...]}
                   {"type": "error", "message": "..."}

REST:
  POST /api/chat/{session_id}  body={"message": "..."}
  → {"response": ChatResponse, "draft": EventDraft}
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel

from app.agent.engine import ConversationEngine

log = logging.getLogger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    message: str


@router.post("/api/chat/{session_id}")
async def chat_rest(session_id: str, body: ChatRequest, request: Request) -> dict:
    engine: ConversationEngine = request.app.state.engine
    user_text = body.message.strip()
    if not user_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "error", "message": "message must not be empty"},
        )
    try:
        turn = await engine.handle(session_id, user_text)
    except Exception as exc:  # noqa: BLE001
        log.exception("chat engine error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "message": f"engine error: {exc}"},
        ) from exc
    return {
        "response": turn["response"].model_dump(),
        "draft": turn["draft"].model_dump(mode="json"),
    }


@router.websocket("/api/chat/{session_id}")
async def chat_ws(websocket: WebSocket, session_id: str) -> None:
    engine: ConversationEngine = websocket.app.state.engine
    await websocket.accept()
    # Push current state on connect so the UI can hydrate panels.
    try:
        initial = await engine.get_state(session_id)
        await websocket.send_json({
            "type": "snapshot",
            "draft": initial["draft"].model_dump(mode="json"),
            "messages": initial["messages"],
        })
    except Exception as e:  # noqa: BLE001
        log.warning("snapshot send failed: %s", e)

    try:
        while True:
            payload = await websocket.receive_json()
            user_text = (payload or {}).get("message", "").strip()
            if not user_text:
                continue
            try:
                turn = await engine.handle(session_id, user_text)
            except Exception as exc:  # noqa: BLE001
                log.exception("engine error")
                await websocket.send_json({
                    "type": "error",
                    "message": f"Internal error: {exc}",
                })
                continue
            await websocket.send_json({
                "type": "turn",
                "response": turn["response"].model_dump(),
                "draft": turn["draft"].model_dump(mode="json"),
            })
    except WebSocketDisconnect:
        return
