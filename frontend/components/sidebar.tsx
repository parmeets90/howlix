"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutGrid, Plus, Settings } from "lucide-react";

import { Brand } from "@/components/brand";
import { cn } from "@/lib/utils";

const navigation = [
  { href: "/dashboard", label: "Projects", icon: LayoutGrid, exact: true },
  { href: "/dashboard/new", label: "New project", icon: Plus, exact: false },
  { href: "/dashboard/account", label: "Account & usage", icon: Settings, exact: false },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="sticky top-0 hidden h-screen w-[17rem] shrink-0 border-r border-white/[0.07] bg-black/25 p-5 backdrop-blur-xl md:flex md:flex-col">
      <Brand className="px-2" />
      <nav className="mt-11 space-y-1.5" aria-label="Dashboard navigation">
        {navigation.map((item) => {
          const active = item.exact ? pathname === item.href : pathname.startsWith(item.href);
          return (
            <Link key={item.href} href={item.href} className={cn("group flex items-center gap-3 rounded-xl border px-3.5 py-3 text-sm font-medium transition-all duration-200", active ? "border-violet-400/15 bg-gradient-to-r from-violet-500/15 to-violet-500/[0.04] text-violet-100 shadow-[inset_0_1px_0_rgba(255,255,255,.04)]" : "border-transparent text-zinc-500 hover:border-white/[0.06] hover:bg-white/[0.035] hover:text-zinc-200")}>
              <item.icon className={cn("h-4 w-4 transition-transform duration-200 group-hover:scale-110", active && "text-violet-300")} /> {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto rounded-2xl border border-white/[0.075] bg-gradient-to-br from-white/[0.045] to-transparent p-4 shadow-inner shadow-white/[0.015]">
        <div className="flex items-center gap-2 text-xs font-medium text-zinc-300"><Settings className="h-3.5 w-3.5" /> Private beta</div>
        <p className="mt-2 text-xs leading-5 text-zinc-600">Your private place for videos and clips.</p>
      </div>
      <p className="px-2 pt-5 text-[11px] text-zinc-700">Wolvesgang Digital</p>
    </aside>
  );
}

