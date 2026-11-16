import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { currentSeason } from "@/lib/data";
import { currentArticles, FORMATS } from "@/lib/articles";
import { fmtDate } from "@/lib/format";
import { PageHead } from "@/components/site/page-head";
import { TeamLogo } from "@/components/site/team-logo";
import { BackLink } from "@/components/site/trail";
import { ArticleBody } from "@/components/articles/blocks";

export const dynamicParams = false;
// A static export needs at least one path; before the season's first game the
// placeholder renders the 404.
export const generateStaticParams = () => {
  const p = currentArticles().map(a => ({ slug: a.slug }));
  return p.length ? p : [{ slug: "none" }];
};

type Props = { params: Promise<{ slug: string }> };
const find = (slug: string) => currentArticles().find(a => a.slug === slug);

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const a = find((await params).slug);
  return a ? { title: a.title, description: a.dek } : {};
}

export default async function ArticlePage({ params }: Props) {
  const a = find((await params).slug);
  if (!a) notFound();
  return (
    <>
      <BackLink href="/articles" label="Articles" />
      <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-[0.06em] text-muted-foreground">
        {a.team && <TeamLogo team={a.team} size={16} />}
        <span>{FORMATS[a.format].name}</span>
        <span aria-hidden>·</span>
        <span>Through {fmtDate(a.through)}</span>
      </div>
      <div className="max-w-[72ch]"><PageHead title={a.title} sub={a.dek} /></div>
      <ArticleBody blocks={a.blocks} season={currentSeason()} />
      <p className="mt-8 max-w-[72ch] border-t border-border pt-4 text-[13px] leading-relaxed text-muted-foreground">
        Written automatically from High Slot&apos;s numbers and rewritten after every game.{" "}
        <Link href="/about#glossary" className="underline underline-offset-4">What the stats mean</Link>.
      </p>
    </>
  );
}
