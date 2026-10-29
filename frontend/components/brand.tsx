import Image from "next/image";
import Link from "next/link";

import { cn } from "@/lib/utils";

export function Brand({ compact = false, className }: { compact?: boolean; className?: string }) {
  return (
    <Link href="/" className={cn("inline-flex items-center", className)} aria-label="Howlix home">
      {compact ? (
        <Image
          src="/brand/howlix-icon-64.png"
          alt="Howlix wolf emblem"
          width={64}
          height={64}
          className="h-9 w-9 object-contain"
        />
      ) : (
        <Image
          src="/brand/howlix-logo-dark.svg"
          alt="Howlix by Wolvesgang Digital"
          width={920}
          height={230}
          className="h-auto w-[154px] sm:w-[166px]"
          unoptimized
        />
      )}
    </Link>
  );
}

