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
  bg: "#070707",          // --background  oklch(0.13 0 0)
  card: "#0f0f0f",        // --card        oklch(0.17 0 0)
  well: "#1b1b1b",
  border: "rgba(255,255,255,0.08)",
  fg: "#ffffff",
  muted: "#868686",       // --muted-foreground oklch(0.62 0 0)
  away: "#f47c6e",        // oklch(0.72 0.15 28)
  home: "#65b2f1",        // oklch(0.74 0.12 245)
  gold: "linear-gradient(180deg, #f4d580 0%, #ca933e 100%)", // --gold-gradient
};

const FONT_DIR = path.join(process.cwd(), "node_modules/@fontsource/inter/files");
let fonts: { name: string; data: Buffer; weight: 500 | 700 | 800; style: "normal" }[] | null = null;
/** Inter from @fontsource (Satori needs woff or ttf, not woff2). */
export function ogFonts() {
  fonts ??= ([500, 700, 800] as const).map(weight => ({
    name: "Inter", weight, style: "normal" as const,
    data: fs.readFileSync(path.join(FONT_DIR, `inter-latin-${weight}-normal.woff`)),
  }));
  return fonts;
}

/** components/site/logo.tsx's vault dial, flattened for Satori. The ticks
 *  are solid: a gradient stroke on a vertical line has a zero-width bounding
 *  box and paints nothing. */
function Dial({ size }: { size: number }) {
  const ticks = Array.from({ length: 40 }, (_, i) => i * 9);
  return (
    <svg width={size} height={size} viewBox="0 0 48 48">
      <defs>
        <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#f6dd90" />
          <stop offset="1" stopColor="#bf8532" />
        </linearGradient>
        <radialGradient id="f" cx=".5" cy=".38" r=".7">
          <stop offset="0" stopColor="#2e2e2e" />
          <stop offset="1" stopColor="#0d0d0d" />
        </radialGradient>
      </defs>
      <circle cx="24" cy="24" r="23" fill="url(#g)" />
      <circle cx="24" cy="24" r="19.5" fill="url(#f)" />
      {ticks.map(a => (
        <line key={a} x1="24" y1={a % 45 === 0 ? 6.5 : 5.5} x2="24" y2="8.5" stroke="#e2b862"
          strokeWidth={a % 45 === 0 ? 1.4 : 0.6} transform={`rotate(${a} 24 24)`} opacity={a % 45 === 0 ? 1 : 0.55} />
      ))}
      <circle cx="24" cy="24" r="9" fill="url(#g)" />
      <circle cx="24" cy="24" r="6.6" fill="url(#f)" />
      {[0, 120, 240].map(a => (
        <rect key={a} x="23" y="11.5" width="2" height="6" rx="1" fill="url(#g)" transform={`rotate(${a + 20} 24 24)`} />
      ))}
      <path d="M24 2.2 l1.6 2.6 h-3.2 z" fill="#f9efc9" />
    </svg>
  );
}

const goldText = { backgroundImage: C.gold, backgroundClip: "text", color: "transparent" } as const;

function Team({ abbrev, color, align }: { abbrev: string; color: string; align: "flex-start" | "flex-end" }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: align, width: 300 }}>
      <div style={{ fontSize: 132, fontWeight: 800, color, letterSpacing: "-0.04em", lineHeight: 1 }}>{abbrev}</div>
      <div style={{ fontSize: 30, fontWeight: 500, color: C.muted, marginTop: 10 }}>{nickname(teamName(abbrev))}</div>
    </div>
  );
}

function Score({ v, win }: { v: number; win: boolean }) {
  return (
    <div style={{ display: "flex", fontSize: 168, fontWeight: 800, lineHeight: 1, letterSpacing: "-0.04em", ...(win ? goldText : { color: "#5a5a5a" }) }}>
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
      backgroundImage: "radial-gradient(ellipse 900px 420px at 50% 0%, rgba(244,213,128,0.10), rgba(7,7,7,0))",
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
          <Dial size={60} />
          <div style={{ display: "flex", fontSize: 40, fontWeight: 700, letterSpacing: "-0.03em" }}>
            Fort<span style={{ marginLeft: 11, ...goldText }}>Knox</span>
          </div>
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
          <div style={{ width: 44, height: 10, borderRadius: 5, background: "#3a3a3a" }} />
          <Score v={G.hs} win={G.hs > G.as} />
        </div>
        <Team abbrev={G.home} color={C.home} align="flex-end" />
      </div>

      <div style={{ display: "flex", flexDirection: "column", padding: "26px 30px 30px", borderRadius: 24, background: C.card, border: `1px solid ${C.border}` }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ fontSize: 44, fontWeight: 800, color: C.away }}>{f2(G.axg)}</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.16em" }}>Expected goals</div>
          <div style={{ fontSize: 44, fontWeight: 800, color: C.home }}>{f2(G.hxg)}</div>
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
      backgroundImage: "radial-gradient(ellipse 900px 480px at 50% 30%, rgba(244,213,128,0.12), rgba(7,7,7,0))",
    }}>
      <Dial size={168} />
      <div style={{ display: "flex", fontSize: 108, fontWeight: 800, letterSpacing: "-0.04em", marginTop: 34, lineHeight: 1 }}>
        Fort<span style={{ marginLeft: 26, ...goldText }}>Knox</span>
      </div>
      <div style={{ fontSize: 36, fontWeight: 500, color: C.muted, marginTop: 26 }}>NHL expected goals, every game, shot by shot</div>
    </div>
  );
}
