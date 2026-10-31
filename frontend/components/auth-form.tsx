"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertCircle, LoaderCircle, MailCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { createClient } from "@/lib/supabase/client";

type Mode = "login" | "signup" | "forgot";

const copy = {
  login: ["Welcome back", "Sign in to your private Howlix workspace."],
  signup: ["Create your account", "Join the limited Howlix private beta."],
  forgot: ["Reset your password", "We will email you a secure recovery link."],
} as const;

export function AuthForm({ mode }: { mode: Mode }) {
  const router = useRouter();
  const search = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const visibleError = error ?? (
    search.get("error") ? "That authentication link is invalid or has expired. Request a new one." : null
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const supabase = createClient();
      if (mode === "login") {
        const { error: authError } = await supabase.auth.signInWithPassword({ email, password });
        if (authError) throw authError;
        const next = search.get("next");
        router.replace(next?.startsWith("/dashboard") ? next : "/dashboard");
        router.refresh();
      } else if (mode === "signup") {
        const { error: authError } = await supabase.auth.signUp({
          email,
          password,
          options: { emailRedirectTo: `${window.location.origin}/auth/callback` },
        });
        if (authError) throw authError;
        setMessage("Check your inbox to verify your email before signing in.");
      } else {
        const { error: authError } = await supabase.auth.resetPasswordForEmail(email, {
          redirectTo: `${window.location.origin}/auth/callback?next=/auth/update-password`,
        });
        if (authError) throw authError;
        setMessage("If that account exists, a recovery link is on its way.");
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Authentication could not be completed.");
    } finally {
      setLoading(false);
    }
  }

  async function signInWithGoogle() {
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const supabase = createClient();
      const { error: authError } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: `${window.location.origin}/auth/callback` },
      });
      if (authError) throw authError;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Google sign-in could not be started.");
      setLoading(false);
    }
  }

  return (
    <Card className="border-violet-400/15 bg-[#0e0b16]/95 shadow-2xl shadow-violet-950/20">
      <CardHeader><CardTitle className="text-2xl">{copy[mode][0]}</CardTitle><CardDescription>{copy[mode][1]}</CardDescription></CardHeader>
      <CardContent>
        {mode !== "forgot" && (
          <>
            <Button type="button" variant="outline" className="w-full" disabled={loading} onClick={signInWithGoogle}>
              Continue with Google
            </Button>
            <div className="my-4 flex items-center gap-3 text-[11px] uppercase tracking-[0.16em] text-zinc-600">
              <span className="h-px flex-1 bg-white/10" />or use email<span className="h-px flex-1 bg-white/10" />
            </div>
          </>
        )}
        {message ? <div className="flex gap-3 rounded-xl border border-emerald-400/15 bg-emerald-400/[0.05] p-4 text-sm text-emerald-200"><MailCheck className="h-5 w-5 shrink-0" />{message}</div> : (
          <form onSubmit={submit} className="space-y-4">
            <label className="block"><span className="mb-2 block text-sm text-zinc-300">Email</span><Input type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></label>
            {mode !== "forgot" && <label className="block"><span className="mb-2 block text-sm text-zinc-300">Password</span><Input type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={8} required value={password} onChange={(event) => setPassword(event.target.value)} /></label>}
            {visibleError && <div role="alert" className="flex gap-2 rounded-lg border border-red-400/15 bg-red-400/[0.04] p-3 text-sm text-red-200"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />{visibleError}</div>}
            <Button className="w-full" disabled={loading}>{loading && <LoaderCircle className="h-4 w-4 animate-spin" />}{mode === "login" ? "Sign in" : mode === "signup" ? "Create account" : "Send recovery link"}</Button>
          </form>
        )}
        <div className="mt-6 flex flex-wrap justify-between gap-3 text-xs text-zinc-500">
          {mode === "login" ? <><Link href="/auth/forgot-password" className="hover:text-violet-300">Forgot password?</Link><Link href="/auth/signup" className="hover:text-violet-300">Create account</Link></> : <Link href="/auth/login" className="hover:text-violet-300">Back to sign in</Link>}
        </div>
      </CardContent>
    </Card>
  );
}
