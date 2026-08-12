"use client";

import { useState } from "react";
import {
  fetchBlastRadius,
  fetchRepair,
  BlastRadiusResponse,
  RepairResponse,
  TermPlan,
  ScheduledCourse,
} from "@/lib/api";
import SemesterGrid from "./SemesterGrid";

const DISRUPTION_KINDS = [
  {
    kind: "COURSE_FULL",
    label: "Course full",
    description: "Section is at capacity — you can't register",
    icon: "🚫",
  },
  {
    kind: "NOT_OFFERED",
    label: "Not offered",
    description: "Department cancelled the course this term",
    icon: "📅",
  },
  {
    kind: "FAILED_COURSE",
    label: "Failed course",
    description: "You did not pass and must retake it",
    icon: "✗",
  },
  {
    kind: "TIME_CONFLICT",
    label: "Time conflict",
    description: "Schedule conflict blocks this course",
    icon: "⏱",
  },
];

function formatTerm(term: string): string {
  if (!term || term.length < 6) return term;
  const year = term.slice(0, 4);
  const season = term.slice(4);
  const names: Record<string, string> = { FA: "Fall", WI: "Winter", SP: "Spring", SU: "Summer" };
  return `${names[season] ?? season} ${year}`;
}

// ---------------------------------------------------------------------------
// Repair diff: compute which courses moved and which terms are new
// ---------------------------------------------------------------------------

function computeRepairDiff(
  original: Record<string, string>,
  repaired: Record<string, string>
): { movedCourses: Record<string, string>; newTerms: Set<string> } {
  const movedCourses: Record<string, string> = {};
  const origTermSet = new Set(Object.values(original));
  const newTerms = new Set<string>();

  for (const [courseId, newTerm] of Object.entries(repaired)) {
    const origTerm = original[courseId];
    if (origTerm && origTerm !== newTerm) {
      movedCourses[courseId] = origTerm; // value = where it came from
    }
  }

  for (const term of Object.values(repaired)) {
    if (!origTermSet.has(term)) {
      newTerms.add(term);
    }
  }

  return { movedCourses, newTerms };
}

// ---------------------------------------------------------------------------
// Disruption kind picker
// ---------------------------------------------------------------------------

interface KindPickerProps {
  selected: string;
  onSelect: (kind: string) => void;
}

function KindPicker({ selected, onSelect }: KindPickerProps) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {DISRUPTION_KINDS.map(({ kind, label, description, icon }) => (
        <button
          key={kind}
          onClick={() => onSelect(kind)}
          className={`rounded-xl border-2 p-3 text-left transition-all ${
            selected === kind
              ? "border-blue-500 bg-blue-50 ring-2 ring-blue-200"
              : "border-neutral-200 bg-white hover:border-neutral-300"
          }`}
        >
          <div className="mb-1 text-lg">{icon}</div>
          <div className="text-xs font-semibold text-neutral-800">{label}</div>
          <div className="mt-0.5 text-xs text-neutral-400 line-clamp-2">
            {description}
          </div>
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Repair summary banner
// ---------------------------------------------------------------------------

interface RepairSummaryProps {
  repair: RepairResponse;
}

function RepairSummary({ repair }: RepairSummaryProps) {
  const isGood =
    repair.status === "OPTIMAL" || repair.status === "FEASIBLE";
  const isInfeasible = repair.status === "INFEASIBLE";

  return (
    <div
      className={`rounded-xl border-2 p-4 ${
        isInfeasible
          ? "border-red-300 bg-red-50"
          : repair.graduation_delay === 0
            ? "border-emerald-300 bg-emerald-50"
            : "border-amber-300 bg-amber-50"
      }`}
    >
      <div className="flex flex-wrap items-center gap-4">
        <div>
          <p className="text-sm font-semibold text-neutral-800">
            {isInfeasible
              ? "No repair found"
              : repair.graduation_delay === 0
                ? "Graduation date preserved ✓"
                : `Graduation delayed ${repair.graduation_delay} term${repair.graduation_delay !== 1 ? "s" : ""}`}
          </p>
          <p className="mt-0.5 text-xs text-neutral-500">{repair.message}</p>
        </div>
        {!isInfeasible && (
          <div className="flex flex-wrap gap-3 text-xs">
            <span className="rounded-full bg-white border border-neutral-200 px-2 py-1">
              {repair.courses_moved} courses moved
            </span>
            <span className="rounded-full bg-white border border-neutral-200 px-2 py-1">
              {repair.summer_terms_added} summer terms added
            </span>
            <span className="rounded-full bg-white border border-neutral-200 px-2 py-1">
              Solved in {(repair.solver_wall_time * 1000).toFixed(0)}ms
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface DisruptionSimulatorProps {
  studentId: string;
  completedCourses: ScheduledCourse[];
  plannedTerms: TermPlan[];
  graduationTerm: string | null;
  totalPlannedCredits: number;
  /** Flat map of course_id -> term from the base plan */
  baseSchedule: Record<string, string>;
}

type SimState = "idle" | "loading-blast" | "ready" | "loading-repair" | "repaired";

export default function DisruptionSimulator({
  studentId,
  completedCourses,
  plannedTerms,
  graduationTerm,
  totalPlannedCredits,
  baseSchedule,
}: DisruptionSimulatorProps) {
  const [simState, setSimState] = useState<SimState>("idle");
  const [selectedCourse, setSelectedCourse] = useState<string | null>(null);
  const [selectedKind, setSelectedKind] = useState<string>("COURSE_FULL");
  const [blastData, setBlastData] = useState<BlastRadiusResponse | null>(null);
  const [repairData, setRepairData] = useState<RepairResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleCourseClick(courseId: string) {
    if (simState === "loading-blast" || simState === "loading-repair") return;
    if (selectedCourse === courseId) {
      // Deselect
      setSelectedCourse(null);
      setBlastData(null);
      setRepairData(null);
      setSimState("idle");
      return;
    }

    setSelectedCourse(courseId);
    setRepairData(null);
    setSimState("loading-blast");
    setError(null);

    const result = await fetchBlastRadius(studentId, courseId);
    if (result.ok) {
      setBlastData(result.data);
      setSimState("ready");
    } else {
      setError(result.error);
      setSimState("idle");
    }
  }

  async function handleSimulate() {
    if (!selectedCourse || simState === "loading-repair") return;

    setSimState("loading-repair");
    setRepairData(null);
    setError(null);

    const term = baseSchedule[selectedCourse];
    const result = await fetchRepair({
      student_id: studentId,
      schedule: baseSchedule,
      disruption: {
        kind: selectedKind,
        course_id: selectedCourse,
        term: selectedKind === "FAILED_COURSE" ? undefined : term,
        description: `Simulated ${selectedKind.toLowerCase().replace("_", " ")} for ${selectedCourse}`,
      },
    });

    if (result.ok) {
      setRepairData(result.data);
      setSimState("repaired");
    } else {
      setError(result.error);
      setSimState("ready");
    }
  }

  function handleReset() {
    setSelectedCourse(null);
    setBlastData(null);
    setRepairData(null);
    setSimState("idle");
    setError(null);
  }

  // Build highlighted sets for the original plan.
  const blastSet = blastData
    ? new Set(blastData.in_schedule)
    : new Set<string>();

  // For the repaired plan, compute which courses moved.
  const repairDiff =
    repairData?.status !== "INFEASIBLE" && repairData
      ? computeRepairDiff(repairData.original_schedule, repairData.repaired_schedule)
      : null;

  const isInteractive = simState !== "loading-repair";

  return (
    <div className="flex flex-col gap-6">
      {/* Instruction banner */}
      {simState === "idle" && (
        <div className="rounded-xl border-2 border-dashed border-blue-200 bg-blue-50 p-4">
          <p className="text-sm font-medium text-blue-800">
            Disruption Simulator
          </p>
          <p className="mt-1 text-xs text-blue-600">
            Click any course card below to select it as the disrupted course. The
            blast radius — courses that depend on it — will be highlighted in amber.
          </p>
        </div>
      )}

      {/* Blast radius loading */}
      {simState === "loading-blast" && (
        <div className="flex items-center gap-2 text-sm text-neutral-500">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
          Computing blast radius…
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Controls: show when a course is selected */}
      {(simState === "ready" || simState === "loading-repair" || simState === "repaired") && blastData && (
        <div className="rounded-xl border border-neutral-200 bg-white p-4 shadow-sm">
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-neutral-800">
                Disrupting{" "}
                <span className="font-mono text-red-600">{selectedCourse}</span>
                {" "}in{" "}
                <span className="text-neutral-600">
                  {formatTerm(baseSchedule[selectedCourse!] ?? "")}
                </span>
              </p>
              <p className="mt-0.5 text-xs text-neutral-500">
                {blastData.impact_count} downstream courses at risk ·{" "}
                {blastData.blast_size} total in catalog
              </p>
            </div>
            <button
              onClick={handleReset}
              className="rounded-lg border border-neutral-200 px-3 py-1.5 text-xs text-neutral-500 hover:border-neutral-300 hover:bg-neutral-50"
            >
              Reset
            </button>
          </div>

          <div className="mb-4">
            <p className="mb-2 text-xs font-medium text-neutral-600">
              Disruption type
            </p>
            <KindPicker selected={selectedKind} onSelect={setSelectedKind} />
          </div>

          <button
            onClick={handleSimulate}
            disabled={simState === "loading-repair"}
            className="w-full rounded-lg bg-red-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-red-700 disabled:opacity-50"
          >
            {simState === "loading-repair" ? (
              <span className="flex items-center justify-center gap-2">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                Repairing with CP-SAT…
              </span>
            ) : (
              "Simulate disruption + repair"
            )}
          </button>
        </div>
      )}

      {/* Repair summary */}
      {repairData && simState === "repaired" && (
        <RepairSummary repair={repairData} />
      )}

      {/* Original plan — always shown, highlighted when course selected */}
      <div>
        {simState !== "idle" && (
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-neutral-400">
            {simState === "repaired" ? "Original plan" : "Your plan"}
          </p>
        )}
        <SemesterGrid
          completedCourses={completedCourses}
          plannedTerms={plannedTerms}
          graduationTerm={graduationTerm}
          totalPlannedCredits={totalPlannedCredits}
          disruptedCourse={selectedCourse}
          blastRadius={blastSet}
          onCourseClick={handleCourseClick}
          interactive={isInteractive}
        />
      </div>

      {/* Repaired plan */}
      {repairData && simState === "repaired" && repairData.status !== "INFEASIBLE" && (
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-neutral-400">
            Repaired plan
          </p>
          <SemesterGrid
            completedCourses={completedCourses}
            plannedTerms={repairData.repaired_terms}
            graduationTerm={
              repairData.graduation_delay === 0
                ? graduationTerm
                : repairData.repaired_terms.at(-1)?.term ?? null
            }
            totalPlannedCredits={repairData.repaired_terms.reduce(
              (s, t) => s + t.total_credits,
              0
            )}
            disruptedCourse={selectedCourse}
            movedCourses={repairDiff?.movedCourses}
            newTerms={repairDiff?.newTerms}
          />
        </div>
      )}
    </div>
  );
}
