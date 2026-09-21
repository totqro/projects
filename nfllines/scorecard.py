"""
Season scorecard: logged predictions vs actual results vs the closing market.
============================================================================
Mirrors nhllines/scorecard.py. The rules that keep it honest:

1. Only pre-kickoff rows count. A row whose timestamp_utc is at or after
   kickoff (schedule gameday + gametime, US Eastern) is dropped. If several
   runs logged a game, the last pre-kickoff row is the prediction.
2. The market is nflverse's closing moneyline, de-vigged; the closing spread
   and total for points. Read here for scoring only, never as a feature.
3. Win probability is the same number in v1 and v2 rows (only the points
   output changed), so win metrics use the last pre-kickoff row regardless of
   version. Points metrics are reported per model version, never pooled.
4. Below 200 games, any model-vs-market gap is reported as noise.

    python scorecard.py --season 2026
    python scorecard.py --season 2026 --week 2
"""
import argparse
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import nflreadpy as nfl
from nflreadpy import config as nfl_config

from src.data.team_games import TEAM_RENAME
from src.models.metrics import log_loss, brier
from src.models.prediction_log import LOG_PATH

ET = ZoneInfo("America/New_York")
MIN_GAMES_FOR_VERDICT = 200


def american_to_prob(ml):
    ml = np.asarray(ml, dtype=float)
    return np.where(ml < 0, -ml / (-ml + 100.0), 100.0 / (ml + 100.0))


def load_results(season: int) -> pd.DataFrame:
    nfl_config.update_config(cache_mode="off")      # always fresh scores
    g = nfl.load_schedules(seasons=[season]).to_pandas()
    g = g[g.game_type.isin(["REG", "WC", "DIV", "CON", "SB"])].copy()
    g["kickoff"] = [datetime.fromisoformat(f"{d} {t}").replace(tzinfo=ET) for d, t in zip(g.gameday, g.gametime)]
    ph, pa = american_to_prob(g.home_moneyline), american_to_prob(g.away_moneyline)
    g["p_market"] = ph / (ph + pa)
    for c in ("home_team", "away_team"):
        g[c] = g[c].replace(TEAM_RENAME)
    return g.set_index("game_id")


def load_log() -> pd.DataFrame:
    rows = [json.loads(l) for l in open(LOG_PATH) if l.strip()]
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df.timestamp_utc, utc=True)
    return df


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--week", type=int)
    args = ap.parse_args()

    res = load_results(args.season)
    log = load_log()
    log = log[log.season == args.season]
    if args.week:
        log = log[log.week == args.week]
    log = log[log.game_id.isin(res.index)].copy()
    log["kickoff"] = log.game_id.map(res.kickoff)
    pre = log[log.ts < pd.to_datetime(log.kickoff, utc=True)]
    dropped = len(log) - len(pre)
    last = pre.sort_values("ts").groupby("game_id").tail(1).set_index("game_id")
    done = last[res.loc[last.index, "home_score"].notna().to_numpy()].copy()
    pending = sorted(set(last.index) - set(done.index))
    r = res.loc[done.index]
    done["hs"], done["as_"] = r.home_score, r.away_score
    done["margin"], done["total"] = done.hs - done.as_, done.hs + done.as_
    done["p_mkt"], done["spread"], done["tot_line"] = r.p_market, r.spread_line, r.total_line
    ties = done.margin == 0
    w = done[~ties]
    y = (w.margin > 0).astype(int).to_numpy()

    title = f"{args.season}" + (f" week {args.week}" if args.week else "")
    print("=" * 96); print(f"  SCORECARD {title}"); print("=" * 96)
    print(f"logged rows {len(log)}, dropped as post-kickoff {dropped}, games scored {len(done)}, "
          f"ties {int(ties.sum())}, pending {len(pending)} {pending}")

    print(f"\n{'game':<18}{'P(home)':>8}{'mkt':>7}{'score':>9}{'ours':>6}{'mkt':>5}{'margin':>8}{'pred':>7}{'total':>7}{'pred':>7}  ver")
    for gid, row in done.sort_values("kickoff").iterrows():
        ours = "✓" if (row.home_win_prob > .5) == (row.margin > 0) else "✗"
        mkt = "✓" if (row.p_mkt > .5) == (row.margin > 0) else "✗"
        ver = "v2" if "coherent" in row.model_version else "v1"
        print(f"{gid:<18}{row.home_win_prob:>8.3f}{row.p_mkt:>7.3f}{int(row.hs):>4}-{int(row.as_):<4}{ours:>6}{mkt:>5}"
              f"{row.margin:>+8.0f}{row.expected_margin:>+7.1f}{row.total:>7.0f}{row.expected_total:>7.1f}  {ver}")

    print(f"\nWIN (n={len(w)})")
    print(f"{'':<10}{'log loss':>10}{'brier':>8}{'correct':>10}")
    for name, p in (("model", w.home_win_prob.to_numpy()), ("market", w.p_mkt.to_numpy()),
                    ("coin flip", np.full(len(w), 0.5))):
        print(f"{name:<10}{log_loss(y, p):>10.4f}{brier(y, p):>8.4f}{int(((p > .5) == (y == 1)).sum()):>5}/{len(w)}")
    agree = float(np.mean((w.home_win_prob > .5) == (w.p_mkt > .5)))
    print(f"favourite agreement with market: {agree:.3f}")
    if len(w) < MIN_GAMES_FOR_VERDICT:
        print(f"(n={len(w)} < {MIN_GAMES_FOR_VERDICT}: any model-vs-market gap here is noise, not evidence)")

    print("\nPOINTS (per model version; market = closing spread / total)")
    print(f"{'':<14}{'n':>4}{'margin MAE':>12}{'mkt':>7}{'total MAE':>11}{'mkt':>7}")
    for ver, d in done.groupby("model_version"):
        print(f"{ver:<14.14}{len(d):>4}{np.mean(np.abs(d.margin - d.expected_margin)):>12.2f}"
              f"{np.mean(np.abs(d.margin - d.spread)):>7.2f}{np.mean(np.abs(d.total - d.expected_total)):>11.2f}"
              f"{np.mean(np.abs(d.total - d.tot_line)):>7.2f}")


if __name__ == "__main__":
    main()
