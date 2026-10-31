import { Brand } from "@/components/brand";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#08070b] px-5 py-12">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,#6d28d920,transparent_38%)]" />
      <div className="relative w-full max-w-md">
        <Brand className="mb-8" />
        {children}
        <p className="mt-8 text-center text-xs text-zinc-700">Private beta by Wolvesgang Digital</p>
      </div>
    </main>
  );
}
