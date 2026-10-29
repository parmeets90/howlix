"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, FileText, LoaderCircle, RefreshCw, Search, Sparkles } from "lucide-react";

import { Button } from "./ui/button";
import { Input } from "./ui/input";
import {
  getTranscript,
  getTranscriptionStatus,
  requestTranscription,
  type Transcript,
  type TranscriptionStatus,
} from "../lib/api";
import { filterTranscriptSegments } from "../lib/transcript";


function timestamp(milliseconds: number): string {
  const seconds = Math.floor(milliseconds / 1000);
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

function progressLabel(status: TranscriptionStatus): string {
  const job = status.job;
  if (!job) return "Preparing transcription";
  const stage = job.progress_stage?.replaceAll("_", " ") ?? job.status;
  if (job.progress_completed !== null && job.progress_total !== null) {
    return `${stage} · ${job.progress_completed} of ${job.progress_total}`;
  }
  return stage;
}

export function TranscriptViewer({ assetId, videoElementId }: { assetId: string; videoElementId: string }) {
  const [status, setStatus] = useState<TranscriptionStatus | null>(null);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const nextStatus = await getTranscriptionStatus(assetId);
      setStatus(nextStatus);
      if (nextStatus.transcript_status === "completed") {
        setTranscript(await getTranscript(assetId));
      }
      setError(null);
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : "Transcription status could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [assetId]);

  useEffect(() => {
    const timeout = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timeout);
  }, [refresh]);

  useEffect(() => {
    if (!status || !["queued", "processing", "retry"].includes(status.transcript_status ?? "")) return;
    const interval = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(interval);
  }, [refresh, status]);

  const visibleSegments = useMemo(
    () => filterTranscriptSegments(transcript?.segments ?? [], query),
    [query, transcript],
  );

  async function start() {
    setSubmitting(true);
    setError(null);
    try {
      setStatus(await requestTranscription(assetId));
      setTranscript(null);
    } catch (startError) {
      setError(startError instanceof Error ? startError.message : "Transcription could not be started.");
    } finally {
      setSubmitting(false);
    }
  }

  function seek(startMs: number) {
    const video = document.getElementById(videoElementId) as HTMLVideoElement | null;
    if (!video) return;
    video.currentTime = startMs / 1000;
    void video.play().catch(() => undefined);
  }

  if (loading) {
    return <div className="mt-6 flex items-center gap-2 text-xs text-zinc-500"><LoaderCircle className="h-3.5 w-3.5 animate-spin" /> Loading transcript status</div>;
  }

  const active = status && ["queued", "processing", "retry"].includes(status.transcript_status ?? "");
  const failed = status?.transcript_status === "failed";

  return (
    <div className="mt-6 border-t border-white/[0.06] pt-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-sm font-medium text-zinc-200"><FileText className="h-4 w-4 text-violet-300" /> Transcript</p>
          <p className="mt-1 text-xs text-zinc-600">Original language with segment and word timestamps.</p>
        </div>
        {!transcript && !active && (
          <Button type="button" size="sm" variant={failed ? "secondary" : "default"} onClick={() => void start()} disabled={submitting}>
            {submitting ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : failed ? <RefreshCw className="h-3.5 w-3.5" /> : <Sparkles className="h-3.5 w-3.5" />}
            {failed ? "Retry transcription" : "Transcribe video"}
          </Button>
        )}
      </div>

      {active && status && (
        <div className="mt-4 flex items-center gap-2 rounded-lg border border-violet-300/10 bg-violet-300/[0.04] px-3 py-2 text-xs capitalize text-violet-200">
          <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> {progressLabel(status)}
        </div>
      )}
      {(error || status?.job?.error_message) && (
        <div className="mt-4 flex gap-2 rounded-lg border border-red-400/15 bg-red-400/[0.04] p-3 text-xs leading-5 text-red-200">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {error ?? status?.job?.error_message}
        </div>
      )}

      {transcript && (
        <div className="mt-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-zinc-500">{transcript.language?.toUpperCase() ?? "Language auto-detected"} · {transcript.provider} / {transcript.model}</p>
            <div className="relative sm:w-64">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-600" />
              <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search transcript" className="h-9 pl-9 text-xs" />
            </div>
          </div>
          <div className="mt-4 max-h-80 space-y-1 overflow-y-auto rounded-xl border border-white/[0.06] bg-black/20 p-2">
            {visibleSegments.map((segment) => (
              <button key={segment.id} type="button" onClick={() => seek(segment.start_ms)} className="grid w-full grid-cols-[3.25rem_1fr] gap-3 rounded-lg px-3 py-2.5 text-left transition hover:bg-white/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400">
                <span className="font-mono text-xs text-violet-300">{timestamp(segment.start_ms)}</span>
                <span className="text-sm leading-6 text-zinc-300">{segment.text}</span>
              </button>
            ))}
            {visibleSegments.length === 0 && <p className="px-3 py-8 text-center text-xs text-zinc-600">No transcript segments match this search.</p>}
          </div>
        </div>
      )}
    </div>
  );
}
