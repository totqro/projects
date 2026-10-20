import { cn } from "@/lib/utils";
import { VaultDial } from "./logo";

// Rebrand samples (app/themes.css): a mark and a wordmark per candidate. All
// are rendered; CSS shows the one matching <html data-theme>.

export const BRANDS = [
  { key: "fortknox", name: "Fort Knox", note: "Current: vault gold" },
  { key: "royal", name: "Royal Road", note: "Violet + orchid, serif" },
  { key: "slot", name: "Slotline", note: "Navy ice + cyan, condensed" },
  { key: "fivehole", name: "Five Hole", note: "Scoreboard amber LED" },
  { key: "crease", name: "Crease", note: "Light box score, red line" },
  { key: "lamp", name: "Goal Lamp", note: "Graphite + red lamp" },
] as const;
export type BrandKey = (typeof BRANDS)[number]["key"];

const G = "var(--gold)";

/** The royal road: a pass cutting across the slot under a crown point. */
function RoyalMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={cn("shrink-0", className)} aria-hidden="true">
      <rect x="2" y="2" width="44" height="44" rx="12" fill="var(--card)" stroke={G} strokeOpacity=".5" />
      <path d="M12 30 L16 17 L24 25 L32 17 L36 30 Z" fill="url(#rr)" />
      <path d="M11 35 H37" stroke={G} strokeWidth="2.4" strokeLinecap="round" />
      <defs><linearGradient id="rr" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="oklch(0.9 0.07 315)" /><stop offset="1" stopColor="oklch(0.64 0.16 300)" /></linearGradient></defs>
    </svg>
  );
}

/** The slot: the house-shaped high-danger area in front of the net. */
function SlotMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={cn("shrink-0", className)} aria-hidden="true">
      <path d="M8 6 H40 V22 L24 42 L8 22 Z" fill="none" stroke={G} strokeWidth="3" strokeLinejoin="round" />
      <path d="M17 6 V12 H31 V6" fill="none" stroke={G} strokeWidth="2" opacity=".6" />
      <circle cx="24" cy="24" r="4" fill={G} />
    </svg>
  );
}

/** A 5 on a scoreboard's dot matrix. */
function FiveHoleMark({ className }: { className?: string }) {
  const rows = ["11111", "10000", "11110", "00001", "00001", "10001", "01110"];
  return (
    <svg viewBox="0 0 48 48" className={cn("shrink-0", className)} aria-hidden="true">
      <rect x="1" y="1" width="46" height="46" rx="8" fill="oklch(0.08 0 0)" stroke="oklch(1 0 0 / 0.1)" />
      {rows.flatMap((r, y) => [...r].map((c, x) => (
        <circle key={`${x}${y}`} cx={12 + x * 6} cy={6 + y * 6} r="2.2" fill={c === "1" ? G : "oklch(1 0 0 / 0.07)"} />
      )))}
    </svg>
  );
}

/** The goal crease: blue paint on the red goal line. */
function CreaseMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={cn("shrink-0", className)} aria-hidden="true">
      <path d="M10 14 A14 14 0 0 0 38 14 Z" fill="var(--home)" opacity=".85" />
      <path d="M4 14 H44" stroke={G} strokeWidth="3.5" strokeLinecap="round" />
      <rect x="18" y="6" width="12" height="8" rx="1.5" fill="none" stroke="var(--foreground)" strokeWidth="2" />
      <circle cx="24" cy="36" r="4" fill="var(--foreground)" />
    </svg>
  );
}

/** The goal lamp: a red dome, lit. */
function LampMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={cn("shrink-0", className)} aria-hidden="true">
      <defs><radialGradient id="gl" cx=".5" cy=".7" r=".6"><stop offset="0" stopColor="oklch(0.85 0.15 40)" /><stop offset="1" stopColor="oklch(0.56 0.22 25)" /></radialGradient></defs>
      <circle cx="24" cy="28" r="19" fill="oklch(0.66 0.22 27 / 0.18)" />
      <path d="M13 34 V27 A11 11 0 0 1 35 27 V34 Z" fill="url(#gl)" />
      <rect x="10" y="34" width="28" height="5" rx="2" fill="oklch(0.35 0.01 20)" />
      {[-60, -30, 0, 30, 60].map(a => (
        <line key={a} x1="24" y1="5" x2="24" y2="10" stroke={G} strokeWidth="2.2" strokeLinecap="round" transform={`rotate(${a} 24 28)`} />
      ))}
    </svg>
  );
}

const word = "font-[family-name:var(--font-display)] text-xl font-bold tracking-[-0.02em]";

/** Every candidate wordmark; themes.css shows the active one. */
export function BrandMarks() {
  return (
    <>
      <span data-brand="fortknox" className="items-center gap-2.5">
        <VaultDial className="size-8" />
        <span className={cn(word, "tracking-[-0.03em]")}>Fort <span className="gold-text">Knox</span></span>
      </span>
      <span data-brand="royal" className="items-center gap-2.5">
        <RoyalMark className="size-8" />
        <span className={cn(word, "font-semibold italic")}>Royal <span className="vault-gold">Road</span></span>
      </span>
      <span data-brand="slot" className="items-center gap-2">
        <SlotMark className="size-8" />
        <span className={cn(word, "text-2xl uppercase tracking-[0.02em]")}>Slot<span className="vault-gold">line</span></span>
      </span>
      <span data-brand="fivehole" className="items-center gap-2.5">
        <FiveHoleMark className="size-8" />
        <span className={cn(word, "text-2xl uppercase tracking-[0.04em]")}>Five <span className="vault-gold">Hole</span></span>
      </span>
      <span data-brand="crease" className="items-center gap-2">
        <CreaseMark className="size-8" />
        <span className={cn(word, "text-2xl tracking-[-0.01em]")}>Crease<span className="text-gold">.</span></span>
      </span>
      <span data-brand="lamp" className="items-center gap-2">
        <LampMark className="size-8" />
        <span className={cn(word, "font-extrabold uppercase tracking-[-0.01em]")}>Goal <span className="vault-gold">Lamp</span></span>
      </span>
    </>
  );
}
