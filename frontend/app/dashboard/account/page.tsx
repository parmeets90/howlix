"use client";

import { useEffect, useState } from "react";
import { AlertCircle, Database, FolderKanban, Sparkles, Subtitles, Video } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getAccount, getUsage, type Account, type Usage } from "@/lib/api";
import { formatFileSize } from "@/lib/utils";

function Meter({ used, limit }: { used: number; limit: number }) {
  const percent = limit ? Math.min(100, (used / limit) * 100) : 100;
  return <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/[0.06]"><div className="h-full rounded-full bg-violet-400" style={{ width: `${percent}%` }} /></div>;
}

export default function AccountPage() {
  const [account, setAccount] = useState<Account | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    Promise.all([getAccount(), getUsage()]).then(([nextAccount, nextUsage]) => { setAccount(nextAccount); setUsage(nextUsage); }).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Usage could not be loaded."));
  }, []);
  const items = usage ? [
    [FolderKanban, "Projects", usage.projects_used, usage.projects_limit, `${usage.projects_used} of ${usage.projects_limit}`],
    [Database, "Video space", usage.stored_media_bytes, usage.stored_media_limit_bytes, `${formatFileSize(usage.stored_media_bytes)} of ${formatFileSize(usage.stored_media_limit_bytes)}`],
    [Subtitles, "Minutes turned into words", usage.transcription_seconds, usage.transcription_limit_seconds, `${Math.ceil(usage.transcription_seconds / 60)} of ${Math.floor(usage.transcription_limit_seconds / 60)} minutes`],
    [Sparkles, "AI analyses", usage.analysis_jobs, usage.analysis_jobs_limit, `${usage.analysis_jobs} of ${usage.analysis_jobs_limit}`],
    [Video, "Clips being made", usage.concurrent_renders, usage.concurrent_renders_limit, `${usage.concurrent_renders} of ${usage.concurrent_renders_limit}`],
  ] as const : [];
  return <main className="app-page mx-auto max-w-6xl px-5 py-8 sm:px-8 sm:py-10 lg:px-10"><div className="border-b border-white/[0.07] pb-8"><p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-violet-300">Account</p><h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-white">Private beta usage</h1><p className="mt-3 text-sm text-zinc-500">{account?.email ?? "Loading account…"}</p></div>{error && <div role="alert" className="mt-8 flex gap-2 text-sm text-red-200"><AlertCircle className="h-4 w-4" />{error}</div>}<div className="mt-8 grid auto-rows-fr gap-5 sm:grid-cols-2 xl:grid-cols-3">{items.map(([Icon, label, used, limit, text]) => <Card key={label} className="flex h-full min-h-44 flex-col transition-transform duration-300 hover:-translate-y-1"><CardHeader><div className="flex items-center gap-3"><span className="rounded-xl border border-violet-300/10 bg-violet-500/10 p-2.5 text-violet-300"><Icon className="h-4 w-4" /></span><div><CardTitle className="text-base">{label}</CardTitle><CardDescription>{text}</CardDescription></div></div></CardHeader><CardContent className="mt-auto"><Meter used={used} limit={limit} /></CardContent></Card>)}</div>{usage && <p className="mt-6 text-xs leading-5 text-zinc-600">Monthly counters reset from {new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(`${usage.period_start}T00:00:00Z`))}. Storage is a current reserved-byte total.</p>}</main>;
}
