import Image from "next/image";
import { AccountMenu } from "@/components/account-menu";

import { Brand } from "@/components/brand";

export function TopNavigation() {
  return (
    <header className="sticky top-0 z-40 flex h-[4.5rem] items-center justify-between border-b border-white/[0.07] bg-[#08070b]/80 px-5 backdrop-blur-xl sm:px-8">
      <Brand compact className="md:hidden" />
      <div className="hidden items-center gap-2.5 md:flex">
        <Image src="/brand/howlix-icon-64.png" alt="" width={64} height={64} className="h-6 w-6 object-contain" aria-hidden="true" />
        <div><p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-zinc-500">Howlix workspace</p><p className="mt-0.5 text-[11px] text-zinc-700">Private creative studio</p></div>
      </div>
      <AccountMenu />
    </header>
  );
}

