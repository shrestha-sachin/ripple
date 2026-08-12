"use client";

import { useState, useEffect } from "react";
import {
  fetchStudents,
  fetchPlan,
  fetchScore,
  StudentSummary,
  PlanResponse,
  RippleScoreResponse,
} from "@/lib/api";
import StudentSelector from "./StudentSelector";
import SemesterGrid from "./SemesterGrid";
import RippleScoreDisplay from "./RippleScoreDisplay";
import DisruptionSimulator from "./DisruptionSimulator";

type LoadingState = "idle" | "loading-students" | "loading-plan" | "loading-score" | "error";
type ActiveTab = "plan" | "simulator" | "score";

export default function PlanPage() {
  const [students, setStudents] = useState<StudentSummary[]>([]);
  const [selectedStudentId, setSelectedStudentId] = useState<string | null>(null);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [score, setScore] = useState<RippleScoreResponse | null>(null);
  const [loadingState, setLoadingState] = useState<LoadingState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<ActiveTab>("plan");

  // Load students on mount.
  useEffect(() => {
    async function loadStudents() {
      setLoadingState("loading-students");
      setError(null);
      const result = await fetchStudents();
      if (result.ok) {
        setStudents(result.data);
        setLoadingState("idle");
      } else {
        setError(result.error);
        setLoadingState("error");
      }
    }
    loadStudents();
  }, []);

  // Load plan when student is selected.
  async function handleSelectStudent(studentId: string) {
    if (studentId === selectedStudentId) return;

    setSelectedStudentId(studentId);
    setPlan(null);
    setScore(null);
    setActiveTab("plan");
    setLoadingState("loading-plan");
    setError(null);

    const result = await fetchPlan(studentId);
    if (result.ok) {
      setPlan(result.data);
      setLoadingState("idle");
    } else {
      setError(result.error);
      setLoadingState("error");
    }
  }

  async function handleRunStressTest() {
    if (!selectedStudentId) return;
    setLoadingState("loading-score");
    setError(null);
    const result = await fetchScore(selectedStudentId);
    if (result.ok) {
      setScore(result.data);
      setLoadingState("idle");
    } else {
      setError(result.error);
      setLoadingState("error");
    }
  }

  const selectedStudent = students.find(
    (s) => s.student_id === selectedStudentId
  );

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-8">
        <p className="mb-2 font-mono text-xs uppercase tracking-widest text-neutral-400">
          Ripple
        </p>
        <h1 className="text-3xl font-bold tracking-tight text-neutral-900">
          Degree Planner
        </h1>
        <p className="mt-2 text-base text-neutral-600">
          Select a student persona to generate an optimized degree plan and resilience score.
        </p>
      </div>

      {/* Error state */}
      {error && (
        <div className="mb-6 rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-sm font-medium text-red-800">Error</p>
          <p className="mt-1 text-sm text-red-600">{error}</p>
        </div>
      )}

      {/* Student selector */}
      <section className="mb-8">
        <h2 className="mb-4 text-lg font-semibold text-neutral-800">
          Choose a Student
        </h2>
        <StudentSelector
          students={students}
          selectedId={selectedStudentId}
          onSelect={handleSelectStudent}
          loading={loadingState === "loading-students"}
        />
      </section>

      {/* Loading plan */}
      {loadingState === "loading-plan" && (
        <div className="mt-10 flex items-center gap-3 rounded-xl border border-neutral-200 bg-white p-6">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
          <p className="text-sm text-neutral-600">
            Generating optimal plan with CP-SAT solver…
          </p>
        </div>
      )}

      {/* Infeasible plan */}
      {plan && plan.status === "INFEASIBLE" && (
        <div className="mt-10 rounded-xl border border-red-200 bg-red-50 p-6">
          <p className="font-medium text-red-800">No feasible plan found</p>
          <p className="mt-1 text-sm text-red-600">{plan.message}</p>
        </div>
      )}

      {/* Main tabbed section — only when we have a feasible plan */}
      {plan && plan.status !== "INFEASIBLE" && loadingState !== "loading-plan" && (
        <section className="mt-10">
          {/* Tab bar */}
          <div className="mb-6 flex items-center gap-1 border-b border-neutral-200">
            {(
              [
                { id: "plan", label: "Degree Plan" },
                { id: "simulator", label: "Disruption Simulator" },
                { id: "score", label: "Ripple Score" },
              ] as { id: ActiveTab; label: string }[]
            ).map(({ id, label }) => (
              <button
                key={id}
                onClick={() => setActiveTab(id)}
                className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px ${
                  activeTab === id
                    ? "border-blue-500 text-blue-600"
                    : "border-transparent text-neutral-500 hover:text-neutral-700"
                }`}
              >
                {label}
              </button>
            ))}
            <div className="ml-auto text-xs text-neutral-400">
              {selectedStudent?.display_name} ·{" "}
              <span
                className={`font-medium ${
                  plan.status === "OPTIMAL"
                    ? "text-emerald-600"
                    : "text-amber-600"
                }`}
              >
                {plan.status}
              </span>{" "}
              · {(plan.solver_wall_time * 1000).toFixed(0)}ms
            </div>
          </div>

          {/* Plan tab */}
          {activeTab === "plan" && (
            <SemesterGrid
              completedCourses={plan.completed_courses}
              plannedTerms={plan.planned_terms}
              graduationTerm={plan.graduation_term}
              totalPlannedCredits={plan.total_planned_credits}
            />
          )}

          {/* Simulator tab */}
          {activeTab === "simulator" && (
            <DisruptionSimulator
              studentId={selectedStudentId!}
              completedCourses={plan.completed_courses}
              plannedTerms={plan.planned_terms}
              graduationTerm={plan.graduation_term}
              totalPlannedCredits={plan.total_planned_credits}
              baseSchedule={Object.fromEntries(
                plan.planned_terms.flatMap((t) =>
                  t.courses.map((c) => [c.course_id, t.term])
                )
              )}
            />
          )}

          {/* Score tab */}
          {activeTab === "score" && (
            <div>
              {!score && loadingState !== "loading-score" && (
                <div className="rounded-xl border-2 border-dashed border-neutral-200 p-10 text-center">
                  <p className="text-base font-medium text-neutral-600">
                    How fragile is this plan?
                  </p>
                  <p className="mt-2 text-sm text-neutral-400">
                    Run 200 seeded disruption scenarios through the CP-SAT repair solver to
                    get a 0–100 resilience score and course-level fragility ranking.
                  </p>
                  <button
                    onClick={handleRunStressTest}
                    className="mt-4 rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
                  >
                    Run stress test
                  </button>
                </div>
              )}

              {loadingState === "loading-score" && (
                <RippleScoreDisplay data={{} as RippleScoreResponse} loading />
              )}

              {score && loadingState !== "loading-score" && (
                <RippleScoreDisplay data={score} />
              )}
            </div>
          )}
        </section>
      )}

      {/* Footer */}
      <footer className="mt-12 border-t border-neutral-200 pt-6">
        <p className="text-xs text-neutral-400">
          Demo data is synthetic. Ripple never ingests real student records.
          The CP-SAT solver is the sole source of truth for plan feasibility.
        </p>
      </footer>
    </div>
  );
}
