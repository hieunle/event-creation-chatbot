import { NextRequest } from "next/server";

const PYTHON_BACKEND_URL = process.env.PYTHON_BACKEND_URL ?? "http://localhost:8000";

/** Proxy for Python's GET /api/events — used by the Events tab. */
export async function GET(req: NextRequest) {
  const limit = req.nextUrl.searchParams.get("limit") ?? "50";
  const upstream = await fetch(
    `${PYTHON_BACKEND_URL}/api/events?limit=${encodeURIComponent(limit)}`,
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
