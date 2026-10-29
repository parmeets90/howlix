"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutGrid, Plus, Settings } from "lucide-react";

import { Brand } from "@/components/brand";
import { cn } from "@/lib/utils";

const navigation = [
  { href: "/dashboard", label: "Projects", icon: LayoutGrid, exact: true },
  { href: "/dashboard/new", label: "New project", icon: Plus, exact: false },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="hidden w-64 shrink-0 border-r border-white/[0.07] bg-black/20 p-5 md:flex md:flex-col">
      <Brand className="px-2" />
      <nav className="mt-10 space-y-1" aria-label="Dashboard navigation">
        {navigation.map((item) => {
          const active = item.exact ? pathname === item.href : pathname.startsWith(item.href);
          return (
            <Link key={item.href} href={item.href} className={cn("flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition", active ? "bg-violet-500/10 text-violet-200" : "text-zinc-500 hover:bg-white/[0.04] hover:text-zinc-200")}>
              <item.icon className="h-4 w-4" /> {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto rounded-xl border border-white/[0.07] bg-white/[0.025] p-4">
        <div className="flex items-center gap-2 text-xs font-medium text-zinc-300"><Settings className="h-3.5 w-3.5" /> Local workspace</div>
        <p className="mt-2 text-xs leading-5 text-zinc-600">Single-user development mode. Authentication is not enabled.</p>
      </div>
      <p className="px-2 pt-5 text-[11px] text-zinc-700">Wolvesgang Digital</p>
    </aside>
  );
}

