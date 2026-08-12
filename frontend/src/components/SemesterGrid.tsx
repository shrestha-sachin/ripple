"use client";

import { TermPlan, ScheduledCourse } from "@/lib/api";

/**
 * Parse a term code like "2026FA" into a readable label like "Fall 2026".
 */
function formatTerm(term: string): string {
  if (term === "completed") return "Completed";
  const year = term.slice(0, 4);
  const season = term.slice(4);
  const seasonNames: Record<string, string> = {
    FA: "Fall",
    WI: "Winter",
    SP: "Spring",
    SU: "Summer",
  };
  return `${seasonNames[season] ?? season} ${year}`;
}

/**
 * Get a color class for a term based on the season.
 */
function termColor(term: string): string {
  const season = term.slice(4);
  switch (season) {
    case "FA":
      return "border-amber-200 bg-amber-50";
    case "WI":
      return "border-sky-200 bg-sky-50";
    case "SP":
      return "border-emerald-200 bg-emerald-50";
    case "SU":
      return "border-orange-200 bg-orange-50";
    default:
      return "border-neutral-200 bg-neutral-50";
  }
}

interface CourseCardProps {
  course: ScheduledCourse;
  highlight?: "disrupted" | "blast" | "moved" | "none";
  movedFromTerm?: string;
  onClick?: (courseId: string) => void;
  interactive?: boolean;
}

function CourseCard({ course, highlight = "none", movedFromTerm, onClick, interactive }: CourseCardProps) {
  const base = "rounded-lg border p-3 shadow-sm transition-all";
  const styleMap: Record<string, string> = {
    disrupted: "border-red-400 bg-red-50 ring-2 ring-red-300",
    blast: "border-amber-400 bg-amber-50 ring-1 ring-amber-200",
    moved: "border-blue-400 bg-blue-50 ring-2 ring-blue-200",
    none: "border-neutral-200 bg-white hover:shadow-md",
  };
  const clickable = interactive && onClick;

  return (
    <button
      type="button"
      disabled={!clickable}
      onClick={clickable ? () => onClick(course.course_id) : undefined}
      className={`w-full text-left ${base} ${styleMap[highlight]} ${
        clickable ? "cursor-pointer hover:scale-[1.02] active:scale-[0.98]" : "cursor-default"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="font-mono text-sm font-medium text-neutral-900">
          {course.course_id}
        </span>
        <span className="rounded-full bg-neutral-100 px-2 py-0.5 text-xs font-medium text-neutral-600">
          {course.credits} cr
        </span>
      </div>
      <p className="mt-1 text-xs leading-snug text-neutral-500 line-clamp-2">
        {course.title}
      </p>
      {highlight === "disrupted" && (
        <p className="mt-1 text-xs font-medium text-red-600">⚠ Disrupted</p>
      )}
      {highlight === "blast" && (
        <p className="mt-1 text-xs font-medium text-amber-600">↘ At risk</p>
      )}
      {highlight === "moved" && movedFromTerm && (
        <p className="mt-1 text-xs font-medium text-blue-600">
          ← moved from {formatTerm(movedFromTerm)}
        </p>
      )}
      {highlight === "moved" && !movedFromTerm && (
        <p className="mt-1 text-xs font-medium text-blue-600">↻ Rescheduled</p>
      )}
    </button>
  );
}

interface TermColumnProps {
  termPlan: TermPlan;
  isGraduationTerm?: boolean;
  disruptedCourse?: string | null;
  blastRadius?: Set<string>;
  movedCourses?: Record<string, string>; // course_id -> original term
  onCourseClick?: (courseId: string) => void;
  interactive?: boolean;
  isNew?: boolean; // term added by repair
}

function TermColumn({
  termPlan,
  isGraduationTerm,
  disruptedCourse,
  blastRadius,
  movedCourses,
  onCourseClick,
  interactive,
  isNew,
}: TermColumnProps) {
  const highlight = (courseId: string): CourseCardProps["highlight"] => {
    if (courseId === disruptedCourse) return "disrupted";
    if (movedCourses && courseId in movedCourses) return "moved";
    if (blastRadius?.has(courseId)) return "blast";
    return "none";
  };

  return (
    <div
      className={`flex min-w-[200px] flex-col rounded-xl border-2 p-4 transition-colors ${
        isNew ? "border-blue-300 bg-blue-50" : termColor(termPlan.term)
      }`}
    >
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-neutral-800">
          {formatTerm(termPlan.term)}
          {isGraduationTerm && (
            <span className="ml-2 text-xs font-normal text-emerald-600">
              🎓 Graduation
            </span>
          )}
          {isNew && (
            <span className="ml-2 text-xs font-normal text-blue-600">new</span>
          )}
        </h3>
        <span className="text-xs font-medium text-neutral-500">
          {termPlan.total_credits} credits
        </span>
      </div>
      <div className="flex flex-col gap-2">
        {termPlan.courses.map((course) => (
          <CourseCard
            key={course.course_id}
            course={course}
            highlight={highlight(course.course_id)}
            movedFromTerm={movedCourses?.[course.course_id]}
            onClick={onCourseClick}
            interactive={interactive}
          />
        ))}
      </div>
    </div>
  );
}

interface CompletedSectionProps {
  courses: ScheduledCourse[];
}

function CompletedSection({ courses }: CompletedSectionProps) {
  const totalCredits = courses.reduce((sum, c) => sum + c.credits, 0);

  return (
    <div className="rounded-xl border-2 border-neutral-300 bg-neutral-100 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-neutral-700">
          ✓ Completed Courses
        </h3>
        <span className="text-xs font-medium text-neutral-500">
          {totalCredits} credits
        </span>
      </div>
      <div className="flex flex-wrap gap-2">
        {courses.map((course) => (
          <span
            key={course.course_id}
            className="rounded-md border border-neutral-200 bg-white px-2 py-1 text-xs font-medium text-neutral-600"
            title={course.title}
          >
            {course.course_id}
          </span>
        ))}
      </div>
    </div>
  );
}

interface SemesterGridProps {
  completedCourses: ScheduledCourse[];
  plannedTerms: TermPlan[];
  graduationTerm: string | null;
  totalPlannedCredits: number;
  // Simulator props
  disruptedCourse?: string | null;
  blastRadius?: Set<string>;
  movedCourses?: Record<string, string>;
  newTerms?: Set<string>;
  onCourseClick?: (courseId: string) => void;
  interactive?: boolean;
  label?: string;
}

export default function SemesterGrid({
  completedCourses,
  plannedTerms,
  graduationTerm,
  totalPlannedCredits,
  disruptedCourse,
  blastRadius,
  movedCourses,
  newTerms,
  onCourseClick,
  interactive,
  label,
}: SemesterGridProps) {
  const completedCredits = completedCourses.reduce((sum, c) => sum + c.credits, 0);

  return (
    <div className="flex flex-col gap-6">
      {/* Label */}
      {label && (
        <p className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
          {label}
        </p>
      )}

      {/* Summary stats */}
      <div className="flex flex-wrap gap-4 text-sm">
        <div className="rounded-lg bg-neutral-100 px-4 py-2">
          <span className="text-neutral-500">Completed: </span>
          <span className="font-semibold text-neutral-800">
            {completedCredits} credits
          </span>
        </div>
        <div className="rounded-lg bg-neutral-100 px-4 py-2">
          <span className="text-neutral-500">Planned: </span>
          <span className="font-semibold text-neutral-800">
            {totalPlannedCredits} credits
          </span>
        </div>
        <div className="rounded-lg bg-neutral-100 px-4 py-2">
          <span className="text-neutral-500">Total: </span>
          <span className="font-semibold text-neutral-800">
            {completedCredits + totalPlannedCredits} credits
          </span>
        </div>
        {graduationTerm && (
          <div className="rounded-lg bg-emerald-100 px-4 py-2">
            <span className="text-emerald-700">🎓 </span>
            <span className="font-semibold text-emerald-800">
              {formatTerm(graduationTerm)}
            </span>
          </div>
        )}
      </div>

      {/* Completed courses */}
      {completedCourses.length > 0 && (
        <CompletedSection courses={completedCourses} />
      )}

      {/* Legend when in blast-radius mode */}
      {(disruptedCourse || (blastRadius && blastRadius.size > 0)) && (
        <div className="flex flex-wrap gap-3 text-xs">
          {disruptedCourse && (
            <span className="flex items-center gap-1.5 rounded-full bg-red-100 px-3 py-1 text-red-700">
              <span className="h-2 w-2 rounded-full bg-red-500" />
              Disrupted
            </span>
          )}
          {blastRadius && blastRadius.size > 0 && (
            <span className="flex items-center gap-1.5 rounded-full bg-amber-100 px-3 py-1 text-amber-700">
              <span className="h-2 w-2 rounded-full bg-amber-500" />
              At risk ({blastRadius.size} courses)
            </span>
          )}
          {movedCourses && Object.keys(movedCourses).length > 0 && (
            <span className="flex items-center gap-1.5 rounded-full bg-blue-100 px-3 py-1 text-blue-700">
              <span className="h-2 w-2 rounded-full bg-blue-500" />
              Rescheduled ({Object.keys(movedCourses).length} courses)
            </span>
          )}
        </div>
      )}

      {/* Planned terms - horizontal scroll */}
      <div className="overflow-x-auto pb-4">
        <div className="flex gap-4">
          {plannedTerms.map((termPlan) => (
            <TermColumn
              key={termPlan.term}
              termPlan={termPlan}
              isGraduationTerm={termPlan.term === graduationTerm}
              disruptedCourse={disruptedCourse}
              blastRadius={blastRadius}
              movedCourses={movedCourses}
              onCourseClick={onCourseClick}
              interactive={interactive}
              isNew={newTerms?.has(termPlan.term)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
