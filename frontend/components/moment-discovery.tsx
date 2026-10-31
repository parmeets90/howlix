"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Check,
  ChevronRight,
  Clock3,
  LoaderCircle,
  PencilLine,
  Play,
  RefreshCw,
  RotateCcw,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";

import { Button } from "./ui/button";
import { Input } from "./ui/input";
import {
  ApiError,
  discoverMoments,
  getMomentAnalysis,
  listMoments,
  reviewMoment,
  redispatchJob,
  updateMoment,
  type MomentAnalysis,
  type MomentCandidate,
  type MomentReviewStatus,
} from "../lib/api";
import { cn } from "../lib/utils";
import { ClipExports } from "./clip-exports";


const ACTIVE_STATUSES = new Set(["queued", "processing", "retry"]);
const FACTOR_LABELS: Record<string, string> = {
  hook_strength: "Hook strength",
  story_payoff: "Story & payoff",
  emotional_engagement: "Emotional engagement",
  standalone_clarity: "Standalone clarity",
  pacing: "Pacing",
  visual_quality: "Visual quality",
};

export function formatMomentTimestamp(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function progressLabel(analysis: MomentAnalysis): string {
  const job = analysis.job;
  if (!job) return "Getting ready to look";
  const stage = job.progress_stage?.replaceAll("_", " ") ?? job.status;
  if (job.progress_completed !== null && job.progress_total !== null) {
    return `${stage} · ${job.progress_completed} of ${job.progress_total}`;
  }
  return stage;
}

function ReviewBadge({ status }: { status: MomentReviewStatus }) {
  return (
    <span className={cn(
      "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.08em]",
      status === "approved" && "border-emerald-300/20 bg-emerald-300/[0.08] text-emerald-200",
      status === "rejected" && "border-red-300/20 bg-red-300/[0.08] text-red-200",
      status === "pending" && "border-white/10 bg-white/[0.04] text-zinc-500",
    )}>
      {status === "approved" && <Check className="h-2.5 w-2.5" />}{status}
    </span>
  );
}

export function MomentReviewPanel({
  candidate,
  onSave,
  onReset,
  onReview,
  onPreview,
}: {
  candidate: MomentCandidate;
  onSave: (input: { suggested_title: string; start_ms: number; end_ms: number }) => Promise<void>;
  onReset: () => Promise<void>;
  onReview: (status: MomentReviewStatus) => Promise<void>;
  onPreview: () => void;
}) {
  const [title, setTitle] = useState(candidate.suggested_title);
  const [startSeconds, setStartSeconds] = useState((candidate.start_ms / 1000).toFixed(1));
  const [endSeconds, setEndSeconds] = useState((candidate.end_ms / 1000).toFixed(1));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    const start = Number(startSeconds);
    const end = Number(endSeconds);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) {
      setError("Enter a valid end time after the start time.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave({ suggested_title: title, start_ms: Math.round(start * 1000), end_ms: Math.round(end * 1000) });
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Moment changes could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-xl border border-violet-300/15 bg-violet-300/[0.035] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><p className="text-[10px] font-medium uppercase tracking-[0.16em] text-violet-300">Clip idea #{candidate.rank}</p><p className="mt-1 text-xs text-zinc-600">This is an idea. Make the clip when you are happy with it.</p></div>
        <ReviewBadge status={candidate.review_status} />
      </div>

      <label className="mt-5 block text-xs text-zinc-500">Suggested title<Input className="mt-2" value={title} maxLength={200} onChange={(event) => setTitle(event.target.value)} /></label>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <label className="text-xs text-zinc-500">Start (seconds)<Input className="mt-2" type="number" min="0" step="0.1" value={startSeconds} onChange={(event) => setStartSeconds(event.target.value)} /></label>
        <label className="text-xs text-zinc-500">End (seconds)<Input className="mt-2" type="number" min="0" step="0.1" value={endSeconds} onChange={(event) => setEndSeconds(event.target.value)} /></label>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button type="button" size="sm" variant="secondary" onClick={onPreview}><Play className="h-3.5 w-3.5" /> Preview range</Button>
        <Button type="button" size="sm" variant="ghost" onClick={() => void onReset()}><RotateCcw className="h-3.5 w-3.5" /> Reset to AI</Button>
      </div>

      <div className="mt-5 rounded-lg border border-white/[0.06] bg-black/20 p-3">
        <p className="text-[10px] uppercase tracking-[0.14em] text-zinc-600">Words in this part</p>
        <p className="mt-2 max-h-32 overflow-y-auto text-xs leading-5 text-zinc-400">{candidate.transcript_excerpt}</p>
      </div>
      {error && <p className="mt-3 flex items-center gap-2 text-xs text-red-200"><AlertCircle className="h-3.5 w-3.5" />{error}</p>}
      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.06] pt-4">
        <div className="flex gap-2">
          <Button type="button" size="sm" variant="secondary" onClick={() => void onReview("approved")}><ThumbsUp className="h-3.5 w-3.5" /> Approve</Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => void onReview("rejected")}><ThumbsDown className="h-3.5 w-3.5" /> Reject</Button>
        </div>
        <Button type="button" size="sm" onClick={() => void save()} disabled={saving || !title.trim()}>{saving ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <PencilLine className="h-3.5 w-3.5" />} Save changes</Button>
      </div>
      {candidate.review_status === "approved" && <ClipExports momentId={candidate.id} />}
    </div>
  );
}

export function MomentDiscovery({ assetId, videoElementId }: { assetId: string; videoElementId: string }) {
  const [analysis, setAnalysis] = useState<MomentAnalysis | null>(null);
  const [moments, setMoments] = useState<MomentCandidate[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<MomentReviewStatus | "all">("all");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selected = useMemo(() => moments.find((item) => item.id === selectedId) ?? null, [moments, selectedId]);

  const refresh = useCallback(async () => {
    try {
      const next = await getMomentAnalysis(assetId);
      setAnalysis(next);
      if (next.status === "completed") {
        const nextMoments = await listMoments(assetId);
        setMoments(nextMoments);
        setSelectedId((current) => current && nextMoments.some((item) => item.id === current) ? current : nextMoments[0]?.id ?? null);
      }
      setError(null);
    } catch (refreshError) {
      if (refreshError instanceof ApiError && refreshError.status === 404) {
        setAnalysis(null);
        setMoments([]);
        setError(null);
      } else {
        setError(refreshError instanceof Error ? refreshError.message : "Moment analysis could not be loaded.");
      }
    } finally {
      setLoading(false);
    }
  }, [assetId]);

  useEffect(() => {
    const timeout = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timeout);
  }, [refresh]);

  useEffect(() => {
    if (!analysis || !ACTIVE_STATUSES.has(analysis.status)) return;
    const interval = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(interval);
  }, [analysis, refresh]);

  useEffect(() => {
    if (!selected) return;
    const video = document.getElementById(videoElementId) as HTMLVideoElement | null;
    if (!video) return;
    const stopAtBoundary = () => {
      if (video.currentTime * 1000 >= selected.end_ms) {
        video.pause();
        video.currentTime = selected.end_ms / 1000;
      }
    };
    video.addEventListener("timeupdate", stopAtBoundary);
    return () => video.removeEventListener("timeupdate", stopAtBoundary);
  }, [selected, videoElementId]);

  async function start() {
    setSubmitting(true);
    setError(null);
    try {
      setAnalysis(await discoverMoments(assetId));
      setMoments([]);
      setSelectedId(null);
    } catch (startError) {
      setError(startError instanceof Error ? startError.message : "Moment discovery could not be started.");
    } finally {
      setSubmitting(false);
    }
  }

  function replaceMoment(next: MomentCandidate) {
    setMoments((current) => current.map((item) => item.id === next.id ? next : item));
  }

  function preview() {
    if (!selected) return;
    const video = document.getElementById(videoElementId) as HTMLVideoElement | null;
    if (!video) return;
    video.currentTime = selected.start_ms / 1000;
    void video.play().catch(() => undefined);
  }

  const visibleMoments = filter === "all" ? moments : moments.filter((item) => item.review_status === filter);
  const active = analysis && ACTIVE_STATUSES.has(analysis.status);
  const failed = analysis?.status === "failed";

  return (
    <div className="mt-6 border-t border-white/[0.06] pt-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><p className="flex items-center gap-2 text-sm font-medium text-zinc-200"><Sparkles className="h-4 w-4 text-violet-300" /> Best moments</p><p className="mt-1 text-xs text-zinc-600">Howlix finds the parts people may enjoy most.</p></div>
        {!active && (!analysis || failed) && <Button type="button" size="sm" onClick={() => void start()} disabled={submitting}>{submitting ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : failed ? <RefreshCw className="h-3.5 w-3.5" /> : <Sparkles className="h-3.5 w-3.5" />}{failed ? "Try again" : "Find the best parts"}</Button>}
      </div>

      {loading && <p className="mt-4 flex items-center gap-2 text-xs text-zinc-500"><LoaderCircle className="h-3.5 w-3.5 animate-spin" /> Checking for great moments</p>}
      {active && analysis && <div className="mt-4 flex items-center gap-2 rounded-lg border border-violet-300/10 bg-violet-300/[0.04] px-3 py-2 text-xs capitalize text-violet-200"><LoaderCircle className="h-3.5 w-3.5 animate-spin" />{progressLabel(analysis)}</div>}
      {(error || analysis?.error_message || analysis?.job?.error_message || analysis?.job?.dispatch_error_message) && <div className="mt-4 flex gap-2 rounded-lg border border-red-400/15 bg-red-400/[0.04] p-3 text-xs leading-5 text-red-200"><AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />{error ?? analysis?.error_message ?? analysis?.job?.error_message ?? analysis?.job?.dispatch_error_message}</div>}
      {active && analysis?.job?.dispatch_error_message && <Button className="mt-3" type="button" size="sm" variant="secondary" onClick={async () => { await redispatchJob(analysis.job!.id); await refresh(); }}><RefreshCw className="h-3.5 w-3.5" /> Try again</Button>}

      {analysis?.status === "completed" && moments.length === 0 && <div className="mt-4 rounded-xl border border-white/[0.06] bg-white/[0.02] p-5 text-sm text-zinc-500">Howlix did not find a strong clip in this video. It will never suggest a weak one just to fill the list.</div>}

      {moments.length > 0 && <div className="mt-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-zinc-500">Howlix found {moments.length} good part{moments.length === 1 ? "" : "s"}. You choose the winners.</p>
          <div className="flex gap-1 rounded-lg border border-white/[0.06] bg-black/20 p-1">{(["all", "pending", "approved", "rejected"] as const).map((value) => <button key={value} type="button" onClick={() => setFilter(value)} className={cn("rounded-md px-2 py-1 text-[10px] capitalize text-zinc-600 transition", filter === value && "bg-white/[0.07] text-zinc-200")}>{value}</button>)}</div>
        </div>
        <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(20rem,0.9fr)]">
          <div className="space-y-2">
            {visibleMoments.map((moment) => <button key={moment.id} type="button" onClick={() => setSelectedId(moment.id)} className={cn("w-full rounded-xl border p-4 text-left transition", selectedId === moment.id ? "border-violet-300/20 bg-violet-300/[0.05]" : "border-white/[0.06] bg-black/15 hover:bg-white/[0.025]")}>
              <div className="flex items-start gap-3"><div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-violet-300/15 bg-violet-300/[0.06] text-sm font-semibold text-violet-200">{Math.round(moment.overall_score)}</div><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><span className="text-[10px] uppercase tracking-[0.14em] text-zinc-600">#{moment.rank} · {moment.category}</span><ReviewBadge status={moment.review_status} /></div><p className="mt-1 truncate text-sm font-medium text-zinc-200">{moment.suggested_title}</p><p className="mt-1 flex items-center gap-1.5 text-[11px] text-zinc-600"><Clock3 className="h-3 w-3" />{formatMomentTimestamp(moment.start_ms)}–{formatMomentTimestamp(moment.end_ms)} · {Math.round(moment.duration_ms / 1000)}s</p></div><ChevronRight className="mt-2 h-4 w-4 text-zinc-700" /></div>
              <p className="mt-3 line-clamp-2 text-xs leading-5 text-zinc-500">“{moment.hook_text}”</p>
            </button>)}
            {visibleMoments.length === 0 && <p className="rounded-xl border border-dashed border-white/10 px-4 py-8 text-center text-xs text-zinc-600">Nothing matches this choice.</p>}
          </div>
          {selected && <div className="space-y-3">
            <div className="rounded-xl border border-white/[0.06] bg-black/20 p-4"><p className="text-sm font-medium text-zinc-200">Why it was selected</p><p className="mt-2 text-xs leading-5 text-zinc-500">{selected.explanation}</p>{selected.needs_context && <p className="mt-3 flex items-center gap-2 text-xs text-amber-200"><AlertCircle className="h-3.5 w-3.5" />May need context from the original video.</p>}<div className="mt-4 space-y-2">{Object.entries(selected.score_breakdown).map(([factor, value]) => <div key={factor} className="grid grid-cols-[1fr_auto] items-center gap-3 text-xs"><span className="text-zinc-500">{FACTOR_LABELS[factor] ?? factor}</span><span className={value.assessed ? "font-mono text-zinc-300" : "text-zinc-700"}>{value.assessed && value.score !== null ? Math.round(value.score) : "Unassessed"}</span></div>)}</div><p className="mt-4 border-t border-white/[0.06] pt-3 text-[11px] leading-4 text-zinc-700">{selected.confidence_notes}</p></div>
            <MomentReviewPanel key={selected.id} candidate={selected} onPreview={preview} onSave={async (input) => replaceMoment(await updateMoment(selected.id, input))} onReset={async () => replaceMoment(await updateMoment(selected.id, { reset_boundaries: true }))} onReview={async (reviewStatus) => replaceMoment(await reviewMoment(selected.id, reviewStatus))} />
          </div>}
        </div>
      </div>}
    </div>
  );
}
