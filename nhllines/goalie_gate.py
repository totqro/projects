"""
Goalie GSAx gate — does the starting goalie's quality add signal?
=================================================================
model_gate.py's ablation found the old goalie block (career SV%, GAA) HURT the
held-out score, which is why production ships the "drop-goalie" model. Those
stats mostly measure the team in front of the goalie. This tests a better
measure — GSAx, goals saved above expected (src/data/goalie_gsax.py) — under
the same rules as every other candidate: held-out log loss AND Brier, never
accuracy.

Two versions of the feature, because they answer different questions:

  actual    the goalie who really started. What a confirmed-starter update
            could reach; an upper bound for serving.
  expected  the average rating of the team's last 10 starters. What is known
            before the starter is announced, and so what a daily run can
            actually use. THIS is the honest test for a model that has to
            predict before the lineup card.

Each variant is scored against the current 44-feature production model on the
same fold, leave-one-season-out over every season in training_set.csv
(train on the other three, test on the fourth), plus the gate's own held-out
season called out separately. A single held-out season is one draw of a noisy
signal; four folds say whether a gain repeats.

Nothing here touches training_set.csv, the production artifacts, or
build_training_set.py. It is a read-only experiment.

Usage:
    python goalie_gate.py
    python goalie_gate.py --sensitivity     # PRIOR_SHOTS x SEASON_CARRY grid
    python goalie_gate.py --json data/goalie_gate.json
"""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from model_gate import evaluate_candidate
from src.data import goalie_gsax as gg
from src.data.historical_dataset import (
    FEATURE_COLUMNS, XG_FEATURE_COLUMNS, fetch_game_starters, fetch_season_games_full,
)

BASE = Path(__file__).resolve().parent
TRAINING_SET = BASE / "data" / "training_set.csv"
WARMUP_YEARS = [2018, 2019, 2020, 2021]

ACTUAL = ["home_gsax", "away_gsax", "gsax_diff"]
EXPECTED = ["home_gsax_exp", "away_gsax_exp", "gsax_exp_diff"]

SHARE = ["home_share", "away_share", "share_diff"]
SHARE_EXP = ["home_share_exp", "away_share_exp", "share_exp_diff"]

BACKUP_VARIANTS = {
    "baseline: 44-feature production model": XG_FEATURE_COLUMNS,
    "+ actual starter share diff": XG_FEATURE_COLUMNS + ["share_diff"],
    "+ actual starter share (home, away, diff)": XG_FEATURE_COLUMNS + SHARE,
    "+ typical (pre-announcement) share diff": XG_FEATURE_COLUMNS + ["share_exp_diff"],
    "+ typical share (home, away, diff)": XG_FEATURE_COLUMNS + SHARE_EXP,
}

VARIANTS = {
    "baseline: 44-feature production model": XG_FEATURE_COLUMNS,
    "+ actual starter GSAx diff": XG_FEATURE_COLUMNS + ["gsax_diff"],
    "+ actual starter GSAx (home, away, diff)": XG_FEATURE_COLUMNS + ACTUAL,
    "+ expected starter GSAx diff": XG_FEATURE_COLUMNS + ["gsax_exp_diff"],
    "+ expected starter GSAx (home, away, diff)": XG_FEATURE_COLUMNS + EXPECTED,
    "reference: old goalie block (SV%, GAA) added": FEATURE_COLUMNS,
}


def build_gsax_features(seasons: list, prior_shots: float = gg.PRIOR_SHOTS,
                        season_carry: float = gg.SEASON_CARRY, verbose: bool = True) -> dict:
    """{game_id: feature dict} for every game of `seasons`, point-in-time: a
    game's features use only games on EARLIER dates."""
    years = WARMUP_YEARS + sorted({int(s[:4]) for s in seasons})
    goalie_games = {y: gg.aggregate_season_goalie_games(y) for y in years}
    scale = gg.calibration_factor(goalie_games)

    ratings = gg.GoalieRatings(scale, prior_shots, season_carry)
    history = gg.StarterHistory()
    shares = gg.StarterShare()

    # Warm-up: seasons before the training data. Ordered by game id (no dates
    # needed — nothing here is scored, it only seeds ratings).
    for i, year in enumerate(WARMUP_YEARS):
        if i:
            ratings.new_season()
        for gid in sorted(goalie_games[year]):
            for goalie, line in goalie_games[year][gid].items():
                ratings.record(goalie, line)

    features, n_uncovered, n_no_starter = {}, 0, 0
    for i, season in enumerate(sorted(seasons)):
        ratings.new_season()
        games = fetch_season_games_full(season, verbose=False)
        by_date = defaultdict(list)
        for g in games:
            by_date[g["date"]].append(g)

        for date in sorted(by_date):
            todays = by_date[date]
            starters = {}
            for g in todays:
                home_s, away_s = fetch_game_starters(g["id"])
                starters[g["id"]] = (home_s and home_s["id"], away_s and away_s["id"])
                if not (starters[g["id"]][0] and starters[g["id"]][1]):
                    n_no_starter += 1

            # Features first (only earlier dates recorded so far)...
            for g in todays:
                hs, as_ = starters[g["id"]]
                h, a = ratings.rating(hs), ratings.rating(as_)
                he = history.expected_rating(g["home_team"], ratings)
                ae = history.expected_rating(g["away_team"], ratings)
                hsh, ash = (shares.share(g["home_team"], hs),
                            shares.share(g["away_team"], as_))
                hte, ate = shares.typical(g["home_team"]), shares.typical(g["away_team"])
                features[g["id"]] = {
                    "home_gsax": h, "away_gsax": a, "gsax_diff": h - a,
                    "home_gsax_exp": he, "away_gsax_exp": ae, "gsax_exp_diff": he - ae,
                    "home_share": hsh, "away_share": ash, "share_diff": hsh - ash,
                    "home_share_exp": hte, "away_share_exp": ate, "share_exp_diff": hte - ate,
                }
            # ...then record the day's results.
            for g in todays:
                lines = goalie_games[int(season[:4])].get(g["id"])
                if lines is None:
                    n_uncovered += 1
                else:
                    for goalie, line in lines.items():
                        ratings.record(goalie, line)
                hs, as_ = starters[g["id"]]
                history.record(g["home_team"], hs)
                history.record(g["away_team"], as_)
                shares.record(g["home_team"], hs)
                shares.record(g["away_team"], as_)

    if verbose:
        print(f"  GSAx scale (goals/xG, {WARMUP_YEARS[0]}-{WARMUP_YEARS[-1]}): {scale:.4f}")
        print(f"  {len(features)} games featurised; {n_uncovered} without shot data, "
              f"{n_no_starter} missing a starter (rated 0.0)")
    return features


def _attach(rows: list, features: dict) -> list:
    out = []
    for r in rows:
        f = features.get(int(r["game_id"]))
        if f is None:
            raise SystemExit(f"game {r['game_id']} has no GSAx features")
        out.append({**r, **{k: f"{v:.6f}" for k, v in f.items()}})
    return out


def evaluate(rows: list, seasons: list, variants: dict = None) -> dict:
    """Per-variant, per-season held-out metrics."""
    results = {}
    for name, columns in (variants or VARIANTS).items():
        per = {}
        for season in seasons:
            m = evaluate_candidate(rows, "logreg", columns=columns, test_season=season)
            per[season] = {"log_loss": m["log_loss"], "brier": m["brier"],
                           "accuracy": m["accuracy"], "n": m["n_test"]}
        results[name] = per
    return results


def print_report(results: dict, seasons: list, gate_season: str, title: str = "GSAx") -> dict:
    base_name = next(iter(results))
    base = results[base_name]
    print()
    print("=" * 96)
    print(f"  GOALIE {title} GATE — leave-one-season-out, paired against the 44-feature production model")
    print("=" * 96)
    print("  Gap = baseline minus variant (positive = variant is BETTER). Log loss in 1e-4 units.")
    print()
    head = f"  {'Variant':<46}" + "".join(f"{s[:4]}-{s[6:]:>3}" for s in seasons) + f"{'mean':>8}{'gate':>8}"
    print(head)
    print("  " + "-" * (len(head) - 2))
    summary = {}
    for name, per in results.items():
        gaps_ll = [(base[s]["log_loss"] - per[s]["log_loss"]) * 1e4 for s in seasons]
        gaps_br = [(base[s]["brier"] - per[s]["brier"]) * 1e4 for s in seasons]
        mean_ll = sum(gaps_ll) / len(gaps_ll)
        gate_ll = (base[gate_season]["log_loss"] - per[gate_season]["log_loss"]) * 1e4
        gate_br = (base[gate_season]["brier"] - per[gate_season]["brier"]) * 1e4
        summary[name] = {
            "log_loss_gap_by_season": dict(zip(seasons, gaps_ll)),
            "mean_log_loss_gap_e4": mean_ll,
            "mean_brier_gap_e4": sum(gaps_br) / len(gaps_br),
            "gate_season_log_loss_gap_e4": gate_ll,
            "gate_season_brier_gap_e4": gate_br,
            "seasons_improved_both": sum(1 for a, b in zip(gaps_ll, gaps_br) if a > 0 and b > 0),
        }
        if name == base_name:
            print(f"  {name:<46}" + "".join(f"{per[s]['log_loss']:>9.4f}" for s in seasons)
                  + f"{sum(per[s]['log_loss'] for s in seasons) / len(seasons):>8.4f}"
                  + f"{'(abs)':>8}")
            continue
        print(f"  {name:<46}" + "".join(f"{g:>+9.1f}" for g in gaps_ll)
              + f"{mean_ll:>+8.1f}{gate_ll:>+8.1f}")
    print()
    for name, s in summary.items():
        if name == base_name:
            continue
        verdict = ("PASS" if s["gate_season_log_loss_gap_e4"] > 0 and s["gate_season_brier_gap_e4"] > 0
                   and s["mean_log_loss_gap_e4"] > 0 else "fail")
        print(f"  {verdict:<5} {name}: held-out {gate_season} "
              f"log loss {s['gate_season_log_loss_gap_e4']:+.1f}e-4, "
              f"Brier {s['gate_season_brier_gap_e4']:+.1f}e-4; "
              f"improved BOTH metrics in {s['seasons_improved_both']}/{len(seasons)} seasons")
        s["verdict"] = verdict
    print()
    print("  PASS needs: better log loss AND Brier on the gate's held-out season, and a positive")
    print("  mean log-loss gap across all folds. Anything else is noise or worse.")
    return summary


def print_sensitivity(rows: list, seasons: list, gate_season: str):
    print("\n  Sensitivity (information only — defaults were fixed before any gate run).")
    print("  Mean log-loss gap vs baseline, expected-starter diff feature, 1e-4 units:")
    print(f"  {'PRIOR_SHOTS':>12}" + "".join(f"  carry={c}" for c in (0.5, 0.7, 0.9)))
    cols = XG_FEATURE_COLUMNS
    base = {s: evaluate_candidate(rows, "logreg", columns=cols, test_season=s)["log_loss"]
            for s in seasons}
    for prior in (300, 600, 1200):
        line = f"  {prior:>12}"
        for carry in (0.5, 0.7, 0.9):
            feats = build_gsax_features(seasons, prior, carry, verbose=False)
            r2 = _attach(rows, feats)
            gaps = [(base[s] - evaluate_candidate(r2, "logreg", columns=cols + ["gsax_exp_diff"],
                                                  test_season=s)["log_loss"]) * 1e4
                    for s in seasons]
            line += f"  {sum(gaps) / len(gaps):>+9.1f}"
        print(line)


def main():
    parser = argparse.ArgumentParser(description="Gate the goalie GSAx feature")
    parser.add_argument("--feature", choices=["gsax", "backup"], default="gsax",
                        help="gsax: goalie quality (failed the gate); backup: is the "
                             "team's usual starter in net")
    parser.add_argument("--sensitivity", action="store_true")
    parser.add_argument("--json", default=None)
    args = parser.parse_args()

    with open(TRAINING_SET) as f:
        rows = list(csv.DictReader(f))
    seasons = sorted({r["season"] for r in rows})
    gate_season = seasons[-1]
    print(f"Seasons: {', '.join(seasons)} (gate held-out season: {gate_season})")
    print("Building point-in-time goalie GSAx features...")
    features = build_gsax_features(seasons)
    rows = _attach(rows, features)

    variants = BACKUP_VARIANTS if args.feature == "backup" else VARIANTS
    results = evaluate(rows, seasons, variants)
    summary = print_report(results, seasons, gate_season,
                           "BACKUP-IN-NET" if args.feature == "backup" else "GSAx")
    if args.sensitivity and args.feature == "gsax":
        print_sensitivity(rows, seasons, gate_season)
    if args.json:
        Path(args.json).write_text(json.dumps({"results": results, "summary": summary}, indent=2))
        print(f"\nWrote {args.json}")


if __name__ == "__main__":
    main()
