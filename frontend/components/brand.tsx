import Link from "next/link";
import { Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";

export function Brand({ compact = false, className }: { compact?: boolean; className?: string }) {
  return (
    <Link href="/" className={cn("inline-flex items-center gap-3", className)} aria-label="Howlix home">
      <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-violet-400/20 bg-violet-500/15 text-violet-300 shadow-glow">
        <Sparkles className="h-4 w-4" aria-hidden="true" />
      </span>
      {!compact && <span className="text-lg font-semibold tracking-[-0.03em] text-white">Howlix</span>}
    </Link>
  );
}

