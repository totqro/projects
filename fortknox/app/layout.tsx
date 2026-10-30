import type { Metadata, Viewport } from "next";
import Link from "next/link";
import "@fontsource/big-shoulders-display/700";
import "@fontsource/big-shoulders-display/800";
import "@fontsource/ibm-plex-sans/400";
import "@fontsource/ibm-plex-sans/500";
import "@fontsource/ibm-plex-sans/600";
import "@fontsource/ibm-plex-sans/700";
import { Barlow, Big_Shoulders } from "next/font/google";
import "./globals.css";
import { currentSeason, seasons } from "@/lib/data";
import { Wordmark } from "@/components/site/logo";
import { SeasonSelect, SiteNav } from "@/components/site/nav";
import { PaletteToggle, THEME_SCRIPT, ThemeToggle } from "@/components/site/theme";
import { SiteSearch } from "@/components/site/search";
import { Trail } from "@/components/site/trail";
import { TooltipProvider } from "@/components/ui/tooltip";

// The two faces, downloaded at build time and served from the site: Big
// Shoulders for headings and scores, Barlow for everything else.
const sans = Barlow({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-barlow", display: "swap" });
const display = Big_Shoulders({ subsets: ["latin"], weight: ["700", "800", "900"], variable: "--font-big-shoulders", display: "swap", adjustFontFallback: false });

export const metadata: Metadata = {
  metadataBase: new URL("https://highslot.web.app"),
  title: { default: "High Slot · NHL expected goals", template: "%s · High Slot" },
  description: "Every NHL game scored shot by shot with a full-data expected-goals model: game sheets, team and player xG, goalie GSAx. Updated after every game.",
  icons: { icon: "/icon.svg" },
  // Pages that set their own openGraph replace this whole object, so the game
  // pages name their image again (app/game/[id]/page.tsx).
  openGraph: { siteName: "High Slot", images: [{ url: "/og/site.png", width: 1200, height: 630, alt: "High Slot" }] },
  twitter: { card: "summary_large_image", images: ["/og/site.png"] },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0b1220" },
    { media: "(prefers-color-scheme: light)", color: "#14213d" },
  ],
  colorScheme: "dark light",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const cur = currentSeason();
  return (
    <html lang="en" className={`light ${sans.variable} ${display.variable}`} suppressHydrationWarning>
      <head>
        {/* Picks the theme before first paint, so light readers see no flash of dark. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-dvh">
        <Trail />
        <TooltipProvider delayDuration={150}>
          <header className="slot-mast">
            {/* Logo and sections left; search, season, palette and theme right. Under md the
                sections drop to their own row. */}
            <div className="mx-auto grid max-w-[1180px] grid-cols-[auto_1fr] items-center gap-x-8 gap-y-1 px-4 py-2.5 xl:grid-cols-[auto_1fr_auto]">
              <Link href="/" aria-label="High Slot home" className="col-start-1 row-start-1 justify-self-start rounded-lg">
                <Wordmark />
              </Link>
              <div className="col-span-2 col-start-1 row-start-2 -ml-2.5 overflow-x-auto xl:col-span-1 xl:col-start-2 xl:row-start-1 xl:ml-0">
                <SiteNav current={cur} />
              </div>
              <div className="col-start-2 row-start-1 flex items-center gap-6 justify-self-end xl:col-start-3">
                <div className="max-sm:hidden"><SiteSearch season={cur} /></div>
                <SeasonSelect seasons={seasons()} current={cur} />
                <span className="flex gap-3 max-sm:hidden"><PaletteToggle /><ThemeToggle /></span>
              </div>
              {/* A phone: search gets its own row, the toggles go to the footer. */}
              <div className="col-span-2 row-start-3 pb-1 sm:hidden"><SiteSearch season={cur} wide /></div>
            </div>
          </header>
          <main className="mx-auto max-w-[1180px] px-4 pb-16 pt-6">{children}</main>
          <footer className="mx-auto flex max-w-[1180px] flex-wrap justify-between gap-x-6 gap-y-2 px-4 pb-10 text-xs text-muted-foreground">
            <span>Data from the NHL&apos;s public play-by-play and shift charts, scored after every game. Not affiliated with the NHL.</span>
            <span className="flex gap-1 sm:hidden"><PaletteToggle /><ThemeToggle /></span>
            <nav aria-label="Site" className="flex flex-wrap gap-x-4 gap-y-1">
              <Link href="/about" className="hover:text-foreground">About</Link>
              <Link href="/about#glossary" className="hover:text-foreground">Glossary</Link>
              <Link href="/model" className="hover:text-foreground">Model</Link>
              <Link href="/privacy" className="hover:text-foreground">Privacy</Link>
              <a href="mailto:highslotanalytics@gmail.com?subject=High%20Slot" className="hover:text-foreground">Contact</a>
            </nav>
          </footer>
        </TooltipProvider>
      </body>
    </html>
  );
}
