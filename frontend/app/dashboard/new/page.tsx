"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, ArrowLeft, LoaderCircle, UploadCloud, Youtube } from "lucide-react";
import Link from "next/link";

import { MultipartUploader, type MultipartUploaderHandle } from "@/components/multipart-uploader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { createProject, createYouTubeImport, type Project } from "@/lib/api";

export default function NewProjectPage() {
  const router = useRouter();
  const uploaderRef = useRef<MultipartUploaderHandle>(null);
  const uploadStartedRef = useRef(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [createdProject, setCreatedProject] = useState<Project | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<"upload" | "youtube">("upload");
  const [fileSelected, setFileSelected] = useState(false);
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [permissionConfirmed, setPermissionConfirmed] = useState(false);
  const [startUpload, setStartUpload] = useState(false);

  useEffect(() => {
    if (!createdProject || !startUpload || uploadStartedRef.current) return;
    uploadStartedRef.current = true;
    uploaderRef.current?.start();
  }, [createdProject, startUpload]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!title.trim()) { setError("Give your project a name."); return; }
    if (source === "upload" && !fileSelected) { setError("Choose a video first."); return; }
    if (source === "youtube" && !youtubeUrl.trim()) { setError("Paste a YouTube link first."); return; }
    if (source === "youtube" && !permissionConfirmed) { setError("Please confirm that you are allowed to use this video."); return; }
    setSubmitting(true);
    setError(null);
    try {
      const project = createdProject ?? await createProject({
        title: title.trim(),
        description: description.trim() || undefined,
      });
      setCreatedProject(project);
      if (source === "upload") {
        setStartUpload(true);
      } else {
        await createYouTubeImport(project.id, { url: youtubeUrl.trim(), permission_confirmed: true });
        router.push(`/dashboard/projects/${project.id}`);
        router.refresh();
      }
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "The project could not be created.");
      setSubmitting(false);
    }
  }

  const ready = Boolean(title.trim()) && (source === "upload" ? fileSelected : Boolean(youtubeUrl.trim() && permissionConfirmed));

  return (
    <main className="mx-auto max-w-4xl px-5 py-10 sm:px-8 sm:py-12">
      <Button asChild variant="ghost" size="sm" className="-ml-3 text-zinc-500"><Link href="/dashboard"><ArrowLeft className="h-4 w-4" /> Back</Link></Button>
      <div className="mt-7"><p className="text-sm font-medium text-violet-300">New project</p><h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-white sm:text-4xl">Add your video</h1><p className="mt-3 max-w-2xl text-sm leading-6 text-zinc-500">Name it, choose your video, then click one button. Howlix will take care of the rest.</p></div>

      <form onSubmit={handleSubmit} className="mt-10 space-y-5">
        <Card>
          <CardHeader><CardTitle>1. Name your project</CardTitle><CardDescription>Pick a name that will help you find it later.</CardDescription></CardHeader>
          <CardContent className="space-y-5">
            <label className="block"><span className="mb-2 block text-sm font-medium text-zinc-300">Project name <span className="text-violet-300">*</span></span><Input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={160} placeholder="My first video" disabled={submitting || Boolean(createdProject)} /></label>
            <label className="block"><span className="mb-2 block text-sm font-medium text-zinc-300">A little note <span className="font-normal text-zinc-600">(you can skip this)</span></span><textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={2000} rows={3} placeholder="What is this video about?" disabled={submitting || Boolean(createdProject)} className="w-full resize-none rounded-xl border border-white/10 bg-black/20 px-3.5 py-3 text-sm text-white outline-none transition placeholder:text-zinc-600 focus:border-violet-400/70 focus:ring-2 focus:ring-violet-500/15 disabled:opacity-50" /></label>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><div className="flex flex-wrap items-center justify-between gap-3"><div><CardTitle>2. Choose your video</CardTitle><CardDescription className="mt-1.5">Upload one from your device or paste a YouTube link.</CardDescription></div><span className="rounded-full border border-violet-400/20 bg-violet-400/10 px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.12em] text-violet-200">Only you can see it</span></div></CardHeader>
          <CardContent>
            <div role="tablist" aria-label="Video source" className="mb-5 grid gap-3 sm:grid-cols-2">
              <button type="button" role="tab" aria-selected={source === "upload"} onClick={() => setSource("upload")} className={`rounded-2xl border p-4 text-left transition ${source === "upload" ? "border-violet-400/40 bg-violet-500/10 text-white" : "border-white/[0.07] bg-black/10 text-zinc-500 hover:border-white/15"}`}><UploadCloud className="h-5 w-5 text-violet-300" /><span className="mt-3 block text-sm font-medium">Choose a video</span><span className="mt-1 block text-xs leading-5 opacity-70">Pick a video saved on this device.</span></button>
              <button type="button" role="tab" aria-selected={source === "youtube"} onClick={() => setSource("youtube")} className={`rounded-2xl border p-4 text-left transition ${source === "youtube" ? "border-violet-400/40 bg-violet-500/10 text-white" : "border-white/[0.07] bg-black/10 text-zinc-500 hover:border-white/15"}`}><Youtube className="h-5 w-5 text-violet-300" /><span className="mt-3 block text-sm font-medium">Use a YouTube link</span><span className="mt-1 block text-xs leading-5 opacity-70">Only use a video you are allowed to use.</span></button>
            </div>
            {source === "upload" ? <MultipartUploader
              ref={uploaderRef}
              projectId={createdProject?.id ?? ""}
              showStartButton={false}
              onSelectionChange={setFileSelected}
              onUploadComplete={() => {
                if (!createdProject) return;
                router.push(`/dashboard/projects/${createdProject.id}`);
                router.refresh();
              }}
            /> : <div className="space-y-4 rounded-2xl border border-white/[0.07] bg-black/10 p-5">
              <label className="block"><span className="mb-2 block text-sm font-medium text-zinc-300">YouTube link</span><Input type="url" value={youtubeUrl} onChange={(event) => setYoutubeUrl(event.target.value)} placeholder="https://youtube.com/watch?v=..." disabled={submitting || Boolean(createdProject)} /></label>
              <label className="flex cursor-pointer items-start gap-3 text-sm leading-6 text-zinc-400"><input type="checkbox" checked={permissionConfirmed} onChange={(event) => setPermissionConfirmed(event.target.checked)} disabled={submitting || Boolean(createdProject)} className="mt-1 h-4 w-4 accent-violet-500" /><span>I own this video, or I have permission to use it.</span></label>
            </div>}
          </CardContent>
        </Card>

        {error && <div role="alert" className="flex items-start gap-3 rounded-xl border border-red-400/15 bg-red-400/[0.045] p-4 text-sm text-red-200"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" /> {error}</div>}
        <div className="flex flex-col-reverse items-stretch gap-3 sm:flex-row sm:items-center sm:justify-end"><span className="text-center text-xs text-zinc-600 sm:mr-auto sm:text-left">One click starts everything.</span><Button asChild type="button" variant="ghost"><Link href="/dashboard">Cancel</Link></Button><Button type="submit" disabled={submitting || !ready || Boolean(createdProject)}>{submitting ? <><LoaderCircle className="h-4 w-4 animate-spin" /> Starting&hellip;</> : "Start my project"}</Button></div>
      </form>
    </main>
  );
}

