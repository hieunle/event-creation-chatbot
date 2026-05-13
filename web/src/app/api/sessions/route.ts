import { NextRequest } from "next/server";

const PYTHON_BACKEND_URL = process.env.PYTHON_BACKEND_URL ?? "http://localhost:8000";

/** Proxy for Python's GET /api/sessions — used by the history drawer. */
export async function GET(req: NextRequest) {
  const limit = req.nextUrl.searchParams.get("limit") ?? "20";
  const upstream = await fetch(
    `${PYTHON_BACKEND_URL}/api/sessions?limit=${encodeURIComponent(limit)}`,
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
