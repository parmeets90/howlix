import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl border border-transparent text-sm font-semibold tracking-[-0.01em] transition-[transform,background-color,border-color,box-shadow,color] duration-200 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400 focus-visible:ring-offset-2 focus-visible:ring-offset-[#08070b] active:translate-y-px disabled:pointer-events-none disabled:opacity-45 motion-safe:hover:-translate-y-0.5",
  {
    variants: {
      variant: {
        default: "border-violet-400/20 bg-gradient-to-b from-violet-500 to-violet-700 text-white shadow-[0_12px_32px_rgba(91,33,182,.28),inset_0_1px_0_rgba(255,255,255,.2)] hover:from-violet-400 hover:to-violet-600 hover:shadow-[0_16px_36px_rgba(109,40,217,.34),inset_0_1px_0_rgba(255,255,255,.24)]",
        secondary: "border-white/10 bg-white/[0.055] text-zinc-100 shadow-sm shadow-black/20 hover:border-white/15 hover:bg-white/[0.09]",
        ghost: "text-zinc-400 hover:bg-white/[0.055] hover:text-white",
        outline: "border-white/15 bg-black/10 text-zinc-100 hover:border-violet-400/50 hover:bg-violet-500/[0.08]",
      },
      size: {
        default: "h-11 px-5",
        sm: "h-9 rounded-lg px-3.5 text-xs",
        lg: "h-12 px-6 text-base",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };

