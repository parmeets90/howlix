"use client";

import { useRouter } from "next/navigation";
import { LogOut, UserRound } from "lucide-react";

import { Button } from "@/components/ui/button";
import { createClient } from "@/lib/supabase/client";

export function AccountMenu() {
  const router = useRouter();
  async function logout() {
    await createClient().auth.signOut();
    router.replace("/auth/login");
    router.refresh();
  }
  return <div className="flex items-center gap-2"><Button asChild size="sm" variant="ghost"><a href="/dashboard/account"><UserRound className="h-4 w-4" /><span className="hidden sm:inline">Account</span></a></Button><Button size="icon" variant="ghost" aria-label="Sign out" onClick={() => void logout()}><LogOut className="h-4 w-4" /></Button></div>;
}
