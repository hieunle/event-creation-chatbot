import { NextRequest } from "next/server";

import type { ChatTurnResult } from "@/lib/types";

const PYTHON_BACKEND_URL = process.env.PYTHON_BACKEND_URL ?? "http://localhost:8000";

/**
 * Chat proxy: forwards the latest user message to Python's POST /api/chat/{session_id}
 * and returns the Python response as JSON. The frontend reads it directly — we
 * don't wrap it in an AI SDK data stream because the backend is non-streaming
 * (one structured response per turn) and the client doesn't need token-level UI.
 */
export async function POST(req: NextRequest) {
  let body: { sessionId?: string; message?: string };
  try {
    body = await req.json();
  } catch {
    return Response.json(
      { status: "error", message: "invalid JSON body" },
      { status: 400 },
    );
  }
  const { sessionId, message } = body;
  if (!sessionId || !message) {
    return Response.json(
      { status: "error", message: "sessionId and message are required" },
      { status: 400 },
    );
  }

  let upstream: Response;
  try {
    upstream = await fetch(
      `${PYTHON_BACKEND_URL}/api/chat/${encodeURIComponent(sessionId)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      },
    );
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return Response.json(
      {
        status: "error",
        message: `cannot reach Python backend at ${PYTHON_BACKEND_URL}: ${msg}`,
      },
      { status: 502 },
    );
  }

  if (!upstream.ok) {
    const errText = await upstream.text().catch(() => "");
    return Response.json(
      {
        status: "error",
        message:
          `Python ${PYTHON_BACKEND_URL} returned ${upstream.status}.` +
          (upstream.status === 404
            ? " (Hint: restart uvicorn — the running process may predate POST /api/chat/{session_id}.)"
            : ` Body: ${errText.slice(0, 500)}`),
      },
      { status: 502 },
    );
  }

  const data = (await upstream.json()) as ChatTurnResult;
  return Response.json(data);
}
