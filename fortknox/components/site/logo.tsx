import { cn } from "@/lib/utils";

/** The High Slot mark: the house-shaped slot in front of the net, with the
 *  net's mouth at the top and a puck in the high slot. */
export function SlotMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={cn("shrink-0", className)} aria-hidden="true">
      <path d="M8 6 H40 V22 L24 42 L8 22 Z" fill="none" stroke="var(--brand)" strokeWidth="3" strokeLinejoin="round" />
      <path d="M17 6 V12 H31 V6" fill="none" stroke="var(--brand)" strokeWidth="2" opacity=".6" />
      <circle cx="24" cy="24" r="4" fill="var(--brand)" />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 whitespace-nowrap", className)}>
      <SlotMark className="size-8" />
      <span className="font-[family-name:var(--font-display)] text-2xl font-extrabold uppercase tracking-[0.03em]">
        High <span className="brand-text">Slot</span>
      </span>
    </span>
  );
}
