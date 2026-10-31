import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { Sidebar } from "@/components/sidebar";
import { TopNavigation } from "@/components/top-navigation";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Dashboard" };
export const dynamic = "force-dynamic";

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { data } = await (await createClient()).auth.getClaims();
  if (!data?.claims?.sub) redirect("/auth/login");
  return (
    <div className="flex min-h-screen bg-[#08070b]">
      <Sidebar />
      <div className="min-w-0 flex-1">
        <TopNavigation />
        {children}
      </div>
    </div>
  );
}

