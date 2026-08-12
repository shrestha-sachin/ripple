"use client";

import { RippleScoreResponse, CourseFragility } from "@/lib/api";

/**
 * Map a 0–100 score to a color class for the score ring.
 */
function scoreColor(score: number): { ring: string; text: string; label: string } {
  if (score >= 70) return { ring: "stroke-emerald-500", text: "text-emerald-600", label: "Resilient" };
  if (score >= 45) return { ring: "stroke-amber-500", text: "text-amber-600", label: "Moderate risk" };
  return { ring: "stroke-red-500", text: "text-red-600", label: "Fragile" };
}

function kindLabel(kind: string): string {
  switch (kind) {
    case "COURSE_FULL": return "Course full";
    case "NOT_OFFERED": return "Not offered";
    case "FAILED_COURSE": return "Failed course";
    case "TIME_CONFLICT": return "Time conflict";
    default: return kind;
  }
}

// ---------------------------------------------------------------------------
// Score ring (SVG gauge)
// ---------------------------------------------------------------------------

interface ScoreRingProps {
  score: number;
}

function ScoreRing({ score }: ScoreRingProps) {
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const progress = (score / 100) * circumference;
  const colors = scoreColor(score);

  return (
    <div className="flex flex-col items-center gap-1">
      <svg width="140" height="140" viewBox="0 0 140 140" className="-rotate-90">
        {/* Track */}
        <circle
          cx="70"
          cy="70"
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth="12"
          className="text-neutral-200"
        />
        {/* Progress */}
        <circle
          cx="70"
          cy="70"
          r={radius}
          fill="none"
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={`${progress} ${circumference}`}
          className={colors.ring}
        />
      </svg>
      {/* Score number overlaid */}
      <div className="-mt-[108px] flex flex-col items-center">
        <span className={`text-4xl font-bold tabular-nums ${colors.text}`}>
          {score}
        </span>
        <span className="text-xs text-neutral-400">/100</span>
      </div>
      <div className="mt-14">
        <span className={`text-sm font-medium ${colors.text}`}>{colors.label}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stat pills
// ---------------------------------------------------------------------------

interface StatPillProps {
  label: string;
  value: string;
  description?: string;
}

function StatPill({ label, value, description }: StatPillProps) {
  return (
    <div className="flex flex-col items-center gap-0.5 rounded-xl bg-neutral-50 border border-neutral-200 px-4 py-3 text-center">
      <span className="text-lg font-semibold text-neutral-900">{value}</span>
      <span className="text-xs font-medium text-neutral-500">{label}</span>
      {description && (
        <span className="text-xs text-neutral-400">{description}</span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Disruption distribution bar chart
// ---------------------------------------------------------------------------

interface DistributionProps {
  scenarios: RippleScoreResponse["scenarios"];
}

function DisruptionDistribution({ scenarios }: DistributionProps) {
  const kinds = ["COURSE_FULL", "NOT_OFFERED", "FAILED_COURSE", "TIME_CONFLICT"];
  const counts: Record<string, { total: number; delayed: number }> = {};
  for (const k of kinds) counts[k] = { total: 0, delayed: 0 };

  for (const s of scenarios) {
    if (counts[s.disruption_kind]) {
      counts[s.disruption_kind].total += 1;
      if (s.graduation_delay >= 1 || s.repair_status === "INFEASIBLE") {
        counts[s.disruption_kind].delayed += 1;
      }
    }
  }

  return (
    <div className="flex flex-col gap-2">
      {kinds.map((kind) => {
        const { total, delayed } = counts[kind];
        const delayRate = total > 0 ? delayed / total : 0;
        return (
          <div key={kind} className="flex items-center gap-3 text-sm">
            <span className="w-28 shrink-0 text-xs text-neutral-500">
              {kindLabel(kind)}
            </span>
            <div className="flex-1 overflow-hidden rounded-full bg-neutral-100 h-2">
              <div
                className="h-full rounded-full bg-red-400"
                style={{ width: `${delayRate * 100}%` }}
              />
            </div>
            <span className="w-10 text-right text-xs font-medium text-neutral-600">
              {Math.round(delayRate * 100)}%
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Fragility table
// ---------------------------------------------------------------------------

interface FragilityTableProps {
  courses: CourseFragility[];
}

function FragilityTable({ courses }: FragilityTableProps) {
  const top = courses.slice(0, 8);

  return (
    <div className="overflow-hidden rounded-xl border border-neutral-200">
      <table className="w-full text-sm">
        <thead className="bg-neutral-50 text-xs text-neutral-500">
          <tr>
            <th className="py-2 pl-4 pr-2 text-left font-medium">Course</th>
            <th className="py-2 px-2 text-left font-medium">Title</th>
            <th className="py-2 px-2 text-right font-medium">Blast radius</th>
            <th className="py-2 pl-2 pr-4 text-right font-medium">Delay rate</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-100">
          {top.map((course, i) => {
            const isHigh = course.delay_rate >= 0.8;
            const isMid = course.delay_rate >= 0.4 && !isHigh;
            return (
              <tr key={course.course_id} className="hover:bg-neutral-50">
                <td className="py-2 pl-4 pr-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-neutral-400">{i + 1}</span>
                    <span className="font-mono font-medium text-neutral-900">
                      {course.course_id}
                    </span>
                  </div>
                </td>
                <td className="py-2 px-2 text-neutral-600 text-xs max-w-[180px] truncate">
                  {course.title}
                </td>
                <td className="py-2 px-2 text-right text-neutral-500">
                  {course.blast_size}
                </td>
                <td className="py-2 pl-2 pr-4 text-right">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      isHigh
                        ? "bg-red-100 text-red-700"
                        : isMid
                          ? "bg-amber-100 text-amber-700"
                          : "bg-neutral-100 text-neutral-600"
                    }`}
                  >
                    {Math.round(course.delay_rate * 100)}%
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface RippleScoreDisplayProps {
  data: RippleScoreResponse;
  loading?: boolean;
}

export default function RippleScoreDisplay({
  data,
  loading,
}: RippleScoreDisplayProps) {
  if (loading) {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-neutral-200 bg-white p-6">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
        <div>
          <p className="text-sm font-medium text-neutral-700">
            Running stress test…
          </p>
          <p className="text-xs text-neutral-400">
            Simulating {200} disruption scenarios with the CP-SAT repair solver
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Top row: score ring + stats */}
      <div className="flex flex-wrap items-start gap-8">
        <div className="flex flex-col items-center">
          <ScoreRing score={data.score} />
          <p className="mt-1 text-center text-xs text-neutral-400">
            Ripple Score
          </p>
          <p className="text-center text-xs text-neutral-400">
            {data.scenario_count} scenarios · seed {data.rng_seed}
          </p>
        </div>

        <div className="flex flex-1 flex-col gap-4 pt-1">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatPill
              label="On-time repairs"
              value={`${data.on_time_count}/${data.scenario_count}`}
            />
            <StatPill
              label="P(delay ≥ 1 term)"
              value={`${Math.round(data.delay_probability * 100)}%`}
            />
            <StatPill
              label="Avg courses moved"
              value={data.mean_courses_moved.toFixed(1)}
            />
            <StatPill
              label="Avg delay"
              value={`${data.mean_graduation_delay.toFixed(1)} terms`}
            />
          </div>

          <div>
            <p className="mb-2 text-xs font-medium text-neutral-500">
              Delay rate by disruption kind
            </p>
            <DisruptionDistribution scenarios={data.scenarios} />
          </div>
        </div>
      </div>

      {/* Fragility table */}
      {data.course_fragility.length > 0 && (
        <div>
          <p className="mb-3 text-sm font-semibold text-neutral-800">
            Most Fragile Courses
            <span className="ml-2 text-xs font-normal text-neutral-400">
              ranked by % of disruptions that caused a graduation delay
            </span>
          </p>
          <FragilityTable courses={data.course_fragility} />
        </div>
      )}

      <p className="text-xs text-neutral-400">
        Computed in {data.total_wall_time.toFixed(2)}s ·{" "}
        {data.infeasible_count} scenarios had no feasible repair
      </p>
    </div>
  );
}
