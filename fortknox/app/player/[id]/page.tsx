import type { Metadata } from "next";
import Link from "next/link";
import { playerGames, playersFile, seasons } from "@/lib/data";
import { f1, f2, pct, seasonLabel, sv, toi } from "@/lib/format";
import { posLabel, teamName } from "@/lib/teams";
import type { GamePlayer } from "@/lib/types";
import { PageHead } from "@/components/site/page-head";
import { Note, Section, Tile } from "@/components/site/section";
import { PlayerLog } from "@/components/players/player-log";
import { Signed } from "@/components/tables/sortable";

export const dynamicParams = false;
export const generateStaticParams = () => [...playerGames().keys()].map(id => ({ id: String(id) }));

type Props = { params: Promise<{ id: string }> };

function who(id: number) {
  const log = playerGames().get(id) ?? [];
  const last = log[log.length - 1];
  return { log, name: last?.line.name ?? "Unknown", pos: last?.line.pos ?? "", team: last?.team ?? "" };
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { name, team } = who(+(await params).id);
  return { title: `${name}, ${teamName(team)}`, description: `${name}'s expected goals, game by game.` };
}

/** Only the keys the game log shows, so each page stays small. */
const SK_KEYS = ["toi_all", "g", "a", "ixg", "att", "xgf", "xga"] as const;
const GK_KEYS = ["toi_all", "sa", "ga_", "xga_"] as const;
function trim(line: GamePlayer, goalie: boolean): GamePlayer {
  const out: GamePlayer = { id: line.id, name: line.name, team: line.team, pos: line.pos, num: line.num };
  for (const k of goalie ? GK_KEYS : SK_KEYS) if (line[k] != null) out[k] = line[k];
  return out;
}

/** A season's line from players.json, regular season first. */
function seasonLines(id: number) {
  return seasons().flatMap(s => (["regular", "playoff"] as const).flatMap(ph => {
    const P = playersFile(s)[ph];
    const sk = P.skaters.find(p => p.id === id), gk = P.goalies.find(p => p.id === id);
    return sk || gk ? [{ season: s, phase: ph, sk, gk }] : [];
  }));
}

export default async function Player({ params }: Props) {
  const id = +(await params).id;
  const { log, name, pos, team } = who(id);
  const goalie = pos === "G";
  const lines = seasonLines(id);
  const cur = lines[0];
  const bySeason = seasons().map(s => ({ s, rows: log.filter(g => g.season === s) })).filter(x => x.rows.length);

  return (
    <>
      <PageHead title={name} sub={<>{posLabel(pos)}, <Link href={`/team/${log[log.length - 1]?.season}/${team}`} className="hover:underline">{teamName(team)}</Link></>} />

      {cur && (
        <Section title={`${seasonLabel(cur.season)}${cur.phase === "playoff" ? " playoffs" : ""}`} className="mb-8">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-[repeat(auto-fit,minmax(128px,1fr))]">
            {cur.sk && <>
              <Tile label="Games">{cur.sk.gp}</Tile>
              <Tile label="Goals, assists">{cur.sk.g}&ndash;{cur.sk.a}</Tile>
              <Tile label="Points"><span className="brand-text">{cur.sk.pts}</span></Tile>
              <Tile label="ixG">{f1(cur.sk.ixg)}</Tile>
              <Tile label="Goals above expected"><Signed v={cur.sk.gax} /></Tile>
              <Tile label="5v5 xG share">{pct(cur.sk.xgf_pct5)}</Tile>
              <Tile label="TOI per game">{toi(cur.sk.toi / cur.sk.gp)}</Tile>
            </>}
            {cur.gk && <>
              <Tile label="Games">{cur.gk.gp}</Tile>
              <Tile label="GSAx"><Signed v={cur.gk.gsax} /></Tile>
              <Tile label="Save %">{sv(cur.gk.sv_pct)}</Tile>
              <Tile label="Expected save %">{sv(cur.gk.xsv_pct)}</Tile>
              <Tile label="GSAx per 60"><Signed v={cur.gk.gsax60} d={2} /></Tile>
              <Tile label="xGA">{f2(cur.gk.xga)}</Tile>
            </>}
          </div>
        </Section>
      )}

      <div className="space-y-8">
        {bySeason.map(({ s, rows }) => (
          <Section key={s} title={`${seasonLabel(s)} game log`}>
            <PlayerLog goalie={goalie} rows={rows.map(r => ({ ...r, line: trim(r.line, goalie) }))} />
          </Section>
        ))}
      </div>
      <Note className="mt-3">Click a date to open that game&apos;s sheet. Hover a heading for what it means.</Note>
    </>
  );
}
