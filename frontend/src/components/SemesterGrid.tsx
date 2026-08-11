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
}

function CourseCard({ course }: CourseCardProps) {
  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-3 shadow-sm transition-shadow hover:shadow-md">
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
    </div>
  );
}

interface TermColumnProps {
  termPlan: TermPlan;
  isGraduationTerm?: boolean;
}

function TermColumn({ termPlan, isGraduationTerm }: TermColumnProps) {
  return (
    <div
      className={`flex min-w-[200px] flex-col rounded-xl border-2 p-4 ${termColor(termPlan.term)}`}
    >
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-neutral-800">
          {formatTerm(termPlan.term)}
          {isGraduationTerm && (
            <span className="ml-2 text-xs font-normal text-emerald-600">
              🎓 Graduation
            </span>
          )}
        </h3>
        <span className="text-xs font-medium text-neutral-500">
          {termPlan.total_credits} credits
        </span>
      </div>
      <div className="flex flex-col gap-2">
        {termPlan.courses.map((course) => (
          <CourseCard key={course.course_id} course={course} />
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
}

export default function SemesterGrid({
  completedCourses,
  plannedTerms,
  graduationTerm,
  totalPlannedCredits,
}: SemesterGridProps) {
  const completedCredits = completedCourses.reduce((sum, c) => sum + c.credits, 0);

  return (
    <div className="flex flex-col gap-6">
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

      {/* Planned terms - horizontal scroll */}
      <div className="overflow-x-auto pb-4">
        <div className="flex gap-4">
          {plannedTerms.map((termPlan) => (
            <TermColumn
              key={termPlan.term}
              termPlan={termPlan}
              isGraduationTerm={termPlan.term === graduationTerm}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
