import type { Metadata, Viewport } from "next";
import Link from "next/link";
import "./globals.css";
import "./themes.css";
import { currentSeason, seasons } from "@/lib/data";
import { BrandMarks } from "@/components/site/brands";
import { ThemeSwitcher } from "@/components/site/theme-switcher";
import { SeasonSelect, SiteNav } from "@/components/site/nav";
import { TooltipProvider } from "@/components/ui/tooltip";

export const metadata: Metadata = {
  metadataBase: new URL("https://fortknox-hockey.web.app"),
  title: { default: "Fort Knox · NHL expected goals", template: "%s · Fort Knox" },
  description: "Every NHL game scored shot by shot with a full-data expected-goals model: game sheets, team and player xG, goalie GSAx. Updated after every game.",
  icons: { icon: "/icon.svg" },
  // Pages that set their own openGraph replace this whole object, so the game
  // pages name their image again (app/game/[id]/page.tsx).
  openGraph: { siteName: "Fort Knox", images: [{ url: "/og/site.png", width: 1200, height: 630, alt: "Fort Knox" }] },
  twitter: { card: "summary_large_image", images: ["/og/site.png"] },
};

// Display faces for the rebrand samples (app/themes.css). A plain stylesheet:
// next/font/google fails under Turbopack builds for these families.
const FONTS = "https://fonts.googleapis.com/css2?family=Archivo:wght@700;800&family=Barlow+Condensed:wght@600;700&family=Fraunces:ital,wght@0,600;0,700;1,600&family=JetBrains+Mono:wght@500;700&family=Newsreader:opsz,wght@6..72,600;6..72,700&family=Oswald:wght@500;700&display=swap";
// Applies a remembered sample before first paint, so pages don't flash.
const PRE = `try{var t=new URLSearchParams(location.search).get("theme")||localStorage.getItem("rebrand-theme");if(t)document.documentElement.dataset.theme=t}catch(e){}`;

export const viewport: Viewport = { themeColor: "#0e0e0e", colorScheme: "dark" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const cur = currentSeason();
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: PRE }} />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link rel="stylesheet" href={FONTS} />
      </head>
      <body className="min-h-dvh">
        <TooltipProvider delayDuration={150}>
          <header className="vault-mast">
            <div className="mx-auto flex max-w-[1180px] flex-wrap items-center justify-between gap-x-6 gap-y-3 px-4 py-4">
              <Link href="/" aria-label="Fort Knox home" className="rounded-lg">
                <BrandMarks />
              </Link>
              <div className="flex flex-wrap items-center gap-3">
                <SiteNav current={cur} />
                <SeasonSelect seasons={seasons()} current={cur} />
              </div>
            </div>
          </header>
          <main className="mx-auto max-w-[1180px] px-4 pb-16 pt-6">{children}</main>
          <footer className="mx-auto max-w-[1180px] px-4 pb-10 text-xs text-muted-foreground">
            Data from the NHL&apos;s public play-by-play and shift charts, scored after every game.
          </footer>
          <ThemeSwitcher />
        </TooltipProvider>
      </body>
    </html>
  );
}
