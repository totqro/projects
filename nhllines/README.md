# NHL Game Prediction Model

Predicts, for every NHL game: **win probability** (calibrated xG + form
logistic — the first model to pass the gate) and **expected total goals**.
Predictions are logged before puck drop and evaluated after — against actual
results and against the strongest available benchmark, the betting market's
implied probabilities.

**Status:** Rebuilt July 2026 — leak-free pipeline, gated models, calibrated output
**Deployment:** https://projects-brawlstars.web.app/nhllines/

---

## What this is (and isn't)

This is a **prediction model with an evaluation discipline**, in the spirit of
MoneyPuck or FiveThirtyEight's old NHL forecasts: probabilities published
up front, scored with proper scoring rules (log loss, Brier), and benchmarked
against the market consensus — the hardest public predictor to beat.

The codebase retains odds-fetching and market-comparison utilities. They serve
as the **evaluation benchmark**: market-implied probabilities are the ~59-60%
accurate yardstick every sports model should be measured against. This project
does not recommend, size, or place wagers.

---

## Honest Performance History (July 2026)

The original model (52-feature XGBoost) evaluated at ~49.8% accuracy over a
season, with inverted calibration — its most confident predictions were its
least accurate (65%+ confidence bins went 2/13). The rebuild started from that
admission.

### Root causes (diagnosed July 2026)

1. **Training data leakage / train-serve skew** — the old model trained on
   historical games stamped with **current** values: current standings as
   features for months-old games, today's goalie/advanced stats applied
   identically to every historical game, injury impact zeroed in training but
   live at prediction. Of 52 features, only 4 were genuinely point-in-time.
2. **Training window far too small** — ~575 games with heavy recency weighting
   left an effective sample of ~150-250 games for 52 features.
3. **No stored benchmark** — model quality was judged against live market
   prices with a leaky model, so apparent "edges" were mostly model error.
4. **Overconfident output pipeline** — hand-tuned confidence constants fitted
   to a 35-observation sample.

### Rebuild (all items independently verified)

1. ✅ **Point-in-time training set over 4 full seasons**
   (`build_training_set.py` → `data/training_set.csv`). 4,902 rows from 5,248
   games (2022-23 through 2025-26); every feature computed only from games
   *before* each game date. Verified: all 44 features match a from-scratch
   recomputation exactly on every row.
2. ✅ **Actual starting goalie per historical game** (NHL API boxscores,
   100% coverage) — rolling career SV%/GAA as of each game. Goalie GAA is a
   top-5 coefficient with correct signs.
3. ✅ **Elo + home-ice baseline and the model gate** (`model_gate.py`) — any
   richer model ships only if it beats the 5-parameter Elo baseline on
   held-out log loss AND Brier. Accuracy alone is not admissible evidence.
   Superseded by item 8 below — see current verdict there.
4. ✅ **Probability calibration** (`calibrate.py`) — Platt scaling fit on a
   held-out season, scored on a third unseen season. Adopted for the shipped
   model (log loss 0.6959 → 0.6931, ECE 0.0549 → 0.0510); isotonic rejected
   (overfits the thin calibration season).
5. ✅ **Prediction logging + market benchmark archive** — every `main.py` run
   appends one JSON line per game to `data/predictions_log.jsonl`
   (`src/analysis/prediction_log.py`): UTC timestamp, game id/date/teams,
   calibrated win probability, expected total, model version. Append-only,
   deduped by (game_id, run date) so re-running the same day doesn't
   double-log. `scripts/snapshot_market.py` fetches and devigs consensus odds
   into `data/market_snapshots/YYYY-MM-DD_HHMM.json` on a cron schedule (see
   the script's docstring) — the season-long market benchmark for step 4 of
   the timeline below.
6. ✅ **Feature ablation** (`model_gate.py --ablation`) — grouped block
   ablation on the 44-feature (pre-xG) set found no pruned variant beating
   Elo. Superseded by item 8 below.
7. ✅ **Total-goals gate** (`model_gate.py --totals`) — a Poisson regression
   and a Poisson-loss gradient-boosting model, both on the same point-in-time
   feature set, gated against a trivial league-average-Poisson baseline on
   held-out RMSE AND mean Poisson NLL (2025-26 held out). Verdict: **the
   baseline still wins**, including with the MoneyPuck xG features added in
   item 8 (RMSE 2.2873 / NLL 2.2455 vs the 55-feature Poisson regression's
   2.2956 / 2.2486). Neither model earns the right to replace the current
   expected-total source — the similarity model in `src/models/model.py`
   keeps supplying `expected_total` in `main.py`, unchanged.
8. ✅ **MoneyPuck xG features — win-model gate PASSES** (`src/data/moneypuck_data.py`,
   `model_gate.py`) — per-team shot-level xG from MoneyPuck's public shots
   dataset (2022-23 through 2025-26 seasons), aggregated to point-in-time
   rolling features: `xgf_per60`/`xga_per60` (5v5, score-within-one "close"
   situations — the raw shots file has no pre-computed score/venue-adjusted
   column, so this is the standard public stand-in), `high_danger_xg_share`
   (xG >= 0.08 shots), and a luck feature (goals − xG, cumulative, for and
   against). Every game in a covered season is asserted to join onto
   MoneyPuck data — unmatched teams/games fail loudly rather than dropping
   silently. Added to the 55-feature logistic candidate, this **now beats
   the Elo baseline on both log loss and Brier** (0.6903/0.2482 vs Elo's
   0.6929/0.2496 on held-out 2025-26) — the first candidate in this rebuild
   to pass the win-model gate. Ablation confirms xG is the driver: dropping
   the xG block is the only ablation variant that fails to beat Elo
   (0.6961/0.2512); dropping goalie/form/streak-trend/h2h/splits all still
   pass. The totals gate (item 7) still does not pass with xG added — xG
   features carry win-probability signal, not total-goals signal, in this
   feature set.

9. ✅ **xG model wired into production serving** (`src/models/xg_production.py`)
   — the ablation winner (the 44-feature drop-goalie logistic: xG in, goalie
   out; 0.6881/0.2473 vs Elo's 0.6929/0.2496 on held-out 2025-26) now serves
   win probability in `main.py`, replacing Elo. Coefficients and the Platt
   calibrator are persisted to `ml_models/` and refit weekly by
   `build_training_set.py`; `main.py` falls back to the calibrated Elo model
   when those artifacts are absent. Train/serve skew guards:
   `compute_serving_features()` asserts its output keys exactly match the
   training feature list, live xG state carries a team's last covered value
   forward rather than resetting to a neutral default when MoneyPuck
   publishes late, and both serving paths apply the identical "+1, capped at
   7" rest-day conversion. Verified: persisted coefficients reproduce the
   calibrator's fitting distribution exactly (max delta 0.0).

10. ✅ **Season-validation record is durable** (`.gitignore`,
    `.github/workflows/`) — the prediction log and the market snapshots are
    committed, not left on the CI runner that wrote them. Both are
    perishable: a prediction not logged before puck drop, or a market price
    not captured before it, cannot be reconstructed afterwards, and the
    Jan/Apr 2027 scorecards have nothing to score without them.
    `market-snapshot.yml` runs `scripts/snapshot_market.py` 3x daily
    (opening / midday / near puck drop) and commits each snapshot;
    `daily-nhl-analysis.yml` commits `data/predictions_log.jsonl` — which
    also makes the log's same-day dedup work, since checkout restores prior
    runs' lines. Each logged row is stamped with the win model that actually
    served it (`xg-dropgoalie-platt-v1` or `elo-platt-v1`), so a fallback run
    can never be pooled with an xG run in the scorecard.

11. ✅ **Season scorecard** (`scorecard.py`) — scores the logged predictions
    against actual results and against the market's closing consensus: log
    loss, Brier, accuracy, ECE, a reliability table, and totals RMSE/MAE/
    Poisson NLL (the same NLL definition the totals gate uses, imported
    rather than reimplemented). Three rules keep it honest: only rows logged
    before the game date count; the market is scored on the latest snapshot
    taken *strictly before* commence time, so the benchmark can't peek; and
    the model-vs-market table is restricted to games where both have a
    pre-game number. Mixed model versions are reported rather than pooled,
    and a head-to-head gap on fewer than 200 games is labelled as noise
    rather than reported as a result. Built before the data exists on
    purpose — verified against a synthetic season with known answers (16
    checks: dedup to the last pre-game row, post-game rows dropped,
    late-evening games keyed to the right date, post-puck-drop snapshots
    excluded, metrics matched against sklearn) and against the real
    snapshots already archived.

The leaky XGBoost path stays quarantined. The similarity model still supplies
**expected total goals** — the totals gate found nothing that beats a constant
league-average Poisson mean, so there's nothing better to wire in yet. The
season list rolls forward automatically each July.

### Timeline (updated July 26, 2026)

| When | Milestone |
|------|-----------|
| ✅ Done (Jul 2026) | Point-in-time dataset, goalie starters, Elo baseline + gate, Platt calibration, production wiring — all verified |
| ✅ Done (Jul 2026) | Totals gate (`model_gate.py --totals`, baseline wins — nothing shipped), prediction log, market-consensus snapshot job — all verified |
| ✅ Done (Jul 2026) | MoneyPuck xG features added to the point-in-time dataset; win-model gate now **passes** (item 8) — first model to beat Elo out-of-sample |
| ✅ Done (Jul 2026) | xG model wired into production serving (item 9); prediction log + market snapshots made durable and the snapshot job put on a schedule (item 10) |
| ✅ Done (Jul 2026) | Season scorecard (`scorecard.py`, item 11) — logged predictions vs actuals vs market closing consensus. Verified on a synthetic season; reports "nothing to score" until the real data arrives |
| Oct 2026 (season start) | Publish predictions pre-game daily; score vs actuals and vs market benchmark |
| Jan 2027 (mid-season) | Interim scorecard (~600 games): log loss / Brier / calibration vs market consensus |
| Apr 2027 (season end) | Full-season evaluation: is the model within striking distance of the market's log loss (~0.66)? Publish the scorecard either way |

The calendar is a hard constraint: a prediction model is only proven by
predictions logged **before** games and scored after. The 2026-27 season is
the validation run.

### Reality check on accuracy

- NHL is a high-variance, low-scoring sport: home teams win ~53-55%, the
  market's closing consensus is right ~59-60%, and the best public models
  reach ~62%. Anything above the high 50s out-of-sample is genuinely strong.
- Single-season differences of 1-2% accuracy are mostly noise; that's why the
  gate uses proper scoring rules on held-out seasons instead.

---

## Product Direction

A public, transparent prediction site — the MoneyPuck model, not a picks
service:

1. **Daily predictions page** — win probability + expected total per game,
   timestamped before puck drop. The existing Firebase site already renders
   daily output; the copy shifts from "bets" to "predictions."
2. **Live accuracy scorecard** — running log loss / Brier / calibration plot
   for the season, shown next to the market benchmark. Publishing the
   scorecard *especially when it's unflattering* is the differentiator; most
   prediction sites don't dare. The numbers exist as of item 11
   (`scorecard.py --json`); rendering them on the site is the open part.
3. **Goalie-news reactivity** — DailyFaceoff starter scraping already exists;
   confirmed-starter updates are the one input that moves NHL win
   probabilities intraday. "Prediction updated: starter confirmed" is a
   genuinely useful, NHL-specific feature.
4. **Projected Stanley Cup bracket** (`playoff_bracket.py`, site tab) — the
   whole bracket projected forward from the actual first-round matchups with
   team form frozen at the end of the regular season, each slot marked ✅/❌
   against what happened. It went 5/15 on the 2025-26 playoffs. Publishing a
   miss rate that plain is the same discipline as the scorecard: an NHL
   playoff bracket is close to a coin-flip tournament, and a model that
   claimed otherwise would be lying.
5. **Multi-sport** — the sibling `mlblines` project covers the NHL off-season
   with the same architecture.

Audience-building follows the same transparency logic: publish daily, show the
scorecard, let the verified record be the marketing. Costs stay near zero (the
NHL API is free; Firebase hosting is effectively free at this scale).

---

## Quick Start

```bash
# Daily predictions
python main.py --conservative

# Score past predictions against results
python bet_tracker.py --check

# Rebuild the point-in-time multi-season training set (+ weekly model refit)
python build_training_set.py

# Gate: does a candidate model beat the Elo + home-ice baseline out-of-sample?
python model_gate.py                  # exit 0 = ship candidate, exit 1 = ship baseline
python model_gate.py --ablation       # grouped feature ablation
python model_gate.py --totals         # total-goals candidate vs league-average Poisson

# Calibration: Platt/isotonic on a held-out season vs raw probabilities
python calibrate.py

# Season scorecard: logged predictions vs actual results vs the market
python scorecard.py                      # current season to date
python scorecard.py --json data/scorecard.json

# Projected playoff bracket (annual; writes data/playoff_bracket.json for the site)
python playoff_bracket.py                # most recent completed playoffs
python playoff_bracket.py --season 20252026

# Season backtest: the SHIPPED model (persisted ml_models/ artifacts, not a
# refit) against a real season, game by game, vs the Elo baseline.
# NOTE: backtest.py / backtest_day.py / backtest_full_season.py /
# backtest_season.py / backtest_historical_blends.py / backtest_blend_ratios.py
# all predate the July 2026 rebuild and call the quarantined leaky model
# (src/models/ml_model.py) — they report on a model that hasn't shipped in
# months. Use model_backtest.py instead.
python model_backtest.py                 # the shipped model's own held-out season
python model_backtest.py --season 20252026 --json data/model_backtest_20252026.json

# Snapshot the market's devigged consensus (runs 3x daily in CI via
# .github/workflows/market-snapshot.yml; this is the manual equivalent)
python scripts/snapshot_market.py

# System status
python system_report.py
```

---

## Project Structure

```
nhllines/
├── src/
│   ├── data/
│   │   ├── nhl_data.py            # NHL API (api-web.nhle.com) fetching
│   │   ├── historical_dataset.py  # Point-in-time multi-season dataset builder
│   │   ├── moneypuck_data.py      # MoneyPuck shot-level xG, aggregated per game/team
│   │   ├── odds_fetcher.py        # Market data (evaluation benchmark)
│   │   └── player_data.py
│   ├── models/
│   │   ├── xg_production.py       # Shipped win model: xG drop-goalie logistic + Platt
│   │   ├── elo_baseline.py        # Elo + home-ice logistic (gate baseline)
│   │   ├── calibration.py         # Platt/isotonic probability calibration
│   │   ├── elo_production.py      # Elo serving path (fallback) + persisted artifacts
│   │   ├── model.py               # Similarity model (totals only; being replaced)
│   │   ├── ml_model.py            # Quarantined (leaky training)
│   │   └── ml_model_streamlined.py  # Quarantined (leaky training)
│   ├── analysis/
│   │   ├── ev_calculator.py       # Model-vs-market comparison math
│   │   ├── bet_tracker.py         # Prediction outcome tracking
│   │   ├── model_feedback.py      # Calibration tracking
│   │   ├── goalie_tracker.py      # Goalie data & starter confirmation
│   │   ├── injury_tracker.py      # Injury tracking
│   │   ├── advanced_stats.py      # MoneyPuck advanced metrics
│   │   └── prediction_log.py      # Append-only prediction log (data/predictions_log.jsonl)
│   └── utils/
├── build_training_set.py          # CLI: build dataset + refit production model
├── model_gate.py                  # CLI: candidate vs baseline gate (+ ablation, + totals)
├── calibrate.py                   # CLI: held-out-season calibration
├── scorecard.py                   # CLI: logged predictions vs actuals vs market
├── playoff_bracket.py             # CLI: projected Stanley Cup bracket vs actual
├── model_backtest.py              # CLI: shipped model vs Elo, game by game, on a real season
├── backtest*.py                   # Legacy — predate the July 2026 rebuild, call the
│                                  #   quarantined ml_model.py. Use model_backtest.py.
├── scripts/
│   └── snapshot_market.py         # CLI: devigged market-consensus snapshot (cron job)
├── docs/                          # Documentation
├── data/                          # Data files (gitignored except the records below)
│   ├── predictions_log.jsonl      # Append-only prediction record (committed)
│   └── market_snapshots/          # One devigged odds snapshot per run (committed)
├── cache/                         # API cache (gitignored)
├── ml_models/                     # *.json coefficients + calibrators (tracked);
│                                  #   quarantined *.pkl (gitignored)
├── web/                           # Web interface
└── config.json                    # API keys (gitignored)
```

---

## Configuration

The NHL data API (api-web.nhle.com) is free and needs no key.

For the market benchmark, create `config.json`:
```json
{
    "odds_api_key": "YOUR_KEY_1",
    "odds_api_key_two": "YOUR_KEY_2",
    "odds_api_key_three": "YOUR_KEY_3"
}
```
Free keys: https://the-odds-api.com

---

## Philosophy

1. **Data quality > model complexity** — clean point-in-time data beats fancy
   algorithms. The July 2026 diagnosis is the proof: leakage, not algorithm
   choice, sank the original model.
2. **Baselines before complexity** — a candidate model ships only if it beats
   Elo + home-ice on held-out log loss AND Brier (`model_gate.py`).
3. **Calibration is the product** — a probability is only useful if 60% means
   60%. Proper scoring rules and held-out-season calibration, never
   hand-tuned confidence constants.
4. **The market is the benchmark** — the consensus implied probability is the
   strongest public predictor (~59-60% accurate, log loss ~0.66). Score
   against it honestly rather than pretending it doesn't exist.
5. **Predictions count only if logged first** — timestamped before puck drop,
   scored after, published either way.

---

## Documentation

All documentation is in the `docs/` folder:
- `docs/QUICK_REFERENCE.md` — usage
- `docs/SYSTEM_OVERVIEW.md` — complete system documentation
- `docs/MODEL_FEEDBACK.md` — feedback system

Note: older docs in `docs/` predate the July 2026 reframe and rebuild; where
they conflict with this README, this README wins.

---

## License

Private project — not for distribution.

Last Updated: July 26, 2026
