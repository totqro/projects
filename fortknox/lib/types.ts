// Shapes of the published game sheets (pipeline/nhl_sheets.py writes
// them to the xg-sheets-data branch). Field names are kept exactly as
// published so the data never needs translating.

export type Phase = "regular" | "playoff";
export type End = "REG" | "OT" | "SO";

/** One game in a season's index.json. */
export interface GameSummary {
  id: number;
  date: string;
  /** 2 = regular season, 3 = playoffs */
  type: number;
  home: string;
  away: string;
  hs: number;
  as: number;
  end: End;
  hxg: number;
  axg: number;
  hxg5: number;
  axg5: number;
  hatt: number;
  aatt: number;
  hsog: number;
  asog: number;
  shifts: boolean;
  /** Who deserved to win, from the shots (lib/deserve.ts). Not in
   *  index.json: added at build time by seasonGames(). */
  dv?: import("./deserve").Deserved;
}

export interface SeasonIndex {
  season: string;
  updated: string;
  games: GameSummary[];
}

export interface Split {
  toi: number;
  xgf: number;
  xga: number;
  gf: number;
  ga: number;
  cf: number;
  ca: number;
  xgf60: number;
  xga60: number;
  xgf_pct: number;
}

export interface TeamSeason {
  team: string;
  gp: number;
  w: number;
  l: number;
  otl: number;
  gf: number;
  ga: number;
  cf: number;
  ca: number;
  pts: number;
  xgf: number;
  xga: number;
  xgf_pct: number;
  gsax_team: number;
  "5v5": Split;
  pp: Split;
  pk: Split;
}

export interface TeamsFile {
  season: string;
  updated: string;
  regular: TeamSeason[];
  playoff: TeamSeason[];
}

export interface SkaterSeason {
  id: number;
  name: string;
  team: string;
  pos: string;
  num: number;
  gp: number;
  toi: number;
  toi5: number;
  g: number;
  a: number;
  pts: number;
  att: number;
  sog: number;
  ixg: number;
  gax: number;
  ixg5: number;
  g5: number;
  xgf5: number;
  xga5: number;
  gf5: number;
  ga5: number;
  xgf_pct5: number | null;
  xgf: number;
  xga: number;
  gf: number;
  ga: number;
  xgf_pct: number | null;
  xgf60_5: number | null;
  xga60_5: number | null;
  ixg60_5: number | null;
  /** His teams' 5v5 numbers in his games with him on the bench. Missing
   *  from seasons built before October 2026. */
  toi5_off?: number;
  xgf5_off?: number;
  xga5_off?: number;
  gf5_off?: number;
  ga5_off?: number;
}

export interface GoalieSeason {
  id: number;
  name: string;
  team: string;
  pos: string;
  num: number;
  gp: number;
  toi: number;
  sa: number;
  ga: number;
  xga: number;
  gsax: number;
  sv_pct: number | null;
  xsv_pct: number | null;
  gsax60: number | null;
}

/** A group of teammates at 5v5: [ids, toi (s), xgf, xga, gf, ga, cf, ca]. */
export type UnitRow = [ids: number[], toi: number, xgf: number, xga: number, gf: number, ga: number, cf: number, ca: number];

/** One team's 5v5 units for a season phase (lines.json). */
export interface TeamUnits {
  /** id to [name, position] */
  players: Record<string, [string, string]>;
  /** each skater's own totals with this team */
  solo: UnitRow[];
  fwd: UnitRow[];
  def: UnitRow[];
  /** every pair of teammates, for with-or-without-you */
  pairs: UnitRow[];
}

export interface LinesFile {
  season: string;
  updated: string;
  regular: Record<string, TeamUnits>;
  playoff: Record<string, TeamUnits>;
}

export interface PlayersFile {
  season: string;
  updated: string;
  regular: { skaters: SkaterSeason[]; goalies: GoalieSeason[] };
  playoff: { skaters: SkaterSeason[]; goalies: GoalieSeason[] };
}

export interface SheetSide {
  abbrev: string;
  name: string;
  score: number;
  xg: number;
  xg5: number;
  att: number;
  sog: number;
  xga: number;
}

/** A player's line in one game. Skaters carry the scoring and on-ice keys,
 *  goalies sa / ga_ / xga_ (goals and xG against while in net). */
export interface GamePlayer {
  id: number;
  name: string;
  team: string;
  pos: string;
  num: number;
  toi_all?: number;
  toi_5v5?: number;
  toi_pp?: number;
  toi_pk?: number;
  g?: number;
  a?: number;
  att?: number;
  sog?: number;
  ixg?: number;
  ixg5?: number;
  g5?: number;
  xgf?: number;
  xga?: number;
  gf?: number;
  ga?: number;
  xgf5?: number;
  xga5?: number;
  gf5?: number;
  ga5?: number;
  sa?: number;
  ga_?: number;
  xga_?: number;
}

export type ShotEvent = "GOAL" | "SHOT" | "MISS" | "BLOCK";

export interface Shot {
  /** index in the game's shot list */
  i: number;
  p: number;
  t: number;
  team: string;
  ev: ShotEvent;
  x: number;
  y: number;
  type: string;
  xg: number;
  shooter: number;
  goalie: number | null;
  sit: string;
  reb: string;
  rush: number;
  ast: number[] | null;
}

/** A game sheet as published: shots are rows keyed by shot_keys. */
export interface RawSheet {
  id: string;
  date: string;
  type: number;
  venue: string;
  end: End;
  home: SheetSide;
  away: SheetSide;
  shot_keys: string[];
  shots: unknown[][];
  players: GamePlayer[];
}

/** A game sheet with its shots unpacked into objects. */
export interface Sheet extends Omit<RawSheet, "shots" | "shot_keys"> {
  shots: Shot[];
}

/** data/tonight.json: the NHL's slate for tonight, fetched at deploy time. */
export interface TonightTeam { abbrev: string; score: number | null; record: string | null }
export interface TonightGame {
  id: number;
  type: number;
  /** Puck drop, ISO UTC. */
  start: string;
  /** off: postponed or cancelled. */
  state: "pre" | "live" | "final" | "off";
  /** REG, OT or SO once final. */
  end: string | null;
  away: TonightTeam;
  home: TonightTeam;
}
export interface Tonight { date: string; fetched: string; games: TonightGame[] }
