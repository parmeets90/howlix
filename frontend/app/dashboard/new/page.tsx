"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, ArrowLeft, LoaderCircle } from "lucide-react";
import Link from "next/link";

import { MultipartUploader } from "@/components/multipart-uploader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { createProject, type Project } from "@/lib/api";

export default function NewProjectPage() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [createdProject, setCreatedProject] = useState<Project | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!title.trim()) { setError("Enter a project title."); return; }
    setSubmitting(true);
    setError(null);
    try {
      const project = await createProject({
        title: title.trim(),
        description: description.trim() || undefined,
      });
      setCreatedProject(project);
      setSubmitting(false);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "The project could not be created.");
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto max-w-4xl px-5 py-10 sm:px-8 sm:py-12">
      <Button asChild variant="ghost" size="sm" className="-ml-3 text-zinc-500"><Link href="/dashboard"><ArrowLeft className="h-4 w-4" /> Back to projects</Link></Button>
      <div className="mt-7"><p className="text-sm font-medium text-violet-300">New project</p><h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-white sm:text-4xl">Bring in a long-form video</h1><p className="mt-3 max-w-2xl text-sm leading-6 text-zinc-500">Create a project, then upload the original video directly to your private Cloudflare R2 bucket.</p></div>

      <form onSubmit={handleSubmit} className="mt-10 space-y-5">
        <Card>
          <CardHeader><CardTitle>Project details</CardTitle><CardDescription>Give this project a clear working name.</CardDescription></CardHeader>
          <CardContent className="space-y-5">
            <label className="block"><span className="mb-2 block text-sm font-medium text-zinc-300">Project title <span className="text-violet-300">*</span></span><Input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={160} placeholder="e.g. Founder interview — October" disabled={submitting || Boolean(createdProject)} /></label>
            <label className="block"><span className="mb-2 block text-sm font-medium text-zinc-300">Description <span className="font-normal text-zinc-600">(optional)</span></span><textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={2000} rows={3} placeholder="What should this project focus on?" disabled={submitting || Boolean(createdProject)} className="w-full resize-none rounded-xl border border-white/10 bg-black/20 px-3.5 py-3 text-sm text-white outline-none transition placeholder:text-zinc-600 focus:border-violet-400/70 focus:ring-2 focus:ring-violet-500/15 disabled:opacity-50" /></label>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><div className="flex flex-wrap items-center justify-between gap-3"><div><CardTitle>Video file</CardTitle><CardDescription className="mt-1.5">Private multipart upload with FFprobe validation.</CardDescription></div><span className="rounded-full border border-violet-400/20 bg-violet-400/10 px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.12em] text-violet-200">Secure upload</span></div></CardHeader>
          <CardContent>
            {createdProject ? (
              <MultipartUploader
                projectId={createdProject.id}
                onUploadComplete={() => {
                  router.push(`/dashboard/projects/${createdProject.id}`);
                  router.refresh();
                }}
              />
            ) : (
              <div className="rounded-xl border border-dashed border-white/10 bg-black/10 px-5 py-8 text-center text-sm text-zinc-500">Create the project to unlock direct R2 upload.</div>
            )}
          </CardContent>
        </Card>

        {error && <div role="alert" className="flex items-start gap-3 rounded-xl border border-red-400/15 bg-red-400/[0.045] p-4 text-sm text-red-200"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" /> {error}</div>}
        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end"><Button asChild type="button" variant="ghost"><Link href="/dashboard">Cancel</Link></Button><Button type="submit" disabled={submitting || Boolean(createdProject)}>{submitting ? <><LoaderCircle className="h-4 w-4 animate-spin" /> Creating project…</> : createdProject ? "Project Created" : "Create Project & Continue"}</Button></div>
      </form>
    </main>
  );
}

