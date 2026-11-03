"""
Season scorecard: logged predictions vs actual results vs the closing market.
============================================================================
Mirrors nhllines/scorecard.py. The rules that keep it honest:

1. Only pre-kickoff rows count. A row whose timestamp_utc is at or after
   kickoff (schedule gameday + gametime, US Eastern) is dropped. If several
   runs logged a game, the last pre-kickoff full-data row is the prediction;
   a backup row (quality="backup", logged from incomplete data, see
   src/readiness.py) counts only when the game has no full-data row.
   The one exception is a rerun row (quality="rerun", written by
   `predict.py --rerun` for a week that was never predicted live, i.e. 2026
   week 1): it is logged after kickoff by definition, counts only for a game
   with no live row, and is labelled "rerun" wherever it is shown.
2. The market is the de-vigged moneyline (and spread / total for points)
   frozen at kickoff: the last line nflverse gave us before the game started,
   kept in data/market_frozen.json by export_web.py. A line nflverse revises
   after kickoff never changes a finished game. Games with no frozen line
   (before the snapshots began in week 4) fall back to nflverse's closing
   line. Read here for scoring only, never as a feature.
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
from pathlib import Path
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
FROZEN_PATH = Path(__file__).resolve().parent / "data" / "market_frozen.json"
FROZEN_FIELDS = {"home_prob": "p_market", "spread": "spread_line", "total": "total_line"}


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


def load_frozen() -> dict:
    return json.loads(FROZEN_PATH.read_text()) if FROZEN_PATH.exists() else {}


def freeze_market(res: pd.DataFrame, now: datetime) -> dict:
    """Save the current line for every game not yet started. After kickoff a
    game's entry is never touched again, so it keeps its last pre-kickoff line."""
    frozen = load_frozen()
    for gid, g in res.iterrows():
        if now < g.kickoff and pd.notna(g.p_market):
            frozen[gid] = {"home_prob": round(float(g.p_market), 4),
                           "spread": None if pd.isna(g.spread_line) else float(g.spread_line),
                           "total": None if pd.isna(g.total_line) else float(g.total_line),
                           "fetched_at": now.isoformat(timespec="seconds")}
    FROZEN_PATH.write_text(json.dumps(dict(sorted(frozen.items())), indent=1) + "\n")
    return frozen


def apply_frozen_market(res: pd.DataFrame, now: datetime, frozen: dict | None = None) -> pd.DataFrame:
    """Swap in the frozen line for games that have kicked off. Fields the
    snapshot lacks (spread / total in the backfilled weeks) stay as nflverse has them."""
    frozen = load_frozen() if frozen is None else frozen
    res = res.copy()
    for gid, f in frozen.items():
        if gid in res.index and now >= res.at[gid, "kickoff"]:
            for k, col in FROZEN_FIELDS.items():
                if f.get(k) is not None:
                    res.at[gid, col] = f[k]
    return res


def load_log() -> pd.DataFrame:
    rows = [json.loads(l) for l in open(LOG_PATH) if l.strip()]
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df.timestamp_utc, utc=True)
    df["quality"] = df["quality"].fillna("final") if "quality" in df else "final"
    return df


QUALITY_RANK = {"final": 2, "backup": 1, "rerun": 0}


def counted_rows(log: pd.DataFrame, res: pd.DataFrame) -> pd.DataFrame:
    """Rows that may count: logged before kickoff, or a labelled rerun."""
    log = log[log.game_id.isin(res.index)].copy()
    log["kickoff"] = log.game_id.map(res.kickoff)
    return log[(log.ts < pd.to_datetime(log.kickoff, utc=True)) | (log.quality == "rerun")]


def pick_prediction(pre: pd.DataFrame) -> pd.DataFrame:
    """One row per game from its counted rows: the last full-data row, else the
    last backup row, else the rerun row (a game never predicted live)."""
    pre = pre.assign(_rank=pre.quality.map(QUALITY_RANK).fillna(2))
    return pre.sort_values(["_rank", "ts"]).groupby("game_id").tail(1).drop(columns="_rank").set_index("game_id")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--week", type=int)
    args = ap.parse_args()

    res = apply_frozen_market(load_results(args.season), datetime.now(ET))
    log = load_log()
    log = log[log.season == args.season]
    if args.week:
        log = log[log.week == args.week]
    log = log[log.game_id.isin(res.index)]
    pre = counted_rows(log, res)
    dropped = len(log) - len(pre)
    last = pick_prediction(pre)
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
        ver = ("v2" if "coherent" in row.model_version else "v1") + (f" {row.quality}" if row.quality != "final" else "")
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

    print("\nPOINTS (per model version; market = spread / total at kickoff)")
    print(f"{'':<14}{'n':>4}{'margin MAE':>12}{'mkt':>7}{'total MAE':>11}{'mkt':>7}")
    for ver, d in done.groupby("model_version"):
        print(f"{ver:<14.14}{len(d):>4}{np.mean(np.abs(d.margin - d.expected_margin)):>12.2f}"
              f"{np.mean(np.abs(d.margin - d.spread)):>7.2f}{np.mean(np.abs(d.total - d.expected_total)):>11.2f}"
              f"{np.mean(np.abs(d.total - d.tot_line)):>7.2f}")


if __name__ == "__main__":
    main()
