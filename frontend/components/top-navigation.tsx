import Image from "next/image";
import Link from "next/link";
import { Plus } from "lucide-react";

import { Brand } from "@/components/brand";
import { Button } from "@/components/ui/button";

export function TopNavigation() {
  return (
    <header className="flex h-16 items-center justify-between border-b border-white/[0.07] px-5 sm:px-8">
      <Brand compact className="md:hidden" />
      <div className="hidden items-center gap-2.5 md:flex">
        <Image src="/brand/howlix-icon-64.png" alt="" width={64} height={64} className="h-6 w-6 object-contain" aria-hidden="true" />
        <p className="text-xs font-medium uppercase tracking-[0.15em] text-zinc-600">Howlix workspace</p>
      </div>
      <Button asChild size="sm">
        <Link href="/dashboard/new"><Plus className="h-4 w-4" /> New Project</Link>
      </Button>
    </header>
  );
}

