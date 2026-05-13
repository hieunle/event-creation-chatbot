import { NextRequest } from "next/server";

const PYTHON_BACKEND_URL = process.env.PYTHON_BACKEND_URL ?? "http://localhost:8000";

/** Proxy for Python's GET /api/session/{id}/state — used to rehydrate on load. */
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> },
) {
  const { sessionId } = await params;
  const upstream = await fetch(
    `${PYTHON_BACKEND_URL}/api/session/${encodeURIComponent(sessionId)}/state`,
    { cache: "no-store" },
  );
  if (!upstream.ok) {
    return Response.json(
      { status: "error", message: `backend ${upstream.status}` },
      { status: 502 },
    );
  }
  return Response.json(await upstream.json());
}
