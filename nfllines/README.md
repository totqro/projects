# NFL Game Prediction Model

Pre-game **win probability** (primary) and **expected points per team**
(secondary) for every NFL regular-season and playoff game, built with the
evaluation discipline of the NHL rebuild (`../nhllines/README.md`): point-in-time
features, one code path for history and serving, leave-one-season-out gating on
proper scoring rules, and a single, one-time test-set evaluation against the
betting market.

**Status:** built September 2026. Test set scored once. Not wired into the site,
CI, or deploy scripts. Not a betting tool: no stakes, no edges, no picks.

---

## Honest results (the one-time 2024–2025 test, 570 games)

The market is the benchmark, never a feature. Scored once by `evaluate_test.py`
after every modelling choice was frozen on 2015–2023.

**Win model** (569 games; one tie excluded)

| Predictor | Log loss | Brier | Accuracy | ECE |
|---|---|---|---|---|
| Market (de-vigged closing moneyline) | **0.5981** | **0.2059** | 0.684 | 0.028 |
| **This model** (10 features) | 0.6119 | 0.2117 | **0.687** | 0.055 |
| Elo baseline (Stage 0) | 0.6224 | 0.2164 | 0.654 | 0.044 |

* Model − market gap: log loss **+0.0138** (95% bootstrap CI [−0.0002, +0.0270]),
  Brier +0.0058 [−0.0004, +0.0118]. Both intervals just touch zero: the gap is
  real in direction but within noise at 570 games.
* Model − Elo: log loss −0.0105 [−0.0243, +0.0032] — the improvement over Elo is
  also within noise on the test set alone (it is not within noise on the nine
  LOSO seasons, see below).
* Straight-up favourite agreement with the market: **84.9%**.
* Accuracy ties the market (68.7% vs 68.4%), but accuracy is not evidence: the
  market is better calibrated (ECE 0.028 vs 0.055) and better on both proper
  scoring rules.

Breakdowns (log loss, model / Elo / market):

| Segment | n | Model | Elo | Market |
|---|---|---|---|---|
| Weeks 1–4 | 127 | 0.6377 | 0.6422 | 0.6428 |
| Weeks 5–18 | 416 | 0.6067 | 0.6177 | 0.5849 |
| Playoffs | 26 | 0.5689 | 0.6018 | 0.5912 |
| Starter QB changed from previous game | 128 | 0.5876 | 0.6383 | 0.5644 |
| No QB change | 441 | 0.6190 | 0.6178 | 0.6079 |
| Major non-QB injury swing (top decile) | 85 | 0.5968 | 0.6505 | 0.5932 |
| 2024 | 285 | 0.6032 | 0.6102 | 0.5892 |
| 2025 | 284 | 0.6207 | 0.6347 | 0.6070 |

The model's entire advantage over Elo sits in the QB-change and injury segments
(where it is close to the market); on plain games it is no better than Elo. The
QB-change segment carries the documented caveat below: the schedule's QB column is
the actual starter, so on the rare surprise-start game the backtest sees
something the closing line did not.

**Points model** (570 games)

| Predictor | Home RMSE / MAE | Away RMSE / MAE | Margin RMSE / MAE | Total RMSE / MAE |
|---|---|---|---|---|
| Market (implied team totals / spread / total) | **9.19 / 7.38** | **8.77 / 6.99** | **12.49 / 9.69** | **12.92 / 10.10** |
| **This model** (ridge, two rows per game) | 9.29 / 7.40 | 8.98 / 7.12 | 12.77 / 9.95 | 13.08 / 10.24 |
| League average + home adjustment | 10.00 / 7.96 | 9.68 / 7.76 | 14.30 / 11.10 | 13.51 / 10.56 |

The points model beats the trivial baseline on every target and trails the
market on every target; its margin is on average 1.9 points from the closing
spread. Unlike the NHL totals model, it earned the right to ship. In this
one-time test, the points model's own margin named the same favourite as the
win probability in 89.8% of games.

**Serving change after the test (2026-09-18): coherent output.** Two numbers
naming two favourites is a defect, so the shipped margin now comes from the win
probability, `margin = σ·Φ⁻¹(p)`, and the points model supplies only the total.
Team points are `(total ± margin) / 2` (`src/models/coherent.py`). Agreement is
100% by construction. The change was chosen on the LOSO 2015–2023 out-of-fold
predictions (2,449 games), not on the test set. It was equal or better on every
points metric there: margin RMSE 12.933 vs 12.970, home RMSE 9.459 vs 9.480,
away RMSE 9.241 vs 9.245. The reverse direction, a win probability from the
points margin, was rejected because it cost log loss (0.6251 vs 0.6223). The
test table above was not re-scored. The first coherent predictions are logged
as model version `nfl-win-v1+coherent-points-v2`, so the scorecard never pools
them with v1 rows.

Reliability (test set, model): the 0.4–0.5 bin ran cold (104 games, predicted
0.45, observed 0.34) and the 0.6–0.7 bin ran hot (109 games, 0.65 → 0.71). Platt
and isotonic calibrators were both rejected by LOSO (neither beat the raw
probabilities on log loss and Brier), so the raw probabilities ship.

---

## Hard rules and how they are enforced

1. **No market data in features.** `spread_line`, `total_line`, moneylines and
   the odds columns are read in exactly one place, `evaluate_test.py`. The feature
   engine is fed `nflverse.feature_frame()`, which drops them.
   `tests/test_market_ban.py` (a) asserts no feature column is a market column,
   (b) greps every feature/model source file for market column names, and (c)
   rebuilds two seasons of features with the market columns replaced by random
   noise and asserts every feature is bit-identical.
2. **Split.** Train 2015–2023, warm-start 2014 (priors only), test 2024–2025.
   `tests/test_split.py`. `evaluate_test.py` writes `data/processed/TEST_EVALUATED`
   and refuses to run twice.
3. **No preseason.** `nflverse.filter_game_types` keeps `REG/WC/DIV/CON/SB` only
   (nflverse spells preseason `PRE`; the schedule loader returns none, and
   play-by-play is restricted to `REG/POST`). Applied to schedules, play-by-play,
   snap counts and injuries. `tests/test_no_preseason.py`.
4. **Point-in-time, one code path.** `src/features/engine.py` walks the schedule
   one `(season, week)` at a time; features for a week see only earlier weeks;
   the week's results are folded in afterwards. Serving (`predict.py`) is the same
   walk stopped before the target week. `build_dataset.py --verify N` rebuilds N
   random games from scratch and asserts exact equality (verified: 40/40 games ×
   131 columns, bit-exact). `tests/test_point_in_time.py` also perturbs the scores
   of every later game and asserts week-w features do not move.
   Three determinism bugs were caught by these checks during the build and
   fixed: season transitions that depended on the order teams were queried,
   float sums that depended on dict insertion order, and injury sums that
   depended on set iteration order (which changes with Python's per-process
   hash seed). Two builds in separate processes now produce byte-identical
   tables.
5. **Small feature set.** 10 features in the win model, ridge C=0.3.
6. **Every addition gated** on LOSO log loss AND Brier (`model_gate.py`).

---

## Gate log (LOSO over 2015–2023, 2,449 games; every number out-of-fold)

| Stage | Model | Log loss | Brier | Acc | Verdict |
|---|---|---|---|---|---|
| — | League-average home win rate (55.2%) | 0.6883 | 0.2476 | 0.552 | baseline |
| 0 | Elo: K=20, HFA=35, MOV multiplier, ⅓ reversion | 0.6376 | 0.2234 | 0.638 | the gate |
| 0 | same, no MOV multiplier | 0.6492 | 0.2287 | 0.632 | MOV kept |
| 1 | QB-adjusted Elo (team component + 800 Elo per EPA/dropback, K=15) | 0.6281 | 0.2194 | 0.646 | **pass** (beats Elo in all 9 seasons) |
| 2 | Week-1 prior as Elo season start | see below | | | not shipped in Elo |
| 3 | + EPA margin, success rate, sack, explosive, turnover, ST, early-week prior features | 0.6248 | 0.2178 | 0.651 | **pass** |
| 4 | + injury adjustment (`inj_total_diff`) | 0.6227 | 0.2169 | 0.657 | **pass** |
| — | ridge C 0.1 → 0.3 | 0.6227 | 0.2169 | | wash, C=0.3 |
| — | Normal(margin ridge / σ=12.94) win prob | 0.6231 | 0.2170 | 0.652 | alone: no |
| — | 50/50 blend logistic + Normal | **0.6223** | **0.2167** | 0.655 | **shipped** |

Per season the shipped model beats Stage-0 Elo in 9 of 9 held-out seasons
(largest gains 2021 and 2023, ~0.025; smallest 2022, 0.002).

**Stage 1 detail.** QB rating = shrunk, season-discounted EPA per dropback
(prior 200 pseudo-dropbacks at replacement level −0.12, or −0.07 for a
round-1/2 pick in his first two seasons; earlier seasons weighted 0.8 per year).
Measured on 2014–2023: starters average +0.04 EPA/dropback, backups −0.12,
rookies −0.07 regardless of draft slot (n small), year-to-year correlation
0.39. CPOE was tracked but adds nothing once EPA is in (its coefficient in a
next-season regression is zero) and was rejected as a feature. The Elo scale
of 800 per EPA/dropback implies a swing of roughly 10 points of Elo-margin
from an elite starter (+0.20) to a backup (−0.12) *before* shrinkage; with
shrinkage the realised swings are ~3–7 points, in line with expectation. The
scale plateaued from 600 to 1000 (LOSO 0.6281–0.6289).

**Stage 2 detail (the week-1 prior).** Built as specified
(`src/features/week1_prior.py`): last-season final team Elo, last-season EPA
margin, QB change, position-weighted returning snap share, coach change; the
target is the team's mean margin net of the QB credit the engine already gives.
Findings, all nested LOSO:

* A margin regression (a≈0.47 on last Elo) is the *wrong* objective: every
  component lost to flat ⅓ reversion. The reason is that for weeks 1–4 the
  LOSO-optimal flat reversion is **0**, not ⅓ (0.6439 vs 0.6484), while for the
  whole season ⅓ is optimal (0.6281 vs 0.6309).
* Choosing the coefficients directly by weeks 1–4 log loss: full carry of the
  team component (a≈1.0) plus returning snap share (+8 pts per unit of share)
  **pass the weeks 1–4 gate** (0.6484 → 0.6415) but degrade the full season
  (0.6281 → 0.6311). Last-season EPA margin, QB change (already in the QB swap)
  and coach change were each rejected on weeks 1–4. An early-season K boost was
  offered to the search and never chosen.
* Resolution: Elo keeps flat ⅓ reversion; the prior's inputs are emitted as
  features that decay linearly to zero over a team's first six games, and the
  win-model logistic weights them. `prior_last_team_pts_early_diff` and
  `prior_snap_return_early_diff` pass the Stage-3 gate together (0.6275 →
  0.6260); last-season EPA and coach change do not. In-season data takes over
  by construction at game 6, which is where the fitted decay put it.

**Stage 3 detail.** Rolling efficiency ratings
(`src/features/efficiency.py`, `EWMATracker`): per-game values adjusted by the
opponent's pre-game rating for the mirror stat, exponentially weighted (0.9 per
game, 0.8 per season boundary, 6 games of league-average prior). A "this-season
mean blended with a carried prior" variant was slightly worse. EPA alone is a
weaker predictor than MOV Elo (LOSO 0.641 vs 0.628) and mostly redundant with
it: on top of QB-adjusted Elo, EPA margin passes by 0.00004 and the pass/rush
split, CPOE, rest, time-varying HFA, neutral flag, weather, division and
playoff flags were all rejected. Ablation of the final set: dropping Elo costs
0.011, injuries 0.002, the early prior 0.001, everything else ≤0.0007.

**Stage 4 detail.** Miss probabilities from the final report × practice status,
measured on 2015–2023 (P(played): Out 0.00, Doubtful 0.01, Questionable 0.41 /
0.69 / 0.82 for DNP / limited / full practice, not listed 0.95). Player value =
contract APY % of cap (+0.03 × draft capital, which turned out irrelevant) ×
snap share; adjustment = value × (P(miss) − share of the last 8 games missed),
so a returning starter is positive and a long-term absence fades to zero as the
rolling stats absorb it. IR is read from weekly roster status. The single
team-total difference passes (0.6248 → 0.6227, ~9 points of margin per unit,
i.e. ≈0.9 points for a 10%-of-cap full-time starter); seven per-position-group
features overfit and fail; an OL-cluster count fails. Position-specific quality
stats (targets, pressures) were not attempted because the contract signal they
must beat is already in, and the group split it would refine did not pass.

**Points model.** Ridge on two team-game rows (own offence ratings, opponent
defence ratings, QB, venue, rest, weather, both injury totals, Elo), α=1000 (the grid was extended to 3000; 1000 was best on margin and total).
LOSO: home RMSE 9.47 vs baseline 10.07; margin 12.95 vs 14.14; total 13.51 vs
13.99 — passes on RMSE and MAE for all four targets. A Poisson/negative-binomial
alternative was not pursued: the ridge already beats the baseline and NFL
scores cluster on 3s and 7s rather than following a count distribution.

**Calibration.** Platt 0.6231/0.2171 and isotonic 0.6370/0.2190 vs raw
0.6223/0.2167 (LOSO on out-of-fold probabilities): raw ships. ECE 0.014 on the
training seasons.

Everything above is reproducible from `experiments/` (one script per stage,
outputs summarised in `data/processed/*.json`).

---

## Caveats and known limitations

* **Starting QB.** nflverse's schedule records the *actual* starter. Backtests
  therefore know the starter for every game, including the handful per season
  announced after the market closed. This favours the model slightly in the
  QB-change segment. At serving time the same columns hold nflverse's expected
  starter; re-run `predict.py` close to kickoff.
* **Contracts.** A player's contract for season S is the latest signed in or
  before S, so an in-season extension is visible a few weeks early. Labour-market
  data, not betting data; small.
* **Weekly granularity.** Thursday results are not used for Sunday's features.
* **Run schedule (live season).** Final injury reports are what the model was
  trained on, so predictions are logged only once they are out
  (`src/readiness.py`): run `predict.py` **Wednesday evening** for the Thursday
  game and **Saturday evening** for Sunday and Monday. Each run logs only games
  whose final report is published and that have not kicked off, and it refuses
  to log while any earlier game of the season still lacks a result or
  play-by-play. Held-back games are printed with the reason.
* **2026 week 2 was logged from a mid-week report.** Those predictions were
  run on Thursday 17 September, a day before the final report. The model saw
  6 game statuses; the final report had 105. The rows stand as logged. Only
  Giants–Rams was re-logged from the final report before kickoff (76.9%,
  down from 80.1%). The same run exposed a 365-day download cache that had
  frozen the 2026 season at its first fetch. The current season now always
  downloads fresh. Both fixes date from 2026-09-21.
* **Contract tie fix (2026-09-21).** When a player had two contracts signed
  in the same year, the one used for his value was whichever an unstable sort
  put last. That order differs between Apple Silicon and the x86 GitHub
  runner. The first CI run exposed it: the same game came out at 0.770 there
  and 0.769 locally. The rule is now explicit: take the larger same-year
  deal. The main-QB and main-coach picks also got explicit tie-breaks. Only
  the injury feature changed (correlation 0.9987 with the old one). The gate
  was re-run on 2015–2023 and made every decision the same way, with LOSO
  still 0.6223 / 0.2167. Coefficients moved by under 2%. The one-time test
  above scored the pre-fix coefficients; it was not re-run.
* **2026 injury files are thinner.** nflverse's 2026 injury data has about
  180–250 rows per week against about 330 historically, and no timestamp
  column. Watch whether that persists; it weakens the injury feature.
* **Ties** (10 in training, 1 in test) are excluded from the win model and kept
  for Elo updates and the points model.
* **Team codes** are normalised to current abbreviations (STL→LA, SD→LAC,
  OAK→LV) so franchise ratings survive relocation.
* `spread_line` is positive when the home team is favoured (checked: mean
  margin +7.7 when spread > 3, −7.0 when spread < −3).

---

## Layout

```
nfllines/
  README.md
  requirements.txt
  build_dataset.py      # point-in-time features for all games + from-scratch verification
  model_gate.py         # LOSO gate: forward selection, C, margin/Normal blend, ablation, points gate
  calibrate.py          # Platt vs isotonic vs raw, LOSO on out-of-fold probabilities
  evaluate_test.py      # the one-time 2024-2025 evaluation (refuses to run twice)
  predict.py            # serving: same engine, stopped before the target week; coherent output;
                        #   logs only games whose final injury report is out (src/readiness.py)
  scorecard.py          # logged pre-kickoff predictions vs results vs closing market
  src/config.py         # every frozen constant, with the experiment that chose it
  src/data/             # nflverse loaders + cache, game_type filter, team-game stats, injury context
  src/features/         # elo, qb, efficiency, week1_prior, injuries, engine, build
  src/models/           # loso, metrics, win_model, points_model, calibration, prediction_log
  tests/                # market ban, no preseason, split, point-in-time + recomputation
  experiments/          # the stage-by-stage scripts behind the gate log
  ml_models/            # win_model.json, points_model.json (chosen config + coefficients)
  data/raw/             # nflverse download cache (gitignored)
  data/processed/       # features.parquet, market.parquet, gate/test results (gitignored)
```

## Running it every week (GitHub Actions)

`.github/workflows/nfl-predictions.yml` runs `predict.py` on a schedule and
commits `data/predictions_log.jsonl`: Tuesday 6 pm, Wednesday 7 pm, Thursday
6 pm, Friday 7 pm, Saturday 6 pm and Sunday 8 am ET. Each run logs only the
games that are ready (final injury report out, not kicked off; see
`src/readiness.py`), so the Wednesday run logs the Thursday game and the
Friday and Saturday runs log Sunday and Monday. The extra runs are backups:
repeating a run never double-logs a day, and a game logged on several days
is scored on its last pre-kickoff row. Each run's predictions and the season
scorecard appear in the run's summary page. A failed run sends an email
because a missed pre-kickoff run cannot be made up. On a pull request the
workflow runs the tests and a dry run, and commits nothing.

CI never rebuilds or refits anything. It serves the frozen models straight
from `ml_models/*.json` (identical to the fitted models to machine
precision), and caches completed nflverse seasons between runs. The current
season is always re-downloaded.

## Quick start

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
export PYTHONPATH=.
.venv/bin/python build_dataset.py --verify 40     # ~1 min after the first download
.venv/bin/python model_gate.py --ablation
.venv/bin/python calibrate.py
.venv/bin/python -m pytest tests -q
.venv/bin/python predict.py            # Wednesday and Saturday evenings; picks the week itself
.venv/bin/python scorecard.py --season 2026
# evaluate_test.py has been run once; it will refuse to run again
```
