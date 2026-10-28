// Teams, positions and the plain-words explanation behind every column.

/** Names and alignment (2024-25 onward: Utah in the Central). */
export const TEAMS: Record<string, [name: string, conf: "East" | "West", div: string]> = {
  ANA: ["Anaheim Ducks", "West", "Pacific"], BOS: ["Boston Bruins", "East", "Atlantic"], BUF: ["Buffalo Sabres", "East", "Atlantic"],
  CGY: ["Calgary Flames", "West", "Pacific"], CAR: ["Carolina Hurricanes", "East", "Metropolitan"], CHI: ["Chicago Blackhawks", "West", "Central"],
  COL: ["Colorado Avalanche", "West", "Central"], CBJ: ["Columbus Blue Jackets", "East", "Metropolitan"], DAL: ["Dallas Stars", "West", "Central"],
  DET: ["Detroit Red Wings", "East", "Atlantic"], EDM: ["Edmonton Oilers", "West", "Pacific"], FLA: ["Florida Panthers", "East", "Atlantic"],
  LAK: ["Los Angeles Kings", "West", "Pacific"], MIN: ["Minnesota Wild", "West", "Central"], MTL: ["Montréal Canadiens", "East", "Atlantic"],
  NSH: ["Nashville Predators", "West", "Central"], NJD: ["New Jersey Devils", "East", "Metropolitan"], NYI: ["New York Islanders", "East", "Metropolitan"],
  NYR: ["New York Rangers", "East", "Metropolitan"], OTT: ["Ottawa Senators", "East", "Atlantic"], PHI: ["Philadelphia Flyers", "East", "Metropolitan"],
  PIT: ["Pittsburgh Penguins", "East", "Metropolitan"], SJS: ["San Jose Sharks", "West", "Pacific"], SEA: ["Seattle Kraken", "West", "Pacific"],
  STL: ["St. Louis Blues", "West", "Central"], TBL: ["Tampa Bay Lightning", "East", "Atlantic"], TOR: ["Toronto Maple Leafs", "East", "Atlantic"],
  UTA: ["Utah Mammoth", "West", "Central"], VAN: ["Vancouver Canucks", "West", "Pacific"], VGK: ["Vegas Golden Knights", "West", "Pacific"],
  WSH: ["Washington Capitals", "East", "Metropolitan"], WPG: ["Winnipeg Jets", "West", "Central"], ARI: ["Arizona Coyotes", "West", "Central"],
};
export const teamName = (ab: string) => (TEAMS[ab] ?? [ab])[0];

const TWO_WORD = ["Golden Knights", "Maple Leafs", "Blue Jackets", "Red Wings"];
/** "Toronto Maple Leafs" to "Maple Leafs". */
export function nickname(full: string) {
  return TWO_WORD.find(n => full.endsWith(n)) ?? full.split(" ").slice(-1)[0];
}

/** The NHL feed codes wingers L and R; hockey says LW and RW. */
const POS: Record<string, string> = { L: "LW", R: "RW", C: "C", D: "D", G: "G" };
export const posLabel = (p: string) => POS[p] ?? p;

export const SIT: Record<string, string> = {
  EV_5v5: "5v5", PP_5v4: "PP 5v4", SH_4v5: "SH 4v5", EV_4v4: "4v4", EV_3v3: "3v3 OT", PP_5v3: "PP 5v3",
  PP_4v3: "PP 4v3", SH_3v5: "SH 3v5", EN_AGAINST: "Empty net", EN_6v5_PULLED: "6v5 goalie pulled", EN_6v5_DELAYED_PEN: "6v5 delayed penalty",
};
export const EVN: Record<string, string> = { GOAL: "Goal", SHOT: "Saved", MISS: "Missed", BLOCK: "Blocked" };
/** The shot type as a noun for running text: "wrist shot", not "wrist". */
export const shotNoun = (type: string) =>
  ({ WRIST: "wrist shot", SNAP: "snap shot", SLAP: "slap shot", BACK: "backhand", TIP: "tip", DEFL: "deflection", WRAP: "wraparound" })[type] ?? "shot";

/** Every column's hover explanation, shared by every table on the site. */
export const TIPS: Record<string, string> = {
  gp: "Games played.", toi: "Time on ice per game, all situations.", toitot: "Total time on ice, all situations.",
  toi5: "Time on ice at 5-on-5.", g: "Goals.", a: "Assists.", p: "Points: goals plus assists.",
  ixg: "Individual expected goals: the summed goal probability of the player's own unblocked shots.",
  gaxnorm: "His norm: the GAx his finishing in earlier seasons says to expect on this season's shots. Shrunk toward zero, the more so the fewer shots he has taken, since one season of finishing is mostly luck.",
  vsnorm: "Vs. norm: GAx minus his norm. Finishing beyond what he usually does, the part most likely to fade; an elite finisher at his usual pace sits near zero here.",
  gax: "Goals above expected (GAx): goals minus ixG. Positive means he finished better than an average shooter would on the same chances. Very noisy over small samples.",
  att: "Shot attempts, blocked and missed included.", sog: "Shots on goal.",
  xgf: "Expected goals for: the xG of every unblocked shot his team took while he was on the ice.",
  xga: "Expected goals against: the xG of every unblocked shot the other team took while he was on the ice.",
  xgs: "xG share: xGF / (xGF + xGA) while he was on the ice. Above 50% means his team out-chanced the opponent with him out there.",
  xgs5: "xG share at 5-on-5 only, which strips out power plays and penalty kills.",
  rel: "Relative xG share at 5-on-5, in percentage points: his on-ice xG share minus his team's with him on the bench, in the games he played. Positive means the team out-chanced opponents more with him than without him.",
  gfOn: "Goals for: goals his team scored while he was on the ice.", gaOn: "Goals against: goals the other team scored while he was on the ice.",
  gs: "Goal share: GF / (GF + GA) while he was on the ice. The actual result next to xG share, which is the better guide to how he played.",
  gs5: "Goal share at 5-on-5 only.",
  g60: "Goals per 60 minutes of 5-on-5 time, next to his 5v5 ixG/60.",
  gf60: "5-on-5 goals for per 60 minutes while he was on the ice.", ga60: "5-on-5 goals against per 60 minutes while he was on the ice. Lower is better.",
  ixg60: "Individual xG per 60 minutes of 5-on-5 time: how much danger he creates himself.",
  xgf60: "5-on-5 xG for per 60 minutes while he was on the ice.", xga60: "5-on-5 xG against per 60 minutes while he was on the ice. Lower is better.",
  sa: "Unblocked shots faced: saves, goals and shots that missed the net.", gaG: "Goals allowed.",
  xgaG: "Expected goals against: the xG of the unblocked shots he faced.",
  gsax: "Goals saved above expected (GSAx): xGA minus goals allowed. Positive means he stopped more than an average goalie would on the same shots.",
  gsax60: "GSAx per 60 minutes in net.", svp: "Save percentage on unblocked shots: misses count as saves, so it runs higher than NHL Sv%. Pairs with Unbl. xSv%, the same shots.",
  nsvp: "Save percentage as the NHL counts it: saves / shots on goal. Missed shots are left out.",
  xsvp: "Expected save percentage: what an average goalie would stop on the same unblocked shots. Compare it with Unbl. Sv%, not NHL Sv%.",
  rank: "Standings position: by points, then the NHL's tiebreakers: regulation wins, regulation + overtime wins, wins, goal differential.",
  w: "Wins.", l: "Regulation losses.", otl: "Overtime and shootout losses (one point each).", pts: "Standings points: 2 for a win, 1 for an overtime or shootout loss.",
  ppct: "Points percentage: points / (2 x games played).", rw: "Regulation wins, the NHL's first standings tiebreaker.",
  row: "Regulation plus overtime wins (shootout wins excluded).", gf: "Goals for. A shootout win counts as one, as in the standings.",
  ga: "Goals against.", diff: "Goal differential.",
  txgf: "Team expected goals for, all situations.", txga: "Team expected goals against, all situations.",
  txgs: "xG share: the team's share of all expected goals in its games. Above 50% means it out-chances its opponents.",
  txgs5: "xG share at 5-on-5, the most predictive single team number: it ignores special teams and the bounces.",
  txgf60: "5-on-5 expected goals for per 60 minutes.", txga60: "5-on-5 expected goals against per 60 minutes. Lower is better.",
  pp60: "Power-play expected goals per 60 power-play minutes.", pk60: "Penalty-kill expected goals against per 60 shorthanded minutes. Lower is better.",
  tgf: "Goals for, shootouts excluded so it lines up with xGF.", tga: "Goals against, shootouts excluded so it lines up with xGA.",
  tgs: "Goal share: GF / (GF + GA), shootouts excluded. The actual result next to xG share; when goal share runs well ahead of xG share, finishing or goaltending is doing the work.",
  tgs5: "Goal share at 5-on-5.",
  tgf60: "5-on-5 goals for per 60 minutes.", tga60: "5-on-5 goals against per 60 minutes. Lower is better.",
  ppg60: "Power-play goals per 60 power-play minutes.", pkg60: "Penalty-kill goals against per 60 shorthanded minutes. Lower is better.",
  tgax: "Goals above expected (GAx): goals scored minus xGF, shootouts excluded. Finishing; tends to drift back toward zero.",
  tgsax: "Goals saved above expected (GSAx): xGA minus goals allowed, shootouts excluded. Goaltending.",
  tgap: "Goal share minus xG share, in percentage points. Positive means results are running ahead of the chances; it usually narrows as the season goes on.",
  ggap5: "His 5-on-5 on-ice goal differential minus his on-ice xG differential, in goals. Grows with ice time, so a short hot run can't top the list the way it can on a share. Big gaps either way usually narrow.",
  ci95: "95% interval: how far chance alone moves the gap to its left, given the chances involved. A gap inside it (shown muted) is no evidence of skill or luck either way yet.",
  gap5: "His 5-on-5 on-ice goal share minus his on-ice xG share, in percentage points. Big gaps either way usually narrow.",
  xgf5: "5-on-5 expected goals for while he was on the ice.", xga5: "5-on-5 expected goals against while he was on the ice.",
  gf5: "5-on-5 goals for while he was on the ice.", ga5: "5-on-5 goals against while he was on the ice.",
  shp: "Shooting percentage: goals / shots on goal.",
  gpace: "Goals per game, over 82 games.", xpace: "Individual xG per game, over 82 games: what an average finisher would score on his chances.",
  xrank: "xG standings position: by xG points, then xG points %, xG wins and xG share.",
  xw: "xG wins: games where the team had more expected goals than its opponent, empty-net shots left out. Worth 2 points.",
  xl: "xG losses: games where the team had fewer expected goals than its opponent by more than 0.25. No points.",
  xotl: "Close xG losses: games where the team had fewer expected goals but was within 0.25 of the winner. Worth 1 point, like an overtime loss.",
  xpts: "xG points: 2 for each xG win and 1 for each close xG loss. The standings if every game had gone to the team with more xG.",
  xppct: "xG points percentage: xPts / (2 x games played).",
  dpts: "Real points minus xG points. Positive means the team has more points than its chances earned: bounces, finishing or goaltending.",
  move: "Places gained or lost against the real standings in the same grouping. Up means the shots say the team deserves to be higher than it is.",
  inout: "Whether the team is actually in a playoff spot today.",
  sumq: "Where the team sits on each chart above, split at the league average (or 50% / zero).",
  date: "Game date.", opp: "Opponent; @ means a road game.", res: "Result and final score.",
};
