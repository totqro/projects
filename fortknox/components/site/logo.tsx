import { cn } from "@/lib/utils";

/** The Fort Knox mark: a vault door's combination dial in gold. */
export function VaultDial({ className }: { className?: string }) {
  const ticks = Array.from({ length: 40 }, (_, i) => i * 9);
  return (
    <svg viewBox="0 0 48 48" className={cn("shrink-0", className)} aria-hidden="true">
      <defs>
        <linearGradient id="fk-gold" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="oklch(0.9 0.1 92)" />
          <stop offset="1" stopColor="oklch(0.66 0.12 72)" />
        </linearGradient>
        <radialGradient id="fk-face" cx=".5" cy=".38" r=".7">
          <stop offset="0" stopColor="oklch(0.3 0 0)" />
          <stop offset="1" stopColor="oklch(0.16 0 0)" />
        </radialGradient>
      </defs>
      <circle cx="24" cy="24" r="23" fill="url(#fk-gold)" />
      <circle cx="24" cy="24" r="19.5" fill="url(#fk-face)" />
      {ticks.map(a => (
        <line key={a} x1="24" y1={a % 45 === 0 ? 6.5 : 5.5} x2="24" y2="8.5"
          stroke="url(#fk-gold)" strokeWidth={a % 45 === 0 ? 1.4 : 0.6}
          transform={`rotate(${a} 24 24)`} opacity={a % 45 === 0 ? 1 : 0.55} />
      ))}
      <circle cx="24" cy="24" r="9" fill="url(#fk-gold)" />
      <circle cx="24" cy="24" r="6.6" fill="url(#fk-face)" />
      {[0, 120, 240].map(a => (
        <rect key={a} x="23" y="11.5" width="2" height="6" rx="1" fill="url(#fk-gold)" transform={`rotate(${a + 20} 24 24)`} />
      ))}
      <path d="M24 2.2 l1.6 2.6 h-3.2 z" fill="oklch(0.95 0.05 95)" />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <VaultDial className="size-8" />
      <span className="font-[family-name:var(--font-display)] text-xl font-bold tracking-[-0.03em]">
        Fort <span className="gold-text">Knox</span>
      </span>
    </span>
  );
}
