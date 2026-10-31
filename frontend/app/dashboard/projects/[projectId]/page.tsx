"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Clock3,
  FileVideo,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  UploadCloud,
  Youtube,
} from "lucide-react";

import { MultipartUploader } from "@/components/multipart-uploader";
import { YouTubeImporter } from "@/components/youtube-importer";
import { TranscriptViewer } from "@/components/transcript-viewer";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getProject,
  listProjectMedia,
  type MediaAsset,
  type MediaAssetStatus,
  type Project,
} from "@/lib/api";
import { cn, formatFileSize } from "@/lib/utils";

const ACTIVE_STATUSES = new Set<MediaAssetStatus>([
  "pending_upload",
  "importing",
  "uploading",
  "uploaded",
  "validating",
]);

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return `${minutes}:${remainder.toString().padStart(2, "0")}`;
}

function MediaStatus({ status }: { status: MediaAssetStatus }) {
  const active = ACTIVE_STATUSES.has(status);
  const ready = status === "ready";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium capitalize",
        ready && "border-emerald-300/15 bg-emerald-300/[0.07] text-emerald-200",
        active && "border-violet-300/15 bg-violet-300/[0.07] text-violet-200",
        !ready && !active && "border-red-300/15 bg-red-300/[0.07] text-red-200",
      )}
    >
      {active ? <LoaderCircle className="h-3 w-3 animate-spin" /> : ready ? <CheckCircle2 className="h-3 w-3" /> : <AlertCircle className="h-3 w-3" />}
      {ready ? "Ready" : active ? "Getting ready" : "Needs help"}
    </span>
  );
}

export default function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [media, setMedia] = useState<MediaAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<"upload" | "youtube">("upload");

  async function refresh(showLoading = false) {
    if (showLoading) setLoading(true);
    try {
      const [nextProject, nextMedia] = await Promise.all([
        getProject(projectId),
        listProjectMedia(projectId),
      ]);
      setProject(nextProject);
      setMedia(nextMedia);
      setError(null);
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : "Project details could not be loaded.");
    } finally {
      if (showLoading) setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    Promise.all([getProject(projectId), listProjectMedia(projectId)])
      .then(([nextProject, nextMedia]) => {
        if (!cancelled) {
          setProject(nextProject);
          setMedia(nextMedia);
          setError(null);
        }
      })
      .catch((loadError: unknown) => {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "Project details could not be loaded.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    const interval = window.setInterval(() => {
      listProjectMedia(projectId)
        .then((nextMedia) => {
          if (!cancelled) setMedia(nextMedia);
        })
        .catch(() => undefined);
    }, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [projectId]);

  return (
    <main className="mx-auto max-w-6xl px-5 py-10 sm:px-8 sm:py-12">
      <Button asChild variant="ghost" size="sm" className="-ml-3 text-zinc-500"><Link href="/dashboard"><ArrowLeft className="h-4 w-4" /> Back to projects</Link></Button>

      {loading ? (
        <div className="mt-10 space-y-4"><div className="h-10 w-72 animate-pulse rounded-lg bg-white/[0.06]" /><div className="h-52 animate-pulse rounded-2xl bg-white/[0.025]" /></div>
      ) : error && !project ? (
        <Card className="mt-8 border-red-400/15"><CardContent className="flex items-center justify-between gap-4 p-6"><div className="flex items-center gap-3 text-sm text-red-200"><AlertCircle className="h-5 w-5" /> {error}</div><Button size="sm" variant="secondary" onClick={() => void refresh(true)}><RefreshCw className="h-4 w-4" /> Retry</Button></CardContent></Card>
      ) : project ? (
        <>
          <div className="mt-7 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div><p className="text-sm font-medium text-violet-300">Project</p><h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-white sm:text-4xl">{project.title}</h1><p className="mt-3 max-w-2xl text-sm leading-6 text-zinc-500">{project.description ?? "No project description."}</p></div>
            <div className="flex items-center gap-2 text-xs text-zinc-600"><ShieldCheck className="h-4 w-4 text-violet-300" /> Only you can see this</div>
          </div>

          <section className="mt-10" aria-labelledby="media-heading">
            <div className="flex items-center justify-between"><h2 id="media-heading" className="text-sm font-medium text-zinc-300">Your videos</h2><span className="text-xs text-zinc-600">{media.length} {media.length === 1 ? "video" : "videos"}</span></div>
            {media.length === 0 ? (
              <div className="mt-4 rounded-2xl border border-dashed border-white/10 bg-white/[0.018] px-6 py-12 text-center"><FileVideo className="mx-auto h-6 w-6 text-violet-300" /><p className="mt-4 text-sm font-medium text-zinc-200">No video yet</p><p className="mt-2 text-xs text-zinc-600">Choose a video below to get started.</p></div>
            ) : (
              <div className="mt-4 space-y-4">
                {media.map((asset) => (
                  <Card key={asset.id}>
                    <CardContent className="grid gap-6 p-5 lg:grid-cols-[1fr_1.2fr]">
                      <div className="flex min-h-48 items-center justify-center overflow-hidden rounded-xl border border-white/[0.06] bg-black/30">
                        {asset.preview_url ? <video id={`video-${asset.id}`} controls preload="metadata" src={asset.preview_url} className="h-full max-h-80 w-full bg-black object-contain" /> : <div className="text-center"><FileVideo className="mx-auto h-7 w-7 text-zinc-700" /><p className="mt-3 text-xs text-zinc-600">Your video will appear here when it is ready</p></div>}
                      </div>
                      <div>
                        <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="font-medium text-white">{asset.original_filename}</h3><p className="mt-1 text-xs text-zinc-600">Uploaded {new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(asset.created_at))}</p></div><MediaStatus status={asset.status} /></div>
                        <dl className="mt-6 grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
                          <div><dt className="text-xs text-zinc-600">File size</dt><dd className="mt-1 text-zinc-300">{formatFileSize(asset.file_size_bytes)}</dd></div>
                          <div><dt className="text-xs text-zinc-600">Length</dt><dd className="mt-1 text-zinc-300">{formatDuration(asset.duration_seconds)}</dd></div>
                          <div><dt className="text-xs text-zinc-600">Picture size</dt><dd className="mt-1 text-zinc-300">{asset.width && asset.height ? `${asset.width} × ${asset.height}` : "—"}</dd></div>
                        </dl>
                        {asset.latest_job?.error_message && <div className="mt-5 flex gap-2 rounded-lg border border-red-400/15 bg-red-400/[0.04] p-3 text-xs leading-5 text-red-200"><AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {asset.latest_job.error_message}</div>}
                        {ACTIVE_STATUSES.has(asset.status) && <p className="mt-5 flex items-center gap-2 text-xs text-zinc-500"><Clock3 className="h-3.5 w-3.5" /> Howlix is getting your video ready. You can leave this page.</p>}
                        {asset.status === "ready" && <TranscriptViewer assetId={asset.id} videoElementId={`video-${asset.id}`} />}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </section>

          <Card className="mt-8">
            <CardHeader><CardTitle>Add another video</CardTitle><CardDescription>Choose a video from your device or use a YouTube link.</CardDescription></CardHeader>
            <CardContent>
              <div role="tablist" aria-label="Video source" className="mb-5 grid gap-3 sm:grid-cols-2">
                <button type="button" role="tab" aria-selected={source === "upload"} onClick={() => setSource("upload")} className={`rounded-2xl border p-4 text-left transition ${source === "upload" ? "border-violet-400/40 bg-violet-500/10 text-white" : "border-white/[0.07] bg-black/10 text-zinc-500"}`}><UploadCloud className="h-5 w-5 text-violet-300" /><span className="mt-3 block text-sm font-medium">Choose a video</span><span className="mt-1 block text-xs opacity-70">Pick one from this device.</span></button>
                <button type="button" role="tab" aria-selected={source === "youtube"} onClick={() => setSource("youtube")} className={`rounded-2xl border p-4 text-left transition ${source === "youtube" ? "border-violet-400/40 bg-violet-500/10 text-white" : "border-white/[0.07] bg-black/10 text-zinc-500"}`}><Youtube className="h-5 w-5 text-violet-300" /><span className="mt-3 block text-sm font-medium">Use a YouTube link</span><span className="mt-1 block text-xs opacity-70">Only use videos you are allowed to use.</span></button>
              </div>
              {source === "upload" ? <MultipartUploader projectId={project.id} onUploadComplete={() => void refresh()} /> : <YouTubeImporter projectId={project.id} onImportChanged={() => void refresh()} />}
            </CardContent>
          </Card>
        </>
      ) : null}
    </main>
  );
}
