import type { Metadata, Viewport } from "next";
import Link from "next/link";
import "@fontsource/big-shoulders-display/700";
import "@fontsource/big-shoulders-display/800";
import "@fontsource/ibm-plex-sans/400";
import "@fontsource/ibm-plex-sans/500";
import "@fontsource/ibm-plex-sans/600";
import "@fontsource/ibm-plex-sans/700";
import "./globals.css";
import { currentSeason, seasons } from "@/lib/data";
import { Wordmark } from "@/components/site/logo";
import { SeasonSelect, SiteNav } from "@/components/site/nav";
import { PaletteToggle, THEME_SCRIPT, ThemeToggle } from "@/components/site/theme";
import { Trail } from "@/components/site/trail";
import { TooltipProvider } from "@/components/ui/tooltip";

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
    { media: "(prefers-color-scheme: dark)", color: "#111d29" },
    { media: "(prefers-color-scheme: light)", color: "#f5f6f7" },
  ],
  colorScheme: "dark light",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const cur = currentSeason();
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        {/* Picks the theme before first paint, so light readers see no flash of dark. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-dvh">
        <Trail />
        <TooltipProvider delayDuration={150}>
          <header className="slot-mast">
            {/* Logo left, sections centred, season, palette and theme right. Under md the
                sections drop to their own row. */}
            <div className="mx-auto grid max-w-[1180px] grid-cols-[1fr_auto] items-center gap-x-6 gap-y-2 px-4 py-3 md:grid-cols-[1fr_auto_1fr]">
              <Link href="/" aria-label="High Slot home" className="col-start-1 row-start-1 justify-self-start rounded-lg">
                <Wordmark />
              </Link>
              <div className="col-span-2 col-start-1 row-start-2 -ml-2.5 md:col-span-1 md:col-start-2 md:row-start-1 md:ml-0">
                <SiteNav current={cur} />
              </div>
              <div className="col-start-2 row-start-1 flex items-center gap-1 justify-self-end md:col-start-3">
                <SeasonSelect seasons={seasons()} current={cur} />
                <PaletteToggle />
                <ThemeToggle />
              </div>
            </div>
          </header>
          <main className="mx-auto max-w-[1180px] px-4 pb-16 pt-6">{children}</main>
          <footer className="mx-auto flex max-w-[1180px] flex-wrap justify-between gap-x-6 gap-y-2 px-4 pb-10 text-xs text-muted-foreground">
            <span>Data from the NHL&apos;s public play-by-play and shift charts, scored after every game. Not affiliated with the NHL.</span>
            <nav aria-label="Site" className="flex gap-4">
              <Link href="/about" className="hover:text-foreground">About</Link>
              <Link href="/about#glossary" className="hover:text-foreground">Glossary</Link>
              <Link href="/model" className="hover:text-foreground">Model</Link>
              <a href="mailto:highslotanalytics@gmail.com?subject=High%20Slot" className="hover:text-foreground">Contact</a>
            </nav>
          </footer>
        </TooltipProvider>
      </body>
    </html>
  );
}
