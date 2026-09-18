# MLB Game Prediction Model

Win probability and expected total runs for every MLB game, built only from
information available before first pitch and shipped only after beating a
baseline on held-out seasons.

**Status:** Rebuilt September 2026, following the July 2026 NHL rebuild
**Deployment:** https://lknox.web.app/mlblines/

---

## Why it was rebuilt

The previous model lost to "always pick the home team." On the 2026 games in
its own published backtest it picked 51.1% of winners while the home team won
53.1%, and its log loss of 0.702 was worse than a coin flip. Causes:

1. **No pitchers in the prediction that counted.** Probable starters were
   fetched but only fed an XGBoost model trained with every historical game's
   pitcher stats set to league-average defaults. That model learned to ignore
   pitching.
2. **Current standings stamped onto old games.** Training rows used today's
   standings and today's bullpen numbers for games months in the past.
3. **Similarity matching instead of a model.** Win probability came from
   averaging outcomes of "similar" games, then went through hand-tuned
   confidence and shrinkage constants fitted to a few dozen bets.
4. **Back-to-back features.** MLB teams play almost daily, so rest flags carry
   no signal. They are gone.
5. **A's games silently skipped.** The odds feed calls them "Athletics", which
   didn't map to a team.

## How it works now

**Data** (`src/data/historical_dataset.py`) — every regular-season game since
2021 from the MLB Stats API, plus game logs for every probable starter. A
single `StateReplayer` walks games in date order and snapshots features before
applying each day's results. The daily run uses the same replayer, stopped at
yesterday, so training and serving can't drift apart.

| Feature | Built from |
|---|---|
| Elo difference | Every prior result, K=4, 1/3 reversion each season |
| Starter FIP difference | Probable starter's K%, BB+HBP%, HR% before the game, prior season at 0.6 weight, each rate shrunk toward a replacement-level prior |
| Starter K−BB% difference | Same logs |
| Starter depth difference | Outs per start, shrunk |
| Bullpen difference | Season-to-date runs allowed per bullpen out, shrunk |
| Run differential difference | Season-to-date run diff per game, shrunk |

2021 is burn-in only. Training rows start in 2022. The schedule's probable
pitcher matched the actual starter in 39 of 40 sampled 2025 games.

**Win model** (`src/models/win_model.py`) — logistic regression on those six
features. It ships only if it beats Elo + home field on **both** log loss and
Brier on the held-out season. Platt calibration is adopted only if it improves
both metrics on a season it never saw. It currently does not, so raw
probabilities ship.

**Totals model** (`src/models/totals_model.py`) — Poisson GLM on starter FIP,
starter depth, bullpens, team run rates, venue park factor (three prior
seasons) and league scoring level. Negative-binomial dispersion turns the
expected total into P(over). It ships only if it beats the league average on
both RMSE and likelihood.

## Results (September 17, 2026)

Leave-one-season-out, training on every other season:

| Held-out season | Always home LL | Elo LL | Pitcher model LL | Beats Elo |
|---|---|---|---|---|
| 2022 | 0.6910 | 0.6747 | 0.6706 | yes |
| 2023 | 0.6925 | 0.6811 | 0.6778 | yes |
| 2024 | 0.6924 | 0.6812 | 0.6774 | yes |
| 2025 | 0.6900 | 0.6800 | 0.6796 | yes |
| 2026 to date | 0.6915 | 0.6855 | 0.6831 | yes |

The totals GLM beats the league average in all five seasons too.

Blind 2026 backtest (`backtest.py`), models trained on 2022–2025 only:

| Predictor | Games | Accuracy | Log loss | Brier |
|---|---|---|---|---|
| This model | 2285 | 55.5% | 0.6831 | 0.2451 |
| Elo + home field | 2285 | 55.7% | 0.6855 | 0.2462 |
| Always home | 2285 | 52.9% | 0.6915 | 0.2492 |
| This model, market games | 280 | 58.2% | 0.6694 | 0.2385 |
| Market closing consensus | 280 | 56.8% | 0.6713 | 0.2394 |

Elo edges the model on accuracy while losing on both proper scoring rules.
That is exactly why accuracy doesn't decide the gate. The model looks level
with the market, but 280 games is noise. Market snapshots only start in late
July 2026, so the real comparison is the 2027 season's prediction log.

## Daily outputs

- `mlbdata/latest_analysis.json` — what the site renders: model and market
  probabilities, the model's side, starters, bullpens, park.
- `mlbdata/predictions_log.jsonl` — append-only, one line per game logged
  before first pitch, with the market price at that moment and model versions.
- `recommendations` in the analysis file are the model's side of each game at
  the best available price, tracked by `bet_tracker.py`. They are not filtered
  for edge over the market, because no edge over the market is established.

## Commands

```bash
python build_training_set.py   # fetch history, rebuild dataset, run gates, refit models
python model_gate.py           # print both gates + LOSO; exit 1 if any gate fails
python backtest.py             # blind backtest of the latest season -> backtest_results.json
python main.py                 # today's predictions (add --no-odds to skip the market)
python scripts/snapshot_market.py
```

CI (`.github/workflows/daily-mlb-analysis.yml`) runs `main.py` daily. On
Sundays it first runs the refit, gate and backtest, then commits the model
JSON, the prediction log and the site data.

## Structure

```
mlblines/
├── src/
│   ├── data/historical_dataset.py  point-in-time replay (training + serving)
│   ├── data/mlb_data.py            live pitcher season lines for display
│   ├── data/odds_fetcher.py        market prices (benchmark)
│   ├── models/win_model.py         Elo baseline, pitcher logistic, gate, calibration
│   ├── models/totals_model.py      NB GLM, league-average baseline, gate
│   ├── serving.py                  today's slate through the shipped models
│   └── analysis/                   prediction log, run history, pick tracking
├── build_training_set.py · model_gate.py · backtest.py · main.py
├── ml_models/*.json                shipped coefficients + gate numbers (tracked)
└── mlbdata/                        site data, prediction log, market snapshots
```

## Known gaps

- Bullpen outs are estimated from innings played, not per-reliever logs.
- No lineup, platoon or injury information. Lineups post too late for a
  morning run.
- Starters announced after the morning run are scored with the
  replacement-level prior and flagged "SP TBD" on the site.
