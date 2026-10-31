"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Download,
  Film,
  LoaderCircle,
  Play,
  RefreshCw,
  Settings2,
  Square,
  X,
} from "lucide-react";

import { Button } from "./ui/button";
import { Input } from "./ui/input";
import {
  cancelClipExport,
  createClipExport,
  getClipExportDownload,
  listClipExports,
  redispatchJob,
  type CaptionPreset,
  type ClipExport,
  type ClipExportSettings,
  type ExportAspectRatio,
  type FramingMode,
} from "../lib/api";
import { cn, formatFileSize } from "../lib/utils";


const ACTIVE = new Set(["queued", "processing", "retry"]);
const selectClass = "h-9 rounded-md border border-white/10 bg-black/30 px-2 text-xs text-zinc-300 outline-none focus:border-violet-400/50";

function exportProgress(item: ClipExport): string {
  const job = item.job;
  const stage = job?.progress_stage?.replaceAll("_", " ") ?? item.status;
  if (job?.progress_completed !== null && job?.progress_completed !== undefined && job.progress_total) {
    return `${stage} · ${Math.min(100, Math.round(job.progress_completed / job.progress_total * 100))}%`;
  }
  return stage;
}

export function ClipExportSettingsForm({
  submitting,
  onSubmit,
}: {
  submitting: boolean;
  onSubmit: (settings: ClipExportSettings) => Promise<void>;
}) {
  const [aspectRatio, setAspectRatio] = useState<ExportAspectRatio>("9:16");
  const [quality, setQuality] = useState<"720p" | "1080p">("720p");
  const [framingMode, setFramingMode] = useState<FramingMode>("center");
  const [captionPreset, setCaptionPreset] = useState<CaptionPreset>("bold");
  const [fontSize, setFontSize] = useState("52");
  const [textColor, setTextColor] = useState("#FFFFFF");
  const [highlightColor, setHighlightColor] = useState("#A78BFA");
  const [verticalPosition, setVerticalPosition] = useState<"bottom" | "center" | "top">("bottom");
  const [cropX, setCropX] = useState("0.5");
  const [cropY, setCropY] = useState("0.5");

  async function submit() {
    await onSubmit({
      aspect_ratio: aspectRatio,
      quality,
      framing_mode: framingMode,
      caption_preset: captionPreset,
      ...(framingMode === "manual" ? { manual_crop_x: Number(cropX), manual_crop_y: Number(cropY) } : {}),
      ...(captionPreset !== "none" ? {
        caption_font_size: Number(fontSize),
        caption_text_color: textColor,
        caption_highlight_color: highlightColor,
        caption_vertical_position: verticalPosition,
      } : {}),
    });
  }

  return <div className="rounded-xl border border-white/[0.06] bg-black/20 p-4">
    <div className="flex items-center gap-2"><Settings2 className="h-4 w-4 text-violet-300" /><p className="text-sm font-medium text-zinc-200">Clip export settings</p></div>
    <p className="mt-1 text-[11px] text-zinc-600">Your final video will appear here when it is ready.</p>
    <div className="mt-4 grid gap-3 sm:grid-cols-2">
      <label className="grid gap-1.5 text-xs text-zinc-500">Aspect ratio<select aria-label="Aspect ratio" className={selectClass} value={aspectRatio} onChange={(event) => setAspectRatio(event.target.value as ExportAspectRatio)}><option value="9:16">9:16 vertical</option><option value="1:1">1:1 square</option><option value="16:9">16:9 landscape</option></select></label>
      <label className="grid gap-1.5 text-xs text-zinc-500">Quality<select aria-label="Export quality" className={selectClass} value={quality} onChange={(event) => { const next = event.target.value as "720p" | "1080p"; setQuality(next); setFontSize(next === "1080p" ? "76" : "52"); }}><option value="720p">720p · recommended</option><option value="1080p">1080p · high quality</option></select></label>
      <label className="grid gap-1.5 text-xs text-zinc-500">Framing<select aria-label="Framing mode" className={selectClass} value={framingMode} onChange={(event) => setFramingMode(event.target.value as FramingMode)}><option value="center">Center crop</option><option value="face">Face-aware · best effort</option><option value="manual">Manual focus</option></select></label>
      <label className="grid gap-1.5 text-xs text-zinc-500">Captions<select aria-label="Caption preset" className={selectClass} value={captionPreset} onChange={(event) => setCaptionPreset(event.target.value as CaptionPreset)}><option value="none">Disabled</option><option value="minimal">Minimal</option><option value="bold">Bold</option><option value="karaoke">Karaoke</option></select></label>
    </div>
    {framingMode === "manual" && <div className="mt-4 grid grid-cols-2 gap-3"><label className="grid gap-1.5 text-xs text-zinc-500">Horizontal focus<Input type="number" min="0" max="1" step="0.05" value={cropX} onChange={(event) => setCropX(event.target.value)} /></label><label className="grid gap-1.5 text-xs text-zinc-500">Vertical focus<Input type="number" min="0" max="1" step="0.05" value={cropY} onChange={(event) => setCropY(event.target.value)} /></label></div>}
    {captionPreset !== "none" && <div className="mt-4 grid gap-3 sm:grid-cols-2"><label className="grid gap-1.5 text-xs text-zinc-500">Caption size<Input type="number" min="24" max="120" value={fontSize} onChange={(event) => setFontSize(event.target.value)} /></label><label className="grid gap-1.5 text-xs text-zinc-500">Position<select aria-label="Caption position" className={selectClass} value={verticalPosition} onChange={(event) => setVerticalPosition(event.target.value as typeof verticalPosition)}><option value="bottom">Lower third</option><option value="center">Center</option><option value="top">Top</option></select></label><label className="grid gap-1.5 text-xs text-zinc-500">Text color<Input type="color" value={textColor} onChange={(event) => setTextColor(event.target.value)} /></label><label className="grid gap-1.5 text-xs text-zinc-500">Highlight color<Input type="color" value={highlightColor} onChange={(event) => setHighlightColor(event.target.value)} /></label></div>}
    <Button type="button" size="sm" className="mt-5 w-full" disabled={submitting} onClick={() => void submit()}>{submitting ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <Film className="h-3.5 w-3.5" />} Create Clip</Button>
  </div>;
}

export function ClipExports({ momentId }: { momentId: string }) {
  const [exports, setExports] = useState<ClipExport[]>([]);
  const [showSettings, setShowSettings] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [downloadUrls, setDownloadUrls] = useState<Record<string, string>>({});

  const refresh = useCallback(async () => {
    try { setExports(await listClipExports(momentId)); setError(null); }
    catch (loadError) { setError(loadError instanceof Error ? loadError.message : "Export history could not be loaded."); }
  }, [momentId]);

  useEffect(() => { const timeout = window.setTimeout(() => void refresh(), 0); return () => window.clearTimeout(timeout); }, [refresh]);
  useEffect(() => {
    if (!exports.some((item) => ACTIVE.has(item.status))) return;
    const interval = window.setInterval(() => void refresh(), 2000);
    return () => window.clearInterval(interval);
  }, [exports, refresh]);

  async function create(settings: ClipExportSettings) {
    setSubmitting(true); setError(null);
    try { await createClipExport(momentId, settings); setShowSettings(false); await refresh(); }
    catch (createError) { setError(createError instanceof Error ? createError.message : "Clip export could not be started."); }
    finally { setSubmitting(false); }
  }

  async function loadDownload(item: ClipExport) {
    try { const result = await getClipExportDownload(item.id); setDownloadUrls((current) => ({ ...current, [item.id]: result.download_url })); }
    catch (downloadError) { setError(downloadError instanceof Error ? downloadError.message : "Private download URL could not be created."); }
  }

  async function retry(item: ClipExport) {
    const settings = item.render_settings;
    await create({
      aspect_ratio: item.aspect_ratio,
      quality: settings.quality as "720p" | "1080p",
      framing_mode: item.framing_mode,
      caption_preset: item.caption_preset,
      fps: item.fps,
      ...(item.framing_mode === "manual" ? { manual_crop_x: Number(settings.manual_crop_x), manual_crop_y: Number(settings.manual_crop_y) } : {}),
      caption_font_size: Number(settings.caption_font_size),
      caption_text_color: String(settings.caption_text_color),
      caption_highlight_color: String(settings.caption_highlight_color),
      caption_vertical_position: settings.caption_vertical_position as "bottom" | "center" | "top",
    });
  }

  return <div className="mt-5 border-t border-white/[0.06] pt-5">
    <div className="flex items-center justify-between gap-3"><div><p className="flex items-center gap-2 text-sm font-medium text-zinc-200"><Film className="h-4 w-4 text-violet-300" /> Your clips</p><p className="mt-1 text-[11px] text-zinc-600">Choose an idea, make it, then download it.</p></div><Button type="button" size="sm" variant="secondary" onClick={() => setShowSettings((value) => !value)}>{showSettings ? <X className="h-3.5 w-3.5" /> : <Square className="h-3.5 w-3.5" />}{showSettings ? "Close" : "Make clip"}</Button></div>
    {showSettings && <div className="mt-4"><ClipExportSettingsForm submitting={submitting} onSubmit={create} /></div>}
    {error && <p className="mt-3 flex gap-2 text-xs text-red-200"><AlertCircle className="h-3.5 w-3.5 shrink-0" />{error}</p>}
    <div className="mt-4 space-y-3">{exports.map((item) => {
      const url = downloadUrls[item.id];
      return <div key={item.id} className="rounded-xl border border-white/[0.06] bg-black/20 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-medium text-zinc-300">{item.aspect_ratio} · {item.resolution} · {item.caption_preset} words</p><p className="mt-1 text-[11px] capitalize text-zinc-600">{item.framing_mode} view</p></div><span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-[10px] uppercase tracking-[0.08em]", item.status === "completed" ? "border-emerald-300/15 text-emerald-200" : item.status === "failed" ? "border-red-300/15 text-red-200" : "border-violet-300/15 text-violet-200")}>{ACTIVE.has(item.status) && <LoaderCircle className="h-3 w-3 animate-spin" />}{item.status === "completed" && <CheckCircle2 className="h-3 w-3" />}{item.status === "completed" ? "Ready" : item.status === "failed" ? "Needs help" : "Making clip"}</span></div>
        {ACTIVE.has(item.status) && <div className="mt-3"><p className="text-[11px] capitalize text-violet-200">{exportProgress(item)}</p>{item.job?.progress_total ? <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/[0.05]"><div className="h-full bg-violet-400 transition-all" style={{ width: `${Math.min(100, (item.job.progress_completed ?? 0) / item.job.progress_total * 100)}%` }} /></div> : null}<Button className="mt-3" size="sm" variant="ghost" onClick={async () => { await cancelClipExport(item.id); await refresh(); }}><X className="h-3.5 w-3.5" /> Cancel</Button></div>}
        {(item.error_message || item.job?.dispatch_error_message) && <p className="mt-3 text-xs leading-5 text-red-200">{item.error_message || item.job?.dispatch_error_message}</p>}
        {ACTIVE.has(item.status) && item.job?.dispatch_error_message && <Button className="mt-3" size="sm" variant="secondary" onClick={async () => { await redispatchJob(item.job!.id); await refresh(); }}><RefreshCw className="h-3.5 w-3.5" /> Retry runner</Button>}
        {(item.status === "failed" || item.status === "cancelled") && <Button className="mt-3" size="sm" variant="secondary" onClick={() => void retry(item)}><RefreshCw className="h-3.5 w-3.5" /> Retry</Button>}
        {item.status === "completed" && <div className="mt-3">{url ? <><video controls preload="metadata" src={url} className="max-h-96 w-full rounded-lg bg-black object-contain" /><div className="mt-3 flex flex-wrap items-center gap-2"><Button asChild size="sm"><a href={url} download><Download className="h-3.5 w-3.5" /> Download MP4</a></Button><span className="text-[11px] text-zinc-600">{item.file_size_bytes ? formatFileSize(item.file_size_bytes) : "MP4"} · private temporary URL</span></div></> : <Button size="sm" variant="secondary" onClick={() => void loadDownload(item)}><Play className="h-3.5 w-3.5" /> Load finished preview</Button>}</div>}
      </div>;
    })}{exports.length === 0 && !showSettings && <p className="rounded-lg border border-dashed border-white/10 px-4 py-6 text-center text-xs text-zinc-600">No clips made yet.</p>}</div>
  </div>;
}
