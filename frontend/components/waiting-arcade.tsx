"use client";

import { useState } from "react";
import { Eye, Gamepad2, Sparkles, Trophy } from "lucide-react";

import { cn } from "@/lib/utils";

const CELLS = Array.from({ length: 9 }, (_, index) => index);

export function WaitingArcade({ className }: { className?: string }) {
  const [game, setGame] = useState<"spark" | "odd">("spark");
  const [target, setTarget] = useState(4);
  const [score, setScore] = useState(0);
  const [round, setRound] = useState(0);
  const [message, setMessage] = useState("Tap the glowing spark.");
  const oddCell = (round * 5 + 2) % CELLS.length;

  function tapSpark(index: number) {
    if (index !== target) {
      setMessage("Almost — find the bright one.");
      return;
    }
    setScore((value) => value + 1);
    setTarget((value) => (value * 5 + 3) % CELLS.length);
    setMessage("Nice! It moved again.");
  }

  function chooseOdd(index: number) {
    if (index !== oddCell) {
      setMessage("Look closely — one shape is different.");
      return;
    }
    setScore((value) => value + 1);
    setRound((value) => value + 1);
    setMessage("Sharp eyes! Here is another.");
  }

  return (
    <section className={cn("mt-5 overflow-hidden rounded-2xl border border-violet-300/15 bg-gradient-to-br from-violet-500/[0.09] to-black/20 p-4", className)} aria-label="While you wait mini games">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><p className="flex items-center gap-2 text-xs font-semibold text-violet-100"><Gamepad2 className="h-4 w-4 text-violet-300" /> A tiny game while you wait</p><p className="mt-1 text-[11px] text-zinc-500">Your video keeps moving in the background.</p></div>
        <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-300/15 bg-amber-300/[0.07] px-2.5 py-1 text-[10px] font-semibold text-amber-100"><Trophy className="h-3 w-3" /> {score}</span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-1 rounded-xl border border-white/[0.07] bg-black/20 p-1" role="tablist" aria-label="Choose a mini game">
        <button type="button" role="tab" aria-selected={game === "spark"} onClick={() => { setGame("spark"); setMessage("Tap the glowing spark."); }} className={cn("flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-[11px] font-medium transition", game === "spark" ? "bg-white/[0.09] text-white" : "text-zinc-600 hover:text-zinc-300")}><Sparkles className="h-3.5 w-3.5" /> Catch the spark</button>
        <button type="button" role="tab" aria-selected={game === "odd"} onClick={() => { setGame("odd"); setMessage("Which shape is different?"); }} className={cn("flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-[11px] font-medium transition", game === "odd" ? "bg-white/[0.09] text-white" : "text-zinc-600 hover:text-zinc-300")}><Eye className="h-3.5 w-3.5" /> Odd one out</button>
      </div>

      <div className="mx-auto mt-4 grid max-w-56 grid-cols-3 gap-2">
        {CELLS.map((index) => {
          const highlighted = game === "spark" ? index === target : index === oddCell;
          return <button key={`${game}-${index}`} type="button" aria-label={game === "spark" ? `Spark tile ${index + 1}` : `Shape tile ${index + 1}`} onClick={() => game === "spark" ? tapSpark(index) : chooseOdd(index)} className={cn("flex aspect-square items-center justify-center rounded-xl border bg-black/20 text-base transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400", highlighted ? "border-violet-300/35 bg-violet-400/15 text-violet-100 shadow-[0_0_24px_rgba(139,92,246,.18)] hover:scale-105" : "border-white/[0.07] text-zinc-700 hover:border-white/15 hover:bg-white/[0.04]")}><span aria-hidden="true">{game === "spark" ? (highlighted ? "✦" : "·") : (highlighted ? "◆" : "●")}</span></button>;
        })}
      </div>
      <p className="mt-3 text-center text-[11px] text-zinc-500" aria-live="polite">{message}</p>
    </section>
  );
}
