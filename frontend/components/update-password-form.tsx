"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, LoaderCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { createClient } from "@/lib/supabase/client";

export function UpdatePasswordForm() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setLoading(true); setError(null);
    const { error: updateError } = await createClient().auth.updateUser({ password });
    setLoading(false);
    if (updateError) setError(updateError.message);
    else { router.replace("/dashboard/account"); router.refresh(); }
  }
  return <Card><CardHeader><CardTitle>Choose a new password</CardTitle><CardDescription>Use at least eight characters.</CardDescription></CardHeader><CardContent><form onSubmit={submit} className="space-y-4"><Input type="password" minLength={8} required autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} />{error && <div role="alert" className="flex gap-2 text-sm text-red-200"><AlertCircle className="h-4 w-4" />{error}</div>}<Button className="w-full" disabled={loading}>{loading && <LoaderCircle className="h-4 w-4 animate-spin" />}Update password</Button></form></CardContent></Card>;
}
