import { fetchHealth, RIPPLE_API_BASE_URL } from "@/lib/api";

function StatusDot({ tone }: { tone: "ok" | "warn" | "bad" }) {
  const color =
    tone === "ok"
      ? "bg-emerald-500"
      : tone === "warn"
        ? "bg-amber-500"
        : "bg-rose-500";
  return (
    <span
      aria-hidden="true"
      className={`inline-block size-2 shrink-0 rounded-full ${color}`}
    />
  );
}

function Row({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "ok" | "warn" | "bad";
}) {
  // Never rely on colour alone: every row carries an explicit text value.
  return (
    <div className="flex items-center justify-between gap-6 border-b border-neutral-100 py-2.5 last:border-b-0">
      <dt className="text-sm text-neutral-500">{label}</dt>
      <dd className="flex items-center gap-2 text-sm font-medium text-neutral-900">
        <StatusDot tone={tone} />
        <span className="font-mono">{value}</span>
      </dd>
    </div>
  );
}

export default async function SystemStatus() {
  const result = await fetchHealth();

  return (
    <section
      aria-live="polite"
      className="w-full rounded-xl border border-neutral-200 bg-white p-6"
    >
      <header className="mb-4 flex items-baseline justify-between gap-4">
        <h2 className="text-sm font-semibold tracking-tight text-neutral-900">
          System status
        </h2>
        <p className="font-mono text-xs text-neutral-400">Phase 0</p>
      </header>

      {result.ok ? (
        <dl>
          <Row
            label="API reachable"
            value={`yes · ${result.latencyMs}ms`}
            tone="ok"
          />
          <Row
            label="CP-SAT solver"
            value={result.data.solver_ready ? "ready" : "unavailable"}
            tone={result.data.solver_ready ? "ok" : "bad"}
          />
          <Row
            label="OR-Tools"
            value={result.data.dependencies.ortools ?? "unknown"}
            tone={
              result.data.dependencies.ortools === "missing" ? "bad" : "ok"
            }
          />
          <Row
            label="Data source"
            value={
              result.data.offline_mode
                ? "offline fixture"
                : result.data.supabase_configured
                  ? "supabase"
                  : "not configured"
            }
            tone={result.data.supabase_configured || result.data.offline_mode ? "ok" : "warn"}
          />
          <Row
            label="Solve time caps"
            value={`plan ${result.data.solver_caps_seconds.plan}s · repair ${result.data.solver_caps_seconds.repair}s`}
            tone="ok"
          />
          <Row
            label="Environment"
            value={result.data.environment}
            tone="ok"
          />
        </dl>
      ) : (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-4">
          <p className="text-sm font-medium text-rose-900">
            Backend unreachable
          </p>
          <p className="mt-1 font-mono text-xs break-words text-rose-700">
            {result.error}
          </p>
          <p className="mt-3 text-xs text-rose-800">
            Expected the API at{" "}
            <code className="font-mono">{RIPPLE_API_BASE_URL}</code>. Start it
            with{" "}
            <code className="font-mono">
              uvicorn app.main:app --reload
            </code>{" "}
            from <code className="font-mono">backend/</code>.
          </p>
        </div>
      )}
    </section>
  );
}
