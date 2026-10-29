"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowRight, FolderPlus, RefreshCw, Video } from "lucide-react";

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
    <main className="mx-auto max-w-6xl px-5 py-10 sm:px-8 sm:py-12">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm font-medium text-violet-300">Workspace</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-white sm:text-4xl">Welcome to Howlix</h1>
          <p className="mt-3 text-sm text-zinc-500">Create and manage your local video projects.</p>
        </div>
        <Button asChild className="self-start"><Link href="/dashboard/new"><FolderPlus className="h-4 w-4" /> New Project</Link></Button>
      </div>

      <section className="mt-12" aria-labelledby="projects-heading">
        <div className="flex items-center justify-between">
          <h2 id="projects-heading" className="text-sm font-medium text-zinc-300">Projects</h2>
          {!loading && !error && <span className="text-xs text-zinc-600">{projects.length} {projects.length === 1 ? "project" : "projects"}</span>}
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
          <div className="mt-5 flex min-h-80 flex-col items-center justify-center rounded-2xl border border-dashed border-white/10 bg-white/[0.018] px-6 text-center">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl border border-violet-400/15 bg-violet-500/10 text-violet-300"><Video className="h-5 w-5" /></span>
            <h3 className="mt-5 text-lg font-medium text-white">No projects yet</h3>
            <p className="mt-2 max-w-sm text-sm leading-6 text-zinc-500">Create a project, upload a video securely, and follow its validation status here.</p>
            <Button asChild className="mt-6"><Link href="/dashboard/new">Create your first project <ArrowRight className="h-4 w-4" /></Link></Button>
          </div>
        )}

        {!loading && !error && projects.length > 0 && (
          <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {projects.map((project) => (
              <Link key={project.id} href={`/dashboard/projects/${project.id}`} className="rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400">
                <Card className="group h-full transition hover:border-violet-400/20 hover:bg-white/[0.045]">
                  <CardContent className="p-5">
                    <div className="flex items-start justify-between gap-4"><span className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-500/10 text-violet-300"><Video className="h-4 w-4" /></span><StatusIndicator status={project.status} /></div>
                    <h3 className="mt-6 truncate font-medium text-white">{project.title}</h3>
                    <p className="mt-2 line-clamp-2 min-h-10 text-sm leading-5 text-zinc-500">{project.description ?? "No description added."}</p>
                    <div className="mt-5 border-t border-white/[0.06] pt-4 text-xs text-zinc-600">Created {new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(project.created_at))}</div>
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

