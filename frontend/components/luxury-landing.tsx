import Image from "next/image";
import Link from "next/link";
import {
  ArrowRight,
  Captions,
  Check,
  ChevronDown,
  Clapperboard,
  Film,
  Focus,
  Play,
  Scissors,
  ShieldCheck,
  Sparkles,
  Upload,
  WandSparkles,
} from "lucide-react";

import { Brand } from "@/components/brand";
import { Button } from "@/components/ui/button";

const studioImage = "https://images.pexels.com/photos/11063289/pexels-photo-11063289.jpeg?auto=compress&cs=tinysrgb&w=1800";
const editorImage = "https://images.pexels.com/photos/8102674/pexels-photo-8102674.jpeg?auto=compress&cs=tinysrgb&w=1400";
const gradingImage = "https://images.pexels.com/photos/30229850/pexels-photo-30229850.jpeg?auto=compress&cs=tinysrgb&w=1400";

const workflow = [
  { number: "01", icon: Upload, title: "Bring your video", copy: "Upload a file or paste a YouTube link. Your video stays private." },
  { number: "02", icon: Sparkles, title: "Find the gold", copy: "Howlix reads the story and surfaces the strongest standalone moments." },
  { number: "03", icon: Scissors, title: "Make it yours", copy: "Approve, fine-tune, frame, caption, and export a polished short." },
];

export default function LuxuryLanding() {
  return (
    <main className="luxury-page overflow-hidden bg-[#070609] text-white">
      <header className="fixed inset-x-0 top-0 z-50 px-4 pt-4 sm:px-6">
        <div className="mx-auto flex max-w-7xl items-center justify-between rounded-2xl border border-white/[0.08] bg-[#09080c]/75 px-4 py-3 shadow-2xl shadow-black/20 backdrop-blur-xl sm:px-5">
          <Brand />
          <nav className="hidden items-center gap-7 text-xs text-zinc-400 md:flex" aria-label="Primary navigation">
            <Link href="#experience" className="transition hover:text-white">How it works</Link>
            <Link href="#craft" className="transition hover:text-white">The product</Link>
            <Link href="#privacy" className="transition hover:text-white">Private by design</Link>
          </nav>
          <Button asChild size="sm" className="rounded-full px-4">
            <Link href="/auth/login">Sign in <ArrowRight className="h-3.5 w-3.5" /></Link>
          </Button>
        </div>
      </header>

      <section className="relative min-h-screen px-5 pb-20 pt-36 sm:px-8 lg:pb-28 lg:pt-44">
        <div className="luxury-orb luxury-orb-one" />
        <div className="luxury-orb luxury-orb-two" />
        <div className="mx-auto grid max-w-7xl gap-14 lg:grid-cols-[.9fr_1.1fr] lg:items-center">
          <div className="relative z-10 luxury-reveal">
            <div className="inline-flex items-center gap-2 rounded-full border border-violet-300/15 bg-violet-300/[0.07] px-3 py-1.5 text-[11px] font-medium uppercase tracking-[0.16em] text-violet-200">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-violet-300" /> Private beta is open
            </div>
            <h1 className="mt-7 max-w-3xl text-balance text-5xl font-medium leading-[.94] tracking-[-0.065em] text-white sm:text-7xl lg:text-[5.6rem]">
              Your best moments, <span className="luxury-gradient-text font-serif italic">beautifully cut.</span>
            </h1>
            <p className="mt-7 max-w-xl text-balance text-base leading-7 text-zinc-400 sm:text-lg">
              Howlix turns long conversations into sharp, vertical clips—finding the hook, keeping the story, and finishing every frame.
            </p>
            <div className="mt-9 flex flex-col gap-3 sm:flex-row">
              <Button asChild size="lg" className="rounded-full px-7">
                <Link href="/auth/signup">Start creating <ArrowRight className="h-4 w-4" /></Link>
              </Button>
              <Button asChild variant="ghost" size="lg" className="rounded-full border border-white/[0.08] px-7">
                <Link href="#experience"><Play className="h-4 w-4" /> See the flow</Link>
              </Button>
            </div>
            <div className="mt-10 flex flex-wrap gap-x-6 gap-y-3 text-xs text-zinc-500">
              {["No editing skills needed", "Private video storage", "Download-ready MP4"].map((item) => (
                <span key={item} className="flex items-center gap-2"><Check className="h-3.5 w-3.5 text-violet-300" /> {item}</span>
              ))}
            </div>
          </div>

          <div className="relative mx-auto w-full max-w-3xl luxury-reveal luxury-delay-1">
            <div className="relative aspect-[1.05/1] overflow-hidden rounded-[2rem] border border-white/10 bg-zinc-950 shadow-[0_40px_120px_rgba(0,0,0,.55)]">
              <Image src={studioImage} alt="A creator's video editing studio" fill priority sizes="(max-width: 1024px) 100vw, 55vw" className="object-cover opacity-80" />
              <div className="absolute inset-0 bg-gradient-to-t from-[#070609] via-transparent to-black/20" />
              <div className="absolute inset-0 bg-[linear-gradient(115deg,rgba(124,58,237,.2),transparent_45%)]" />
              <div className="absolute bottom-5 left-5 right-5 rounded-2xl border border-white/10 bg-black/65 p-4 backdrop-blur-xl sm:bottom-7 sm:left-7 sm:right-auto sm:w-72">
                <div className="flex items-center justify-between text-[10px] uppercase tracking-[.14em] text-zinc-500"><span>Strong moment found</span><span className="text-violet-300">00:42</span></div>
                <p className="mt-3 text-sm leading-6 text-white">“The mistake wasn’t starting too late. It was waiting to feel ready.”</p>
                <div className="mt-4 h-1 overflow-hidden rounded-full bg-white/10"><div className="h-full w-4/5 rounded-full bg-gradient-to-r from-violet-500 to-fuchsia-400" /></div>
              </div>
            </div>
            <div className="luxury-float absolute -bottom-8 right-4 w-40 overflow-hidden rounded-[1.5rem] border border-white/15 bg-[#111015] p-2 shadow-2xl shadow-black/50 sm:-right-7 sm:bottom-8 sm:w-52">
              <div className="relative aspect-[9/16] overflow-hidden rounded-[1.1rem]">
                <Image src={editorImage} alt="A vertical clip being edited" fill sizes="210px" className="object-cover" />
                <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-black/10" />
                <p className="absolute inset-x-3 bottom-8 text-center text-sm font-semibold uppercase leading-tight text-white">Make the moment<br /><span className="rounded bg-violet-500 px-1.5">impossible to skip.</span></p>
                <span className="absolute left-3 top-3 rounded-full border border-white/15 bg-black/45 px-2 py-1 text-[9px] uppercase tracking-wider text-white/80 backdrop-blur">9:16 ready</span>
              </div>
            </div>
            <div className="luxury-float-reverse absolute -left-3 top-8 rounded-2xl border border-white/10 bg-black/65 px-4 py-3 shadow-xl backdrop-blur-xl sm:-left-8">
              <div className="flex items-center gap-3"><span className="flex h-9 w-9 items-center justify-center rounded-full bg-violet-500/20 text-violet-200"><WandSparkles className="h-4 w-4" /></span><div><p className="text-xs font-medium text-white">Story complete</p><p className="mt-1 text-[10px] text-zinc-500">Strong hook · Clear payoff</p></div></div>
            </div>
          </div>
        </div>
        <a href="#experience" aria-label="Scroll to how it works" className="absolute bottom-5 left-1/2 hidden -translate-x-1/2 flex-col items-center gap-2 text-[10px] uppercase tracking-[.2em] text-zinc-600 lg:flex">Explore <ChevronDown className="h-4 w-4 animate-bounce" /></a>
      </section>

      <section className="border-y border-white/[0.06] bg-white/[0.018] py-5">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-center gap-x-10 gap-y-3 px-6 text-[10px] font-medium uppercase tracking-[.22em] text-zinc-600 sm:justify-between">
          <span>Podcasts</span><span className="text-violet-500/60">✦</span><span>Interviews</span><span className="text-violet-500/60">✦</span><span>Webinars</span><span className="text-violet-500/60">✦</span><span>Founder stories</span><span className="text-violet-500/60">✦</span><span>Tutorials</span>
        </div>
      </section>

      <section id="experience" className="mx-auto max-w-7xl px-5 py-28 sm:px-8 lg:py-36">
        <div className="grid gap-12 lg:grid-cols-[.72fr_1.28fr] lg:items-end">
          <div><p className="text-xs font-medium uppercase tracking-[.2em] text-violet-300">One effortless flow</p><h2 className="mt-5 text-balance text-4xl font-medium tracking-[-0.05em] text-white sm:text-6xl">From two hours to <span className="font-serif italic text-zinc-400">the right sixty seconds.</span></h2></div>
          <p className="max-w-xl text-base leading-7 text-zinc-500 lg:justify-self-end">You stay in control of every choice. Howlix does the searching, scoring, framing, and caption timing—then lets you approve the result.</p>
        </div>
        <div className="mt-16 grid gap-px overflow-hidden rounded-[1.75rem] border border-white/[0.08] bg-white/[0.08] md:grid-cols-3">
          {workflow.map((step) => (
            <article key={step.title} className="group relative bg-[#0a090d] p-7 transition duration-500 hover:bg-[#100e15] sm:p-9">
              <span className="absolute right-7 top-7 font-serif text-5xl italic text-white/[0.035]">{step.number}</span>
              <span className="flex h-11 w-11 items-center justify-center rounded-xl border border-violet-300/15 bg-violet-400/[0.08] text-violet-200 transition duration-500 group-hover:scale-110 group-hover:bg-violet-400/15"><step.icon className="h-5 w-5" /></span>
              <h3 className="mt-14 text-xl font-medium text-white">{step.title}</h3>
              <p className="mt-3 text-sm leading-6 text-zinc-500">{step.copy}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="craft" className="relative border-y border-white/[0.06] bg-[#0a090d] py-28 lg:py-36">
        <div className="mx-auto grid max-w-7xl gap-14 px-5 sm:px-8 lg:grid-cols-[1.05fr_.95fr] lg:items-center">
          <div className="relative min-h-[34rem] overflow-hidden rounded-[2rem] border border-white/10">
            <Image src={gradingImage} alt="Professional video color editing controls" fill sizes="(max-width: 1024px) 100vw, 50vw" className="object-cover" />
            <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/10 to-transparent" />
            <div className="absolute bottom-6 left-6 right-6 rounded-2xl border border-white/10 bg-black/55 p-5 backdrop-blur-xl">
              <div className="flex items-center justify-between"><p className="text-xs uppercase tracking-[.16em] text-zinc-400">Clip score</p><p className="font-serif text-3xl italic text-violet-200">88</p></div>
              <div className="mt-4 grid grid-cols-3 gap-2 text-[10px] text-zinc-500"><span>Hook <b className="block pt-1 text-zinc-200">Strong</b></span><span>Story <b className="block pt-1 text-zinc-200">Complete</b></span><span>Clarity <b className="block pt-1 text-zinc-200">High</b></span></div>
            </div>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-[.2em] text-violet-300">Taste, built in</p>
            <h2 className="mt-5 text-balance text-4xl font-medium tracking-[-0.05em] text-white sm:text-6xl">Not every loud moment is a <span className="font-serif italic text-zinc-400">good moment.</span></h2>
            <p className="mt-6 max-w-xl text-base leading-7 text-zinc-500">Howlix looks for a real opening, a complete thought, and a satisfying finish. It recommends fewer, stronger clips instead of filling your screen with noise.</p>
            <div className="mt-10 space-y-3">
              {["Hooks supported by what was actually said", "Clear scores you can understand", "Easy approval, editing, and rejection"].map((item) => <div key={item} className="flex items-center gap-3 rounded-xl border border-white/[0.07] bg-white/[0.025] px-4 py-3 text-sm text-zinc-300"><Check className="h-4 w-4 text-violet-300" /> {item}</div>)}
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-28 sm:px-8 lg:py-36">
        <div className="grid gap-5 lg:grid-cols-3">
          <article className="group relative overflow-hidden rounded-[1.75rem] border border-white/[0.08] bg-gradient-to-br from-violet-500/10 to-transparent p-7 lg:col-span-2 sm:p-9">
            <Captions className="h-5 w-5 text-violet-300" /><h3 className="mt-16 max-w-lg text-3xl font-medium tracking-[-0.04em]">Captions that land on the word—not somewhere near it.</h3><p className="mt-4 max-w-lg text-sm leading-6 text-zinc-500">Choose clean, bold, or karaoke styling with timing taken directly from your video.</p>
            <div className="mt-10 rounded-2xl border border-white/10 bg-black/50 p-6 text-center text-2xl font-semibold uppercase sm:text-4xl">Ideas deserve to be <span className="rounded-md bg-violet-500 px-2 py-1">seen.</span></div>
          </article>
          <article className="rounded-[1.75rem] border border-white/[0.08] bg-white/[0.025] p-7 sm:p-9"><Focus className="h-5 w-5 text-violet-300" /><h3 className="mt-16 text-3xl font-medium tracking-[-0.04em]">Keep the speaker in frame.</h3><p className="mt-4 text-sm leading-6 text-zinc-500">Smart vertical framing follows the conversation, with a reliable center-crop fallback.</p></article>
          <article id="privacy" className="rounded-[1.75rem] border border-white/[0.08] bg-white/[0.025] p-7 sm:p-9"><ShieldCheck className="h-5 w-5 text-violet-300" /><h3 className="mt-16 text-3xl font-medium tracking-[-0.04em]">Private by default.</h3><p className="mt-4 text-sm leading-6 text-zinc-500">Only you can open your videos and downloads. Delete them whenever you are finished.</p></article>
          <article className="relative overflow-hidden rounded-[1.75rem] border border-white/[0.08] bg-[#100e15] p-7 lg:col-span-2 sm:p-9"><Film className="h-5 w-5 text-violet-300" /><h3 className="mt-16 max-w-lg text-3xl font-medium tracking-[-0.04em]">One idea. Every screen.</h3><p className="mt-4 max-w-lg text-sm leading-6 text-zinc-500">Make vertical, square, or landscape clips in 720p or 1080p, ready to preview and download.</p><div className="absolute -bottom-14 right-10 hidden gap-3 sm:flex"><span className="h-40 w-24 rotate-[-6deg] rounded-xl border border-violet-300/20 bg-violet-500/10" /><span className="h-36 w-36 rotate-3 rounded-xl border border-white/10 bg-white/[0.04]" /><span className="h-28 w-48 translate-y-8 rotate-[-2deg] rounded-xl border border-white/10 bg-white/[0.03]" /></div></article>
        </div>
      </section>

      <section className="px-5 pb-24 sm:px-8">
        <div className="relative mx-auto max-w-7xl overflow-hidden rounded-[2rem] border border-violet-300/15 bg-[#100c19] px-6 py-20 text-center sm:px-12 lg:py-28">
          <div className="luxury-orb luxury-orb-cta" />
          <Clapperboard className="mx-auto h-6 w-6 text-violet-300" />
          <h2 className="relative mx-auto mt-6 max-w-3xl text-balance text-4xl font-medium tracking-[-0.055em] sm:text-6xl">The story is already there. <span className="font-serif italic text-violet-200">Find its best cut.</span></h2>
          <p className="relative mx-auto mt-5 max-w-xl text-sm leading-7 text-zinc-400 sm:text-base">Create your first project and turn a long video into something people want to finish.</p>
          <Button asChild size="lg" className="relative mt-9 rounded-full px-8"><Link href="/auth/signup">Create your free account <ArrowRight className="h-4 w-4" /></Link></Button>
        </div>
      </section>

      <footer className="border-t border-white/[0.07]">
        <div className="mx-auto flex max-w-7xl flex-col gap-5 px-6 py-9 text-xs text-zinc-600 sm:flex-row sm:items-center sm:justify-between lg:px-8">
          <div><Brand /><p className="mt-2">A product by Wolvesgang Digital</p></div>
          <div className="flex flex-wrap gap-5"><Link href="/auth/login" className="hover:text-white">Sign in</Link><a href="https://www.pexels.com" target="_blank" rel="noreferrer" className="hover:text-white">Photography via Pexels</a></div>
        </div>
      </footer>
    </main>
  );
}
