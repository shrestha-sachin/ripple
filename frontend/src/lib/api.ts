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

// ---------------------------------------------------------------------------
// Score API types (Phase 5)
// ---------------------------------------------------------------------------

export interface CourseFragility {
  course_id: string;
  title: string;
  disruption_count: number;
  delay_count: number;
  delay_rate: number;
  blast_size: number;
}

export interface ScenarioResult {
  scenario_index: number;
  disruption_kind: string;
  disrupted_course: string;
  disruption_term: string | null;
  repair_status: string;
  graduation_delay: number;
  courses_moved: number;
  summer_terms_added: number;
  affected_course_count: number;
  solver_wall_time: number;
}

export interface RippleScoreResponse {
  student_id: string;
  score: number;
  scenario_count: number;
  on_time_count: number;
  infeasible_count: number;
  delay_probability: number;
  mean_courses_moved: number;
  mean_graduation_delay: number;
  course_fragility: CourseFragility[];
  scenarios: ScenarioResult[];
  rng_seed: number;
  total_wall_time: number;
}

export type ScoreResult =
  | { ok: true; data: RippleScoreResponse }
  | { ok: false; error: string };

/**
 * Compute the Ripple Score for a student via Monte-Carlo stress test.
 * Long timeout: 200 scenarios × solver overhead.
 */
export async function fetchScore(  studentId: string,
  timeoutMs = 60000
): Promise<ScoreResult> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(
      `${RIPPLE_API_BASE_URL}/score/${encodeURIComponent(studentId)}`,
      {
        signal: controller.signal,
        cache: "no-store",
        headers: { accept: "application/json" },
      }
    );

    if (!response.ok) {
      return { ok: false, error: `Backend returned HTTP ${response.status}` };
    }

    return { ok: true, data: (await response.json()) as RippleScoreResponse };
  } catch (error) {
    const message =
      error instanceof Error && error.name === "AbortError"
        ? `Stress test timed out after ${timeoutMs}ms`
        : error instanceof Error
          ? error.message
          : "Unknown error";
    return { ok: false, error: message };
  } finally {
    clearTimeout(timer);
  }
}

// ---------------------------------------------------------------------------
// Simulator API types (Phase 6)
// ---------------------------------------------------------------------------

export interface BlastRadiusResponse {
  student_id: string;
  course_id: string;
  course_title: string;
  blast_radius: string[];
  in_schedule: string[];
  blast_size: number;
  impact_count: number;
}

export type BlastRadiusResult =
  | { ok: true; data: BlastRadiusResponse }
  | { ok: false; error: string };

export interface RepairRequest {
  student_id: string;
  schedule: Record<string, string>;
  disruption: {
    kind: string;
    course_id: string;
    term?: string;
    description?: string;
  };
}

export interface RepairResponse {
  status: string;
  original_schedule: Record<string, string>;
  repaired_schedule: Record<string, string>;
  disruption_kind: string;
  disrupted_course: string;
  graduation_delay: number;
  courses_moved: number;
  summer_terms_added: number;
  solver_wall_time: number;
  message: string;
  affected_courses: string[];
  original_terms: TermPlan[];
  repaired_terms: TermPlan[];
}

export type SimulatorRepairResult =
  | { ok: true; data: RepairResponse }
  | { ok: false; error: string };

export async function fetchBlastRadius(
  studentId: string,
  courseId: string,
  timeoutMs = 15000
): Promise<BlastRadiusResult> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(
      `${RIPPLE_API_BASE_URL}/blast/${encodeURIComponent(studentId)}/${encodeURIComponent(courseId)}`,
      {
        signal: controller.signal,
        cache: "no-store",
        headers: { accept: "application/json" },
      }
    );
    if (!response.ok) {
      return { ok: false, error: `Backend returned HTTP ${response.status}` };
    }
    return { ok: true, data: (await response.json()) as BlastRadiusResponse };
  } catch (error) {
    const message =
      error instanceof Error && error.name === "AbortError"
        ? "Request timed out"
        : error instanceof Error
          ? error.message
          : "Unknown error";
    return { ok: false, error: message };
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchRepair(
  request: RepairRequest,
  timeoutMs = 10000
): Promise<SimulatorRepairResult> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${RIPPLE_API_BASE_URL}/repair`, {
      method: "POST",
      signal: controller.signal,
      cache: "no-store",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
      },
      body: JSON.stringify(request),
    });
    if (!response.ok) {
      return { ok: false, error: `Backend returned HTTP ${response.status}` };
    }
    return { ok: true, data: (await response.json()) as RepairResponse };
  } catch (error) {
    const message =
      error instanceof Error && error.name === "AbortError"
        ? "Repair solver timed out"
        : error instanceof Error
          ? error.message
          : "Unknown error";
    return { ok: false, error: message };
  } finally {
    clearTimeout(timer);
  }
}