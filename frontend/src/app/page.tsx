import { Suspense } from "react";

import SystemStatus from "@/components/SystemStatus";

function StatusSkeleton() {
  return (
    <section className="w-full rounded-xl border border-neutral-200 bg-white p-6">
      <div className="mb-4 h-4 w-28 animate-pulse rounded bg-neutral-100" />
      <div className="space-y-3">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-4 animate-pulse rounded bg-neutral-100" />
        ))}
      </div>
      <p className="mt-4 text-xs text-neutral-400">Contacting solver…</p>
    </section>
  );
}

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center gap-10 px-6 py-20">
      <div>
        <p className="mb-3 font-mono text-xs tracking-widest text-neutral-400 uppercase">
          Ripple
        </p>
        <h1 className="text-4xl leading-tight font-semibold tracking-tight text-neutral-900">
          Degree plans that survive reality.
        </h1>
        <p className="mt-4 text-base leading-relaxed text-neutral-600">
          Every plan is one full section away from a lost semester. Ripple
          scores how fragile yours is — then reroutes it with the fewest
          possible changes when something breaks.
        </p>
      </div>

      <Suspense fallback={<StatusSkeleton />}>
        <SystemStatus />
      </Suspense>

      <p className="text-xs text-neutral-400">
        Demo data is synthetic. Ripple never ingests real student records.
      </p>
    </main>
  );
}
