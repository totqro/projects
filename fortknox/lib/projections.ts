import "server-only";
import fs from "node:fs";
import path from "node:path";

// Projected standings and playoff odds (pipeline/nhl_projections.py), one
// file per season in progress: data/<season>/projections.json.

export interface ProjTeam {
  team: string;
  conf: "East" | "West";
  div: string;
  gp: number; w: number; l: number; otl: number; pts: number;
  /** Mean final points over the simulated seasons, and the 10th-90th percentile range. */
  proj: number; lo: number; hi: number;
  playoff: number; divwin: number; pres: number;
  /** Final-points histogram: [lowest points, counts from there up]. */
  hist: [number, number[]];
  elo: number;
  /** Season-to-date 5v5 xG differential per game. */
  xgd: number;
  left: number;
}

export interface Projections {
  season: number;
  updated: string;
  as_of: string | null;
  sims: number;
  games_played: number;
  games_left: number;
  model: { version: string; sigma: number; min_gp: number; ot: { rate: number; so_share: number; k: number } };
  teams: ProjTeam[];
}

export function projections(season: number): Projections | null {
  const file = path.join(process.cwd(), "data", String(season), "projections.json");
  return fs.existsSync(file) ? (JSON.parse(fs.readFileSync(file, "utf8")) as Projections) : null;
}
