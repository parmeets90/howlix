export default function DashboardLoading() {
  return (
    <main className="mx-auto max-w-6xl px-5 py-10 sm:px-8">
      <div className="h-8 w-48 animate-pulse rounded-lg bg-white/[0.06]" />
      <div className="mt-3 h-4 w-80 animate-pulse rounded bg-white/[0.04]" />
      <div className="mt-10 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {[0, 1, 2].map((item) => <div key={item} className="h-44 animate-pulse rounded-2xl border border-white/[0.06] bg-white/[0.025]" />)}
      </div>
    </main>
  );
}

