"use client";

import { StudentSummary } from "@/lib/api";

/**
 * Parse a term code like "2026FA" into a readable label.
 */
function formatTerm(term: string): string {
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

interface StudentCardProps {
  student: StudentSummary;
  isSelected: boolean;
  onSelect: (studentId: string) => void;
}

function StudentCard({ student, isSelected, onSelect }: StudentCardProps) {
  return (
    <button
      onClick={() => onSelect(student.student_id)}
      className={`w-full rounded-xl border-2 p-4 text-left transition-all ${
        isSelected
          ? "border-blue-500 bg-blue-50 ring-2 ring-blue-200"
          : "border-neutral-200 bg-white hover:border-neutral-300 hover:shadow-md"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-semibold text-neutral-900">
          {student.display_name}
        </h3>
        {isSelected && (
          <span className="rounded-full bg-blue-500 px-2 py-0.5 text-xs font-medium text-white">
            Selected
          </span>
        )}
      </div>
      <p className="mt-1 text-sm text-neutral-600 line-clamp-2">
        {student.scenario}
      </p>
      <div className="mt-3 flex flex-wrap gap-2 text-xs text-neutral-500">
        <span className="rounded bg-neutral-100 px-2 py-1">
          {student.completed_credits} credits done
        </span>
        <span className="rounded bg-neutral-100 px-2 py-1">
          {student.remaining_courses} courses left
        </span>
        <span className="rounded bg-neutral-100 px-2 py-1">
          Target: {formatTerm(student.target_graduation_term)}
        </span>
      </div>
    </button>
  );
}

interface StudentSelectorProps {
  students: StudentSummary[];
  selectedId: string | null;
  onSelect: (studentId: string) => void;
  loading?: boolean;
}

export default function StudentSelector({
  students,
  selectedId,
  onSelect,
  loading,
}: StudentSelectorProps) {
  if (loading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="h-32 animate-pulse rounded-xl border-2 border-neutral-200 bg-neutral-100"
          />
        ))}
      </div>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {students.map((student) => (
        <StudentCard
          key={student.student_id}
          student={student}
          isSelected={selectedId === student.student_id}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}
