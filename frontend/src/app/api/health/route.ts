import { NextResponse } from "next/server";

import { fetchHealth } from "@/lib/api";

export const dynamic = "force-dynamic";

/**
 * Proxies the backend health check through the Next.js server.
 * Keeps the backend URL server-side and sidesteps CORS for this endpoint.
 */
export async function GET() {
  const result = await fetchHealth();

  if (!result.ok) {
    return NextResponse.json(
      { reachable: false, error: result.error, latencyMs: result.latencyMs },
      { status: 503 },
    );
  }

  return NextResponse.json({
    reachable: true,
    latencyMs: result.latencyMs,
    backend: result.data,
  });
}
