import * as React from "react";

import { cn } from "@/lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "flex h-11 w-full rounded-xl border border-white/10 bg-black/25 px-3.5 text-sm text-white shadow-inner shadow-black/10 outline-none transition-[border-color,box-shadow,background-color] placeholder:text-zinc-600 hover:border-white/[0.16] focus:border-violet-400/70 focus:bg-black/35 focus:ring-4 focus:ring-violet-500/10 disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

