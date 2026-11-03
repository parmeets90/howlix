"use client";

import { useEffect, useState, type CSSProperties } from "react";
import Link from "next/link";
import { AlertCircle, ArrowRight, FolderPlus, LockKeyhole, Play, RefreshCw, Sparkles, Video } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { StatusIndicator } from "@/components/ui/status-indicator";
import { listProjects, type Project } from "@/lib/api";

export default function DashboardPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadProjects() {
    setLoading(true);
    setError(null);
    try {
      setProjects(await listProjects());
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Projects could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    listProjects()
      .then((loadedProjects) => {
        if (!cancelled) setProjects(loadedProjects);
      })
      .catch((loadError: unknown) => {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Projects could not be loaded.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="app-page mx-auto max-w-7xl px-5 py-8 sm:px-8 sm:py-10 lg:px-10">
      <div className="surface-noise relative overflow-hidden rounded-[1.75rem] border border-white/[0.08] bg-gradient-to-br from-violet-500/[0.11] via-white/[0.035] to-transparent px-6 py-7 shadow-[0_30px_90px_rgba(0,0,0,.25)] sm:px-8 sm:py-9">
        <div className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-violet-500/15 blur-3xl" />
        <div className="relative flex flex-col gap-7 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-violet-300/15 bg-violet-300/[0.07] px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-violet-200"><Sparkles className="h-3 w-3" /> Creative workspace</div>
            <h1 className="mt-5 text-3xl font-semibold tracking-[-0.045em] text-white sm:text-4xl lg:text-[2.75rem]">Turn long videos into<br className="hidden sm:block" /> moments worth sharing.</h1>
            <p className="mt-4 max-w-xl text-sm leading-6 text-zinc-400 sm:text-[15px]">Keep every video, idea, and finished clip organized in one private workspace.</p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row lg:flex-col xl:flex-row">
            <div className="flex items-center gap-3 rounded-xl border border-white/[0.07] bg-black/20 px-4 py-3 text-xs text-zinc-400"><LockKeyhole className="h-4 w-4 text-violet-300" /><span><strong className="block font-medium text-zinc-200">Private by default</strong>Only you can access your videos.</span></div>
            <Button asChild size="lg" className="shrink-0"><Link href="/dashboard/new"><FolderPlus className="h-4 w-4" /> Create project</Link></Button>
          </div>
        </div>
      </div>

      <section className="content-auto mt-10" aria-labelledby="projects-heading">
        <div className="flex items-center justify-between">
          <div><p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-violet-300">Library</p><h2 id="projects-heading" className="mt-1.5 text-xl font-semibold tracking-[-0.025em] text-white">Your projects</h2></div>
          {!loading && !error && <span className="rounded-full border border-white/[0.07] bg-white/[0.03] px-3 py-1.5 text-xs text-zinc-500">{projects.length} {projects.length === 1 ? "project" : "projects"}</span>}
        </div>

        {loading && (
          <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-label="Loading projects">
            {[0, 1, 2].map((item) => <div key={item} className="h-44 animate-pulse rounded-2xl border border-white/[0.06] bg-white/[0.025]" />)}
          </div>
        )}

        {!loading && error && (
          <Card className="mt-5 border-red-400/15 bg-red-400/[0.035]">
            <CardContent className="flex flex-col items-start gap-4 p-6 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex gap-3"><AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-red-300" /><div><p className="text-sm font-medium text-zinc-200">Couldn’t load projects</p><p className="mt-1 text-sm text-zinc-500">{error}</p></div></div>
              <Button variant="secondary" size="sm" onClick={() => void loadProjects()}><RefreshCw className="h-3.5 w-3.5" /> Try again</Button>
            </CardContent>
          </Card>
        )}

        {!loading && !error && projects.length === 0 && (
          <div className="mt-6 flex min-h-80 flex-col items-center justify-center rounded-[1.5rem] border border-dashed border-white/10 bg-gradient-to-b from-white/[0.025] to-transparent px-6 text-center">
            <span className="flex h-14 w-14 items-center justify-center rounded-2xl border border-violet-400/15 bg-violet-500/10 text-violet-300 shadow-[0_12px_35px_rgba(109,40,217,.18)]"><Play className="h-5 w-5 fill-current" /></span>
            <h3 className="mt-5 text-lg font-medium text-white">No projects yet</h3>
            <p className="mt-2 max-w-sm text-sm leading-6 text-zinc-500">Add a video and let Howlix help you turn the best parts into short clips.</p>
            <Button asChild className="mt-6"><Link href="/dashboard/new">Create your first project <ArrowRight className="h-4 w-4" /></Link></Button>
          </div>
        )}

        {!loading && !error && projects.length > 0 && (
          <div className="mt-6 grid auto-rows-fr gap-5 sm:grid-cols-2 xl:grid-cols-3">
            {projects.map((project, index) => (
              <Link key={project.id} href={`/dashboard/projects/${project.id}`} style={{ "--stagger": index } as CSSProperties} className="stagger-item rounded-[1.35rem] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400">
                <Card className="app-grid-glow group flex h-full min-h-56 flex-col transition-[transform,border-color,background-color,box-shadow] duration-300 hover:-translate-y-1 hover:border-violet-400/20 hover:from-white/[0.065] hover:shadow-[0_28px_70px_rgba(0,0,0,.28)]">
                  <CardContent className="flex h-full flex-col p-5 sm:p-6">
                    <div className="flex items-start justify-between gap-4"><span className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-500/10 text-violet-300"><Video className="h-4 w-4" /></span><StatusIndicator status={project.status} /></div>
                    <h3 className="mt-6 truncate font-medium text-white">{project.title}</h3>
                    <p className="mt-2 line-clamp-2 min-h-10 text-sm leading-5 text-zinc-500">{project.description ?? "No description added."}</p>
                    <div className="mt-auto flex items-center justify-between border-t border-white/[0.06] pt-4 text-xs text-zinc-600"><span>Created {new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(project.created_at))}</span><ArrowRight className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-1 group-hover:text-violet-300" /></div>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

