import Link from "next/link";
import {
  ArrowRight,
  Captions,
  Check,
  Clapperboard,
  Play,
  Scissors,
  Sparkles,
  Upload,
  WandSparkles,
} from "lucide-react";

import { Brand } from "@/components/brand";
import { Button } from "@/components/ui/button";

const steps = [
  { icon: Upload, number: "01", title: "Upload Video", copy: "Bring your podcast, interview, webinar, tutorial, or vlog." },
  { icon: WandSparkles, number: "02", title: "AI Finds Moments", copy: "Howlix will surface strong hooks and the moments worth keeping." },
  { icon: Scissors, number: "03", title: "Export Shorts", copy: "Refine your picks and turn them into vertical, captioned clips." },
];

const previews = [
  { icon: Sparkles, title: "Hook detection", copy: "Identify openings that earn attention and make viewers want the next sentence.", label: "Planned analysis" },
  { icon: Clapperboard, title: "Editorial scoring", copy: "Compare candidate moments using clear, useful signals—not a mysterious black box.", label: "Planned analysis" },
  { icon: Captions, title: "Short-ready output", copy: "Build polished vertical clips with readable animated captions and smart framing.", label: "Planned export" },
];

export default function LandingPage() {
  return (
    <main className="overflow-hidden">
      <header className="mx-auto flex max-w-7xl items-center justify-between px-6 py-6 lg:px-8">
        <Brand />
        <nav className="hidden items-center gap-8 text-sm text-zinc-400 md:flex" aria-label="Primary navigation">
          <Link href="#workflow" className="transition hover:text-white">How it works</Link>
          <Link href="#features" className="transition hover:text-white">Product</Link>
        </nav>
        <Button asChild variant="secondary" size="sm">
          <Link href="/dashboard">Open dashboard <ArrowRight className="h-3.5 w-3.5" /></Link>
        </Button>
      </header>

      <section className="relative mx-auto max-w-7xl px-6 pb-28 pt-20 text-center lg:px-8 lg:pb-36 lg:pt-28">
        <div className="pointer-events-none absolute left-1/2 top-10 -z-10 h-[32rem] w-[32rem] -translate-x-1/2 rounded-full bg-violet-700/10 blur-3xl" />
        <div className="mx-auto mb-7 inline-flex items-center gap-2 rounded-full border border-violet-400/20 bg-violet-400/[0.07] px-3 py-1.5 text-xs font-medium text-violet-200">
          <Sparkles className="h-3.5 w-3.5" /> AI video clipping workspace
        </div>
        <h1 className="mx-auto max-w-5xl text-balance text-5xl font-semibold leading-[0.98] tracking-[-0.055em] text-white sm:text-6xl lg:text-8xl">
          Find the moments <span className="bg-gradient-to-r from-violet-300 to-fuchsia-300 bg-clip-text text-transparent">worth watching.</span>
        </h1>
        <p className="mx-auto mt-7 max-w-2xl text-balance text-base leading-7 text-zinc-400 sm:text-lg">
          Howlix is being built to turn long-form video into focused, high-potential short clips—with stronger hooks, clear editorial signals, and less searching.
        </p>
        <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Button asChild size="lg">
            <Link href="/dashboard/new">Start Creating <ArrowRight className="h-4 w-4" /></Link>
          </Button>
          <Button asChild variant="ghost" size="lg">
            <Link href="#workflow"><Play className="h-4 w-4" /> See how it works</Link>
          </Button>
        </div>

        <div className="relative mx-auto mt-20 max-w-5xl rounded-[1.75rem] border border-white/10 bg-[#0b0a0f] p-2 shadow-2xl shadow-violet-950/30">
          <div className="rounded-[1.35rem] border border-white/[0.07] bg-[#0e0d13] p-5 text-left sm:p-7">
            <div className="flex items-center justify-between border-b border-white/[0.07] pb-5">
              <div>
                <p className="text-xs font-medium uppercase tracking-[0.18em] text-zinc-600">Editorial workspace</p>
                <h2 className="mt-1.5 text-lg font-medium text-white">One video. The right moments.</h2>
              </div>
              <div className="hidden items-center gap-2 rounded-full border border-white/10 px-3 py-1.5 text-xs text-zinc-400 sm:flex">
                <span className="h-1.5 w-1.5 rounded-full bg-violet-400" /> Foundation live
              </div>
            </div>
            <div className="grid gap-4 pt-5 md:grid-cols-[1.35fr_.65fr]">
              <div className="relative flex min-h-64 items-center justify-center overflow-hidden rounded-xl border border-white/[0.06] bg-[radial-gradient(circle_at_center,_rgba(124,58,237,.16),_transparent_55%)]">
                <div className="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-violet-400/50 to-transparent" />
                <span className="flex h-14 w-14 items-center justify-center rounded-full border border-violet-300/30 bg-violet-500/15 text-violet-200">
                  <Play className="ml-0.5 h-5 w-5" fill="currentColor" />
                </span>
              </div>
              <div className="space-y-3">
                {["Find the strongest opening", "Rank editorial potential", "Prepare a short-ready cut"].map((item, index) => (
                  <div key={item} className="flex items-start gap-3 rounded-xl border border-white/[0.06] bg-white/[0.025] p-4">
                    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-violet-500/15 text-violet-300">
                      <Check className="h-3 w-3" />
                    </span>
                    <div>
                      <p className="text-sm text-zinc-200">{item}</p>
                      <p className="mt-1 text-xs text-zinc-600">Stage {index + 1}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="workflow" className="border-y border-white/[0.07] bg-white/[0.018] py-24">
        <div className="mx-auto max-w-7xl px-6 lg:px-8">
          <p className="text-sm font-medium text-violet-300">A focused workflow</p>
          <h2 className="mt-3 max-w-2xl text-balance text-3xl font-semibold tracking-[-0.04em] text-white sm:text-5xl">From a long recording to the moments that matter.</h2>
          <div className="mt-14 grid gap-4 md:grid-cols-3">
            {steps.map((step) => (
              <article key={step.title} className="group rounded-2xl border border-white/[0.08] bg-black/20 p-6 transition hover:border-violet-400/25 hover:bg-white/[0.025]">
                <div className="flex items-center justify-between">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-500/10 text-violet-300"><step.icon className="h-4 w-4" /></span>
                  <span className="font-mono text-xs text-zinc-700">{step.number}</span>
                </div>
                <h3 className="mt-8 text-lg font-medium text-white">{step.title}</h3>
                <p className="mt-2 text-sm leading-6 text-zinc-500">{step.copy}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section id="features" className="mx-auto max-w-7xl px-6 py-24 lg:px-8 lg:py-32">
        <div className="grid gap-12 lg:grid-cols-[.75fr_1.25fr] lg:items-start">
          <div className="lg:sticky lg:top-12">
            <p className="text-sm font-medium text-violet-300">Built for judgment</p>
            <h2 className="mt-3 text-balance text-3xl font-semibold tracking-[-0.04em] text-white sm:text-5xl">Less timeline scrubbing. Better editorial choices.</h2>
            <p className="mt-5 max-w-lg text-base leading-7 text-zinc-500">The product roadmap centers on the hard part: deciding what is genuinely worth turning into a short.</p>
          </div>
          <div className="space-y-4">
            {previews.map((feature) => (
              <article key={feature.title} className="rounded-2xl border border-white/[0.08] bg-white/[0.025] p-6 sm:p-8">
                <div className="flex items-start gap-5">
                  <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-violet-400/15 bg-violet-500/10 text-violet-300"><feature.icon className="h-5 w-5" /></span>
                  <div>
                    <div className="flex flex-wrap items-center gap-3">
                      <h3 className="text-xl font-medium text-white">{feature.title}</h3>
                      <span className="rounded-full border border-white/10 px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.12em] text-zinc-500">{feature.label}</span>
                    </div>
                    <p className="mt-3 max-w-xl text-sm leading-6 text-zinc-500">{feature.copy}</p>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-6 pb-24 lg:px-8">
        <div className="relative overflow-hidden rounded-3xl border border-violet-400/15 bg-violet-500/[0.07] px-6 py-14 text-center sm:px-12">
          <div className="absolute left-1/2 top-0 -z-10 h-56 w-96 -translate-x-1/2 rounded-full bg-violet-500/20 blur-3xl" />
          <h2 className="text-balance text-3xl font-semibold tracking-[-0.04em] text-white sm:text-5xl">Start with the moments.</h2>
          <p className="mx-auto mt-4 max-w-xl text-zinc-400">Create your first project and securely upload the moments waiting inside.</p>
          <Button asChild size="lg" className="mt-8"><Link href="/dashboard/new">Start Creating <ArrowRight className="h-4 w-4" /></Link></Button>
        </div>
      </section>

      <footer className="border-t border-white/[0.07]">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-6 py-8 text-sm text-zinc-600 sm:flex-row sm:items-center sm:justify-between lg:px-8">
          <Brand />
          <p>A product by Wolvesgang Digital</p>
        </div>
      </footer>
    </main>
  );
}

