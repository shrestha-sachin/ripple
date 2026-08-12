"use client";

import { FormEvent, useMemo, useState } from "react";
import { importTranscript } from "@/lib/api";

interface TranscriptUploaderProps {
  onImported: (studentId: string) => Promise<void> | void;
  onRefreshStudents: () => Promise<void> | void;
}

export default function TranscriptUploader({
  onImported,
  onRefreshStudents,
}: TranscriptUploaderProps) {
  const [file, setFile] = useState<File | null>(null);
  const [studentId, setStudentId] = useState("real-student");
  const [displayName, setDisplayName] = useState("Real Student");
  const [program, setProgram] = useState("");
  const [currentTerm, setCurrentTerm] = useState("2026FA");
  const [targetTerm, setTargetTerm] = useState("2029SP");
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const disabled = useMemo(() => uploading || !file, [uploading, file]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;

    setUploading(true);
    setMessage(null);
    setError(null);

    const result = await importTranscript(file, {
      studentId,
      displayName,
      program,
      currentTerm,
      targetGraduationTerm: targetTerm,
    });

    if (!result.ok) {
      setError(result.error);
      setUploading(false);
      return;
    }

    const warningLine =
      result.data.unrecognized_course_ids.length > 0
        ? ` Unrecognized courses: ${result.data.unrecognized_course_ids.join(", ")}.`
        : "";
    setMessage(
      `Extracted ${result.data.extracted_course_ids.length} transcript courses for ${result.data.display_name}. ` +
        `Recognized ${result.data.recognized_course_ids.length}, remaining degree courses: ${result.data.remaining_courses}.` +
        warningLine
    );
    await onRefreshStudents();
    await onImported(result.data.student_id);
    setUploading(false);
  }

  return (
    <section className="mb-8 rounded-xl border border-neutral-200 bg-white p-5">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-neutral-900">Upload Transcript</h2>
        <p className="mt-1 text-sm text-neutral-600">
          Upload JSON, CSV, TXT, or PDF transcript. Ripple scrubs student identity and course history, then computes taken and remaining courses for planning and resilience analysis.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="grid gap-3 md:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm text-neutral-700">
          Transcript file
          <input
            type="file"
            accept=".json,.csv,.txt,.pdf,text/plain,application/json,text/csv,application/pdf"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="rounded-lg border border-neutral-300 px-3 py-2 text-sm"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm text-neutral-700">
          Student ID
          <input
            value={studentId}
            onChange={(e) => setStudentId(e.target.value)}
            className="rounded-lg border border-neutral-300 px-3 py-2 text-sm"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm text-neutral-700">
          Display name
          <input
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className="rounded-lg border border-neutral-300 px-3 py-2 text-sm"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm text-neutral-700">
          Program (optional)
          <input
            value={program}
            onChange={(e) => setProgram(e.target.value)}
            placeholder="Leave blank to use catalog default"
            className="rounded-lg border border-neutral-300 px-3 py-2 text-sm"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm text-neutral-700">
          Current term
          <input
            value={currentTerm}
            onChange={(e) => setCurrentTerm(e.target.value)}
            placeholder="2026FA"
            className="rounded-lg border border-neutral-300 px-3 py-2 text-sm"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm text-neutral-700">
          Target graduation term
          <input
            value={targetTerm}
            onChange={(e) => setTargetTerm(e.target.value)}
            placeholder="2029SP"
            className="rounded-lg border border-neutral-300 px-3 py-2 text-sm"
          />
        </label>

        <div className="md:col-span-2 flex items-center gap-3">
          <button
            type="submit"
            disabled={disabled}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50 hover:bg-emerald-700"
          >
            {uploading ? "Importing..." : "Import Transcript"}
          </button>
          <span className="text-xs text-neutral-500">
            Supported formats: .json, .csv, .txt, .pdf
          </span>
        </div>
      </form>

      {message && (
        <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          {message}
        </div>
      )}
      {!error && !uploading && message && (
        <p className="mt-2 text-xs text-neutral-500">
          If many courses are unrecognized, switch to the matching catalog (for example UWGB) before uploading.
        </p>
      )}
      {error && (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}
    </section>
  );
}
