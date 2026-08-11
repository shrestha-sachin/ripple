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
// ---------------------------------------------------------------------------
// Plan API types
// ---------------------------------------------------------------------------

export interface StudentSummary {
  student_id: string;
  display_name: string;
  scenario: string;
  program: string;
  current_term: string;
  target_graduation_term: string;
  completed_credits: number;
  remaining_courses: number;
}

export interface ScheduledCourse {
  course_id: string;
  title: string;
  credits: number;
  term: string;
}

export interface TermPlan {
  term: string;
  courses: ScheduledCourse[];
  total_credits: number;
}

export interface PlanResponse {
  student_id: string;
  display_name: string;
  status: string;
  message: string;
  graduation_term: string | null;
  solver_wall_time: number;
  completed_courses: ScheduledCourse[];
  planned_terms: TermPlan[];
  total_planned_credits: number;
}

export type StudentsResult =
  | { ok: true; data: StudentSummary[] }
  | { ok: false; error: string };

export type PlanResult =
  | { ok: true; data: PlanResponse }
  | { ok: false; error: string };

/**
 * Fetch list of available students for planning.
 */
export async function fetchStudents(timeoutMs = 8000): Promise<StudentsResult> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${RIPPLE_API_BASE_URL}/students`, {
      signal: controller.signal,
      cache: "no-store",
      headers: { accept: "application/json" },
    });

    if (!response.ok) {
      return { ok: false, error: `Backend returned HTTP ${response.status}` };
    }

    return { ok: true, data: (await response.json()) as StudentSummary[] };
  } catch (error) {
    const message =
      error instanceof Error && error.name === "AbortError"
        ? `Request timed out after ${timeoutMs}ms`
        : error instanceof Error
          ? error.message
          : "Unknown error";
    return { ok: false, error: message };
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Generate a degree plan for a student.
 */
export async function fetchPlan(
  studentId: string,
  timeoutMs = 15000
): Promise<PlanResult> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(
      `${RIPPLE_API_BASE_URL}/plan/${encodeURIComponent(studentId)}`,
      {
        signal: controller.signal,
        cache: "no-store",
        headers: { accept: "application/json" },
      }
    );

    if (!response.ok) {
      return { ok: false, error: `Backend returned HTTP ${response.status}` };
    }

    return { ok: true, data: (await response.json()) as PlanResponse };
  } catch (error) {
    const message =
      error instanceof Error && error.name === "AbortError"
        ? `Solver timed out after ${timeoutMs}ms`
        : error instanceof Error
          ? error.message
          : "Unknown error";
    return { ok: false, error: message };
  } finally {
    clearTimeout(timer);
  }
}