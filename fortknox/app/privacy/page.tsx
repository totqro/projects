import type { Metadata } from "next";
import { Card, CardContent } from "@/components/ui/card";
import { PageHead } from "@/components/site/page-head";

// What the site keeps about visitors: next to nothing. Keep this in step with
// the code if analytics, embeds or accounts are ever added.

export const metadata: Metadata = {
  title: "Privacy",
  description: "High Slot sets no cookies and runs no tracking. What little it keeps, and where.",
};

const H2 = ({ children }: { children: React.ReactNode }) => <h2 className="mb-2 mt-7 text-base font-semibold tracking-[-0.015em] first:mt-0">{children}</h2>;
const P = ({ children }: { children: React.ReactNode }) => <p className="mb-3 max-w-[72ch] text-[15px] leading-relaxed text-secondary-foreground [&_a]:text-foreground [&_a]:underline [&_a]:underline-offset-4 [&_b]:font-semibold [&_b]:text-foreground">{children}</p>;

export default function Privacy() {
  return (
    <>
      <PageHead title="Privacy" sub="Short, because there isn't much to say." />
      <Card className="max-w-4xl">
        <CardContent>
          <H2>No cookies, no tracking</H2>
          <P>High Slot sets <b>no cookies</b> and runs <b>no analytics, ads or third-party scripts</b>. There are no accounts. The fonts are served from this site, so loading a page doesn&apos;t contact anyone else.</P>

          <H2>Settings kept in your browser</H2>
          <P>A few choices are remembered in your own browser&apos;s storage so the site works the way you left it: light or dark mode, the colour-blind palette, the season you picked, and the pages you came through (for the back link). They stay on your device, are never sent to High Slot, and you can clear them at any time by clearing this site&apos;s data in your browser.</P>

          <H2>Hosting</H2>
          <P>The site is hosted on Google&apos;s Firebase Hosting. Like any web server, it keeps standard request logs, which include your IP address and browser type, to deliver pages and keep the service running. High Slot doesn&apos;t use those logs to track or profile anyone. Google&apos;s handling of them is covered by the <a href="https://policies.google.com/privacy">Google Privacy Policy</a>.</P>

          <H2>Email</H2>
          <P>If you write to <a href="mailto:highslotanalytics@gmail.com?subject=High%20Slot">highslotanalytics@gmail.com</a>, your address and message are used only to reply. They aren&apos;t shared or added to any list. Ask, and they&apos;ll be deleted.</P>

          <H2>Changes</H2>
          <P>If any of this changes, for example if analytics are ever added, this page will say so first. Last updated October 29, 2026.</P>
        </CardContent>
      </Card>
    </>
  );
}
