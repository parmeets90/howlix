"use client";

import { FormEvent, useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, ExternalLink, LoaderCircle, RotateCcw, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  cancelYouTubeImport,
  createYouTubeImport,
  listYouTubeImports,
  retryYouTubeImport,
  redispatchJob,
  type YouTubeImport,
} from "@/lib/api";
import { formatFileSize } from "@/lib/utils";


const ACTIVE = new Set(["queued", "processing", "retry"]);

export function YouTubeImporter({
  projectId,
  onImportChanged,
}: {
  projectId: string;
  onImportChanged?: () => void;
}) {
  const [url, setUrl] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [imports, setImports] = useState<YouTubeImport[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setImports(await listYouTubeImports(projectId));
    } catch {
      // The primary submit action surfaces API errors; background polling stays quiet.
    }
  }

  useEffect(() => {
    let cancelled = false;
    listYouTubeImports(projectId).then((values) => { if (!cancelled) setImports(values); }).catch(() => undefined);
    const timer = window.setInterval(() => {
      listYouTubeImports(projectId).then((values) => {
        if (!cancelled) {
          setImports(values);
          if (values.some((value) => value.status === "completed")) onImportChanged?.();
        }
      }).catch(() => undefined);
    }, 4000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [projectId, onImportChanged]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!confirmed) { setError("Confirm that you own this video or have permission to process it."); return; }
    setLoading(true);
    setError(null);
    try {
      await createYouTubeImport(projectId, { url: url.trim(), permission_confirmed: true });
      setUrl("");
      setConfirmed(false);
      await refresh();
      onImportChanged?.();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The YouTube import could not be queued. Use manual upload instead.");
    } finally {
      setLoading(false);
    }
  }

  async function action(importId: string, kind: "cancel" | "retry") {
    setError(null);
    try {
      await (kind === "cancel" ? cancelYouTubeImport(importId) : retryYouTubeImport(importId));
      await refresh();
      onImportChanged?.();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : `Could not ${kind} the import.`);
    }
  }

  async function retryRunner(jobId: string) {
    setError(null);
    try { await redispatchJob(jobId); await refresh(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "The processing runner could not be restarted."); }
  }

  return (
    <div className="space-y-5">
      <form onSubmit={submit} className="space-y-4">
        <label className="block">
          <span className="mb-2 block text-sm font-medium text-zinc-300">YouTube video URL</span>
          <Input
            type="url"
            inputMode="url"
            required
            maxLength={500}
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://www.youtube.com/watch?v=..."
            disabled={loading}
          />
          <span className="mt-2 block text-xs leading-5 text-zinc-600">Single public watch, Shorts, live, or youtu.be URL. Playlists and restricted videos are not supported.</span>
        </label>
        <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-white/[0.07] bg-black/15 p-4 text-sm leading-5 text-zinc-400">
          <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} className="mt-0.5 h-4 w-4 accent-violet-500" />
          <span>I own this video or have explicit permission to download and process it with Howlix.</span>
        </label>
        {error && <div role="alert" className="flex gap-2 rounded-xl border border-red-400/15 bg-red-400/[0.04] p-3 text-sm text-red-200"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" /><span>{error} You can use the video upload option instead.</span></div>}
        <Button type="submit" disabled={loading || !url.trim()} className="w-full sm:w-auto">
          {loading ? <><LoaderCircle className="h-4 w-4 animate-spin" /> Queuing import…</> : "Import permitted video"}
        </Button>
      </form>

      {imports.length > 0 && (
        <div className="space-y-3 border-t border-white/[0.06] pt-5">
          <p className="text-xs font-medium uppercase tracking-[0.14em] text-zinc-600">Import history</p>
          {imports.map((value) => {
            const active = ACTIVE.has(value.status);
            const completed = value.status === "completed";
            return (
              <div key={value.id} className="rounded-xl border border-white/[0.07] bg-black/15 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-zinc-200">{value.title ?? `YouTube ${value.video_id}`}</p>
                    <a href={value.canonical_url} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-xs text-zinc-600 hover:text-violet-300">View source <ExternalLink className="h-3 w-3" /></a>
                  </div>
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-violet-300/15 bg-violet-300/[0.06] px-2.5 py-1 text-xs capitalize text-violet-200">
                    {active ? <LoaderCircle className="h-3 w-3 animate-spin" /> : completed ? <CheckCircle2 className="h-3 w-3 text-emerald-300" /> : <AlertCircle className="h-3 w-3 text-red-300" />}
                    {value.status}
                  </span>
                </div>
                {active && <p className="mt-3 text-xs text-zinc-500">{value.job?.progress_stage?.replaceAll("_", " ") ?? "Waiting for worker"}{value.job?.progress_completed ? ` · ${formatFileSize(value.job.progress_completed)} received` : ""}</p>}
                {(value.error_message || value.job?.dispatch_error_message) && <p className="mt-3 text-xs leading-5 text-red-200">{value.error_message || value.job?.dispatch_error_message}</p>}
                <div className="mt-3 flex gap-2">
                  {active && <Button type="button" size="sm" variant="ghost" onClick={() => void action(value.id, "cancel")}><X className="h-3.5 w-3.5" /> Cancel</Button>}
                  {active && value.job?.dispatch_error_message && <Button type="button" size="sm" variant="secondary" onClick={() => void retryRunner(value.job!.id)}><RotateCcw className="h-3.5 w-3.5" /> Retry runner</Button>}
                  {(value.status === "failed" || value.status === "cancelled") && <Button type="button" size="sm" variant="secondary" onClick={() => void action(value.id, "retry")}><RotateCcw className="h-3.5 w-3.5" /> Retry</Button>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
