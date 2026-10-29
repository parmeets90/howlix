import type { Metadata } from "next";

import { Sidebar } from "@/components/sidebar";
import { TopNavigation } from "@/components/top-navigation";

export const metadata: Metadata = { title: "Dashboard" };

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
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

