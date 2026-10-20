import fs from "node:fs";
import path from "node:path";
import type { GameSummary } from "./types";
import { f2, longDate } from "./format";
import { nickname, teamName } from "./teams";

// The share card for a game page, drawn by Satori in scripts/og-images.tsx
// before every build. Satori reads neither oklch nor CSS variables, so the
// theme colours from globals.css are written out here in sRGB.
//
// Plain Node imports only (no "server-only", no @/ data layer): the script
// runs outside Next.

export const OG_SIZE = { width: 1200, height: 630 };

const C = {
  bg: "#030c17",          // --background  oklch(0.15 0.03 252)
  card: "#081523",        // --card        oklch(0.19 0.035 252)
  well: "#05101d",        // --well
  border: "rgba(255,255,255,0.08)",
  fg: "#ffffff",
  muted: "#8da1b3",       // --muted-foreground oklch(0.7 0.035 245)
  loser: "#495766",
  sep: "#243447",
  away: "#fd7562",        // oklch(0.72 0.17 30)
  home: "#a1bdf9",        // oklch(0.8 0.09 265)
  brand: "#6ce6f3",       // --brand oklch(0.86 0.11 205)
  gradient: "linear-gradient(180deg, #c8f9fc 0%, #16bee1 100%)", // --brand-gradient
  glow: "rgba(108,230,243,0.12)",
};

/** Barlow Condensed for the display type, Inter for the small print, both
 *  from @fontsource (Satori needs woff or ttf, not woff2). */
type Font = { name: string; data: Buffer; weight: 500 | 600 | 700; style: "normal" };
let fonts: Font[] | null = null;
export function ogFonts() {
  const file = (pkg: string, f: string) => fs.readFileSync(path.join(process.cwd(), "node_modules/@fontsource", pkg, "files", f));
  fonts ??= [
    ...([600, 700] as const).map(weight => ({ name: "Barlow", weight, style: "normal" as const, data: file("barlow-condensed", `barlow-condensed-latin-${weight}-normal.woff`) })),
    ...([500, 700] as const).map(weight => ({ name: "Inter", weight, style: "normal" as const, data: file("inter", `inter-latin-${weight}-normal.woff`) })),
  ];
  return fonts;
}

/** components/site/logo.tsx's slot mark, with the colour written out. */
function Mark({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48">
      <path d="M8 6 H40 V22 L24 42 L8 22 Z" fill="none" stroke={C.brand} strokeWidth="3" strokeLinejoin="round" />
      <path d="M17 6 V12 H31 V6" fill="none" stroke={C.brand} strokeWidth="2" opacity=".6" />
      <circle cx="24" cy="24" r="4" fill={C.brand} />
    </svg>
  );
}

const brandText = { backgroundImage: C.gradient, backgroundClip: "text", color: "transparent" } as const;
const display = { fontFamily: "Barlow", textTransform: "uppercase" } as const;

function Brand({ size }: { size: number }) {
  return (
    <div style={{ display: "flex", ...display, fontSize: size, fontWeight: 700, letterSpacing: "0.02em", lineHeight: 1 }}>
      High<span style={{ marginLeft: size * 0.24, ...brandText }}>Slot</span>
    </div>
  );
}

function Team({ abbrev, color, align }: { abbrev: string; color: string; align: "flex-start" | "flex-end" }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: align, width: 300 }}>
      <div style={{ ...display, fontSize: 168, fontWeight: 700, color, letterSpacing: "0.01em", lineHeight: 0.9 }}>{abbrev}</div>
      <div style={{ fontSize: 30, fontWeight: 500, color: C.muted, marginTop: 10 }}>{nickname(teamName(abbrev))}</div>
    </div>
  );
}

function Score({ v, win }: { v: number; win: boolean }) {
  return (
    <div style={{ display: "flex", ...display, fontSize: 200, fontWeight: 700, lineHeight: 0.9, ...(win ? brandText : { color: C.loser }) }}>
      {String(v)}
    </div>
  );
}

export function GameCard({ G }: { G: GameSummary }) {
  const total = G.axg + G.hxg;
  const awayShare = total > 0 ? G.axg / total : 0.5;
  const end = G.end === "REG" ? "Final" : `Final · ${G.end}`;
  const year = G.date.slice(0, 4);
  return (
    <div style={{
      width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "space-between",
      padding: "52px 64px 56px", background: C.bg, color: C.fg, fontFamily: "Inter",
      backgroundImage: `radial-gradient(ellipse 900px 420px at 50% 0%, ${C.glow}, rgba(3,12,23,0))`,
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <Mark size={60} />
          <Brand size={50} />
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
          <div style={{ fontSize: 28, fontWeight: 700 }}>{`${longDate(G.date)}, ${year}`}</div>
          <div style={{ fontSize: 24, fontWeight: 500, color: C.muted, marginTop: 4, textTransform: "uppercase", letterSpacing: "0.12em" }}>{end}</div>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <Team abbrev={G.away} color={C.away} align="flex-start" />
        <div style={{ display: "flex", alignItems: "center", gap: 36 }}>
          <Score v={G.as} win={G.as > G.hs} />
          <div style={{ width: 44, height: 10, borderRadius: 5, background: C.sep }} />
          <Score v={G.hs} win={G.hs > G.as} />
        </div>
        <Team abbrev={G.home} color={C.home} align="flex-end" />
      </div>

      <div style={{ display: "flex", flexDirection: "column", padding: "26px 30px 30px", borderRadius: 24, background: C.card, border: `1px solid ${C.border}` }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ ...display, fontSize: 56, fontWeight: 700, color: C.away, lineHeight: 1 }}>{f2(G.axg)}</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.16em" }}>Expected goals</div>
          <div style={{ ...display, fontSize: 56, fontWeight: 700, color: C.home, lineHeight: 1 }}>{f2(G.hxg)}</div>
        </div>
        <div style={{ display: "flex", height: 22, marginTop: 16, borderRadius: 11, background: C.well, gap: 6 }}>
          <div style={{ width: `${(awayShare * 100).toFixed(2)}%`, borderRadius: 11, background: C.away }} />
          <div style={{ flexGrow: 1, borderRadius: 11, background: C.home }} />
        </div>
      </div>
    </div>
  );
}

/** The site-wide card: home, team and player pages, and games from earlier
 *  seasons (only the current season gets a card of its own). */
export function SiteCard() {
  return (
    <div style={{
      width: "100%", height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
      background: C.bg, color: C.fg, fontFamily: "Inter",
      backgroundImage: `radial-gradient(ellipse 900px 480px at 50% 30%, ${C.glow}, rgba(3,12,23,0))`,
    }}>
      <Mark size={168} />
      <div style={{ display: "flex", marginTop: 30 }}><Brand size={150} /></div>
      <div style={{ fontSize: 36, fontWeight: 500, color: C.muted, marginTop: 26 }}>NHL expected goals, every game, shot by shot</div>
    </div>
  );
}
