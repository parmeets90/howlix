import { cn } from "@/lib/utils";

export function StatusIndicator({ status, className }: { status: "draft"; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border border-amber-300/15 bg-amber-300/[0.08] px-2.5 py-1 text-xs font-medium capitalize text-amber-200",
        className,
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-amber-300" />
      {status}
    </span>
  );
}

