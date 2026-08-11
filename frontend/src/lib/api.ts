/**
 * Server-side API client for the Ripple backend.
 *
 * The backend base URL is only ever read on the server so the browser never
 * needs to know it and we avoid CORS entirely for the health check by routing
 * through /api/health. Solver endpoints in later phases go through the same
 * helper.
 */

export const RIPPLE_API_BASE_URL =
  process.env.RIPPLE_API_URL?.replace(/\/+$/, "") ?? "http://127.0.0.1:8000";

export interface HealthResponse {
  status: "ok" | "degraded";
  service: string;
  version: string;
  environment: string;
  git_sha: string;
  uptime_seconds: number;
  offline_mode: boolean;
  supabase_configured: boolean;
  solver_ready: boolean;
  solver_caps_seconds: {
    plan: number;
    repair: number;
    scenario: number;
  };
  dependencies: Record<string, string>;
}

export type HealthResult =
  | { ok: true; data: HealthResponse; latencyMs: number }
  | { ok: false; error: string; latencyMs: number };

/**
 * Fetch backend health. Never throws: a dead backend must render as a clear
 * UI state rather than a crashed page, since the live demo depends on it.
 */
export async function fetchHealth(timeoutMs = 8000): Promise<HealthResult> {
  const startedAt = Date.now();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${RIPPLE_API_BASE_URL}/health`, {
      signal: controller.signal,
      cache: "no-store",
      headers: { accept: "application/json" },
    });

    if (!response.ok) {
      return {
        ok: false,
        error: `Backend returned HTTP ${response.status}`,
        latencyMs: Date.now() - startedAt,
      };
    }

    return {
      ok: true,
      data: (await response.json()) as HealthResponse,
      latencyMs: Date.now() - startedAt,
    };
  } catch (error) {
    const message =
      error instanceof Error && error.name === "AbortError"
        ? `Backend did not respond within ${timeoutMs}ms`
        : error instanceof Error
          ? error.message
          : "Unknown error contacting backend";
    return { ok: false, error: message, latencyMs: Date.now() - startedAt };
  } finally {
    clearTimeout(timer);
  }
}
