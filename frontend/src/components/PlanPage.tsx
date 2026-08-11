"use client";

import { useState, useEffect } from "react";
import {
  fetchStudents,
  fetchPlan,
  StudentSummary,
  PlanResponse,
} from "@/lib/api";
import StudentSelector from "./StudentSelector";
import SemesterGrid from "./SemesterGrid";

type LoadingState = "idle" | "loading-students" | "loading-plan" | "error";

export default function PlanPage() {
  const [students, setStudents] = useState<StudentSummary[]>([]);
  const [selectedStudentId, setSelectedStudentId] = useState<string | null>(null);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [loadingState, setLoadingState] = useState<LoadingState>("idle");
  const [error, setError] = useState<string | null>(null);

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
          Select a student persona to generate an optimized degree plan.
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

      {/* Plan result */}
      {selectedStudentId && (
        <section className="mt-10">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-neutral-800">
                Degree Plan
                {selectedStudent && (
                  <span className="ml-2 text-base font-normal text-neutral-500">
                    for {selectedStudent.display_name}
                  </span>
                )}
              </h2>
              {plan && (
                <p className="mt-1 text-sm text-neutral-500">
                  Status:{" "}
                  <span
                    className={`font-medium ${
                      plan.status === "OPTIMAL" || plan.status === "FEASIBLE"
                        ? "text-emerald-600"
                        : plan.status === "INFEASIBLE"
                          ? "text-red-600"
                          : "text-amber-600"
                    }`}
                  >
                    {plan.status}
                  </span>
                  {" · "}
                  Solved in {(plan.solver_wall_time * 1000).toFixed(0)}ms
                </p>
              )}
            </div>
          </div>

          {loadingState === "loading-plan" && (
            <div className="flex items-center gap-3 rounded-xl border border-neutral-200 bg-white p-6">
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
              <p className="text-sm text-neutral-600">
                Generating optimal plan with CP-SAT solver...
              </p>
            </div>
          )}

          {plan && loadingState !== "loading-plan" && (
            <>
              {plan.status === "INFEASIBLE" ? (
                <div className="rounded-xl border border-red-200 bg-red-50 p-6">
                  <p className="font-medium text-red-800">
                    No feasible plan found
                  </p>
                  <p className="mt-1 text-sm text-red-600">{plan.message}</p>
                </div>
              ) : (
                <SemesterGrid
                  completedCourses={plan.completed_courses}
                  plannedTerms={plan.planned_terms}
                  graduationTerm={plan.graduation_term}
                  totalPlannedCredits={plan.total_planned_credits}
                />
              )}
            </>
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
