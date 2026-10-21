// Team pages ship every player's line from every game so the window picker
// (season, last 10, ...) can re-total them in the browser.

/** One player's line in one of this team's games, trimmed for the page. */
export interface Line {
  gid: number; id: number; name: string; pos: string;
  toi_all: number; toi_5v5: number; g: number; a: number; ixg: number; att: number;
  xgf: number; xga: number; xgf5: number; xga5: number; gf: number; ga: number; gf5: number; ga5: number;
  sa: number; ga_: number; xga_: number;
  /** goalies: shots on goal faced (saves + goals), the NHL's save % denominator */
  sog_a: number;
}

/** The numeric keys of a Line, in the order a packed row carries them. */
export const LINE_KEYS = ["toi_all", "toi_5v5", "g", "a", "ixg", "att", "xgf", "xga", "xgf5", "xga5", "gf", "ga", "gf5", "ga5", "sa", "ga_", "xga_", "sog_a"] as const;

/** Lines as the page ships them: a name table and one array per line,
 *  [game id, player id, ...LINE_KEYS]. Objects repeated every key for every
 *  player in every game, which was most of a team page. */
export interface PackedLines { names: Record<number, [name: string, pos: string]>; rows: number[][] }

export function packLines(lines: Line[]): PackedLines {
  const names: PackedLines["names"] = {};
  for (const l of lines) names[l.id] = [l.name, l.pos];
  return { names, rows: lines.map(l => [l.gid, l.id, ...LINE_KEYS.map(k => l[k])]) };
}

export function unpackLines({ names, rows }: PackedLines): Line[] {
  return rows.map(([gid, id, ...v]) => {
    const l = { gid, id, name: names[id]?.[0] ?? "", pos: names[id]?.[1] ?? "" } as Line;
    LINE_KEYS.forEach((k, i) => { l[k] = v[i]; });
    return l;
  });
}
