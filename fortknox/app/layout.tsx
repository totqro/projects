import type { Metadata, Viewport } from "next";
import Link from "next/link";
import "@fontsource/barlow-condensed/600.css";
import "@fontsource/barlow-condensed/700.css";
import "./globals.css";
import { currentSeason, seasons } from "@/lib/data";
import { Wordmark } from "@/components/site/logo";
import { SeasonSelect, SiteNav } from "@/components/site/nav";
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

export const viewport: Viewport = { themeColor: "#030c17", colorScheme: "dark" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const cur = currentSeason();
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body className="min-h-dvh">
        <TooltipProvider delayDuration={150}>
          <header className="slot-mast">
            <div className="mx-auto flex max-w-[1180px] flex-wrap items-center justify-between gap-x-6 gap-y-3 px-4 py-4">
              <Link href="/" aria-label="High Slot home" className="rounded-lg">
                <Wordmark />
              </Link>
              <div className="flex flex-wrap items-center gap-3">
                <SiteNav current={cur} />
                <SeasonSelect seasons={seasons()} current={cur} />
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
            </nav>
          </footer>
        </TooltipProvider>
      </body>
    </html>
  );
}
