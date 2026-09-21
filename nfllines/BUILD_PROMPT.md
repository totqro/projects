# Build an NFL game prediction model (`nfllines/`)

You are building a new NFL game prediction model in this repo, in `nfllines/`.
The repo already contains a rigorously rebuilt NHL model (`nhllines/`) and an
older MLB model (`mlblines/`). Follow the NHL project's evaluation discipline;
do not copy the MLB project's approach.

## Goals (in priority order)

1. **Primary — who wins.** A calibrated pre-game win probability for every
   regular-season and playoff game.
2. **Secondary — points scored by each team.** Expected home points and
   expected away points (and therefore expected margin and total).

**Success criterion:** get as close as possible to the betting market's
accuracy *without using market data as an input*. The market is the
benchmark we score against, never a feature. We are not building a betting
tool: no stake sizing, no "edges," no picks copy.

## Hard rules

1. **No market data in features — ever.** Spreads, totals, moneylines,
   win-total futures, implied team totals, line movement, public betting %:
   all banned as inputs, including anything derived from them. nflverse's
   schedule file contains `spread_line`, `total_line`, `home_moneyline`,
   `away_moneyline` — those columns are used **only** in the evaluation step.
   Add an automated check that fails if any feature column is derived from
   them.
2. **Data split.**
   - Training: 2015–2023 seasons (nflverse labels seasons by start year).
   - Warm-start data only: 2014 (to build priors for week 1 of 2015).
   - Test: 2024 and 2025 seasons (~570 games incl. playoffs). **Untouched
     until the model is frozen.** All feature selection, hyperparameters,
     and calibration are chosen with leave-one-season-out (LOSO)
     cross-validation inside 2015–2023. The test set is scored once, at the
     end. If you catch yourself wanting to iterate after seeing test
     results, stop and report instead.
3. **No preseason games.** Filter every nflverse dataset to
   `game_type in {REG, WC, DIV, CON, SB}` (verify the exact codes). No
   preseason plays in EPA, no preseason snaps, no preseason results. Week-1
   roster/depth/injury inputs come from the regular-season week-1 data.
4. **Point-in-time features only.** Every feature for a game uses only
   information available before kickoff of that game. Historical features
   must be computed by exactly the same code path that computes live
   features. Lesson from the NHL rebuild: the old NHL model had ~50%
   accuracy largely because of leakage and train/serve skew (current
   standings stamped onto old games; injury impact zeroed in training but
   live at prediction). Write a verification test that recomputes features
   from scratch for a random sample of games and asserts exact equality.
5. **Small feature sets.** ~2,400 training games. Target ~10–15 features in
   the win model. The NHL rebuild found 40–50 features on a small sample
   overfit. Use strong regularization (ridge/L2) and shrinkage.
6. **Gate every addition.** A component ships only if it beats the previous
   stage on LOSO log loss **and** Brier score. Accuracy alone is not
   admissible evidence.
7. **Scope.** Don't modify `nhllines/` or `mlblines/`. Reuse/adapt their
   ideas; import nothing that couples the projects unless you first extract
   a clean shared module and ask. Don't wire into the Firebase site, CI
   workflows, or deploy scripts, and don't commit, without asking.

## Read these first (the NHL framework to mirror)

- `nhllines/README.md` — the rebuild narrative, root causes, and gate
  philosophy. Read the whole "Honest Performance History" section.
- `nhllines/src/models/elo_baseline.py` — Elo + home advantage baseline.
- `nhllines/model_gate.py` — held-out gating on log loss and Brier, ablation.
- `nhllines/calibrate.py` — Platt vs isotonic calibration on held-out data.
- `nhllines/build_training_set.py` — point-in-time dataset construction and
  its exact-recomputation verification.
- `nhllines/scorecard.py` — scoring predictions vs actuals vs market,
  including the "no peeking" rules.
- `nhllines/src/analysis/prediction_log.py` — append-only pre-game logging.
- `nhllines/roster_turnover.py`, `nhllines/roster_change_vs_record.py` —
  offseason roster-change measurement, and validating it before wiring it in.

## Data

Use **nflverse** (try `nflreadpy`; fall back to `nfl_data_py` or the
nflverse GitHub release CSV/parquet files). Cache raw downloads under
`nfllines/data/raw/` (gitignored). Relevant datasets:

- Schedules/games: scores, `game_type`, `week`, `location` (home/neutral),
  `home_rest`/`away_rest`, `div_game`, `roof`, `surface`, `temp`, `wind`,
  `home_qb_name`/`away_qb_name` (+ ids), `home_coach`/`away_coach`,
  stadium. Market columns for evaluation only (verify `spread_line` sign
  convention before using it).
- Play-by-play (1999+): EPA, success, CPOE, pass/rush, sacks, turnovers,
  special teams.
- Snap counts (2012+), weekly rosters, depth charts.
- Injury reports (2009+): report status and practice participation.
- PFR advanced stats (2018+): pressures, coverage, receiving detail.
- Contracts (Over The Cap via nflverse): APY as % of cap. This is labor
  market data, not betting market data, so it is allowed.
- Draft picks.

**Known caveat:** schedule QB columns record the *actual* starter, not the
expected one. For nearly all games the starter is known by Friday, so accept
this, but document it and note the rare surprise-start cases as a slight
advantage over the market in backtests.

## Model design

### Stage 0 — baselines
- Always-home-team, and league-average home win rate.
- **Elo:** margin-of-victory multiplier, home-field term, flat 1/3
  season-to-season reversion to the mean (FiveThirtyEight NFL style). Tune K
  and home advantage with LOSO. This is the gate everything else must beat.

### Stage 1 — QB-adjusted Elo
- Split team strength into a team component and a QB component.
- QB rating: rolling EPA per dropback + CPOE with a career/prior-season
  prior, shrunk toward replacement level by sample size. Rookies get a
  draft-slot-based prior.
- When the starter isn't the team's usual QB, swap in that QB's value.
  Expected magnitude: several points (roughly 3–7+ for elite starters to
  backups). Measure it; don't hardcode.

### Stage 2 — week-1 prior (replaces flat reversion)
Name it the "week-1 prior" in code and docs (not "preseason"; preseason
games are never used). Fit on 2015–2023 to predict each team-season's
per-game point margin:

```
week1_prior = a·(last season final Elo)
            + b·(last season EPA/play margin, off minus def)
            + c·(QB change: new starter value − old starter value)
            + d·(position-weighted returning snap share)
            + e·(head coach change flag)
            + learned regression toward league mean
```

Add components one at a time; each must improve LOSO log loss on
**weeks 1–4** specifically. Expect QB change and last-season efficiency to
matter most and snap continuity to matter little — let the data decide.
Then fit how fast in-season data takes over from the prior (expect this
season's data to dominate around weeks 5–6).

### Stage 3 — efficiency features (the candidate win model)
Regularized logistic regression (and/or a margin regression, see below),
home-minus-away differences where sensible:

Tier 1:
1. Elo / QB-adjusted Elo difference.
2. QB rating difference (starter-aware).
3. Opponent-adjusted rolling EPA/play, offense and defense, split pass/rush,
   blended with the week-1 prior with a fitted decay.
4. Success rate (offense/defense).
5. Home field: time-varying (it has declined from ~2.5 pts pre-2020 to ~1.5).
   Neutral-site and international flags.
6. Rest: days rest, rest differential, off-bye, Thursday short week.

Tier 2 (heavy shrinkage, keep only if gated in):
7. Sack rate allowed/forced.
8. Explosive play rate.
9. Turnover luck: fumble recovery rate and INT rate as regressors toward the
   mean, not rewarded as skill.
10. Point differential vs record; one-score game record (luck).
11. Special teams EPA.
12. Travel distance and time zones crossed (esp. West→East early kickoffs).

Tier 3 (situational, test individually):
13. Weather: wind > ~15 mph, cold, dome team outdoors (mostly totals).
14. Division game flag.
15. Week 18 "nothing to play for" / resting starters flag (document how it's
    determined point-in-time).

Explicitly excluded: head-to-head history, streaks/momentum, ATS records,
referees, public betting data, anything from preseason games.

### Stage 4 — injury adjustment
1. **Status → miss probability.** Estimate from 2015–2023 data, P(miss) by
   final Friday status × practice participation (Out ≈ 100%, Doubtful
   ≈ 90–95%, Questionable ≈ 20–30%, not listed ≈ 1–2%). Train on these
   *probabilities*, not on who ended up playing, because only the Friday
   report exists at serving time.
2. **Player value above replacement** (next player on the depth chart, not
   zero), by position:
   - QB: handled by the Stage 1 QB swap, not here.
   - WR/TE: target share, EPA/target, yards per route run (2018+).
   - Edge: pressures, pressure rate, sacks.
   - CB: snap share + coverage stats (noisy, lean on contract/draft).
   - OL: count missing starters (no good public blocking data); model the
     extra loss when multiple linemen are out.
   - RB: rushing/receiving EPA. Expect a small value (replacement RBs
     perform close to starters). Test it; don't assume it's large.
   - Universal quality signal for every position: contract APY % of cap +
     draft capital.
3. **Fit by position group, not per player.** Regress the margin not
   explained by team rating + QB on expected value missing per position
   group, with strong shrinkage. Test whether multiple CBs or OL out
   compounds.
4. **No double counting.** Rolling stats already absorb a player's
   absence. Adjustment = value × (P(miss today) − share of rolling-window
   games he missed). A returning star produces a positive adjustment.
   After a few weeks on season-ending IR, fold the loss into the team
   rating as a roster change and drop the weekly adjustment.
5. Build order: QB swap → Friday-status probabilities × contract/draft
   value by position group → position-specific quality stats (keep only if
   they beat contract/draft) → OL/CB cluster effects. Gate each step.

### Points model (secondary goal)
- Predict **expected points for each team**: a team's offense vs the
  opponent's defense (EPA-based), plus home field, pace/neutral pass rate,
  weather, and injuries. Start with a regularized linear model per team-game
  (two rows per game), then consider count/negative-binomial alternatives.
  NFL scores cluster on 3 and 7, so don't assume Poisson fits; check it.
- Derive margin = home − away and total = home + away.
- Baseline to beat: league-average points per team with a home adjustment.
  Gate on LOSO RMSE and MAE for team points, margin, and total. Warning from
  NHL: its totals model never beat the league-average baseline. That's an
  acceptable, reportable outcome.
- **Coherence:** also convert the predicted margin into a win probability
  (Normal, σ fitted on training data, ~13–14 points) and compare that with
  the direct logistic win model under the gate. Ship whichever wins, or a
  blend chosen by LOSO. Make sure the shipped win probability and shipped
  margin never disagree on the favorite without a flag.

### Calibration
Platt scaling vs isotonic, chosen by LOSO within 2015–2023 (mirror
`nhllines/calibrate.py`). Report expected calibration error and a
reliability table.

## Evaluation (the final, one-time test on 2024–2025)

Report, for our model, the Elo baseline, and the market:

- **Win model:** log loss, Brier, accuracy, ECE, reliability table.
  Market benchmark = de-vigged closing moneyline probabilities (fall back to
  spread converted via the fitted σ if moneylines are missing; say which).
- **Points model:** RMSE/MAE for home points, away points, margin, total.
  Market benchmark = closing spread for margin, closing total for total,
  implied team totals (total/2 ± spread/2) for team points.
- Straight-up agreement rate between our favorite and the market favorite.
- **Breakdowns:** weeks 1–4 vs 5–18 vs playoffs; games with a QB change or
  a major non-QB injury vs games without; each test season separately.
- Bootstrap confidence intervals on the log-loss and Brier gaps vs the
  market. With ~570 games, say plainly when a gap is within noise.
- Honest framing: the NFL closing line is the most efficient of the major
  sports (favorites win ~65–67%). "Close to the market" is the goal;
  report the gap whatever it is.

## Project layout (suggested)

```
nfllines/
  README.md              # mirror NHL README: what it is, honest results, gate log
  requirements.txt
  build_dataset.py       # point-in-time features for all games, + verification
  model_gate.py          # LOSO gating, ablations, win + points
  calibrate.py
  evaluate_test.py       # the one-time 2024–2025 evaluation
  src/data/              # nflverse loaders, caching, game_type filtering
  src/features/          # elo, qb, efficiency, week1_prior, injuries, situational
  src/models/            # win model, points model, calibration
  tests/                 # leakage checks, market-column ban, recomputation equality
  data/raw/              # gitignored cache
```

## Checkpoints (stop and report at each)

1. **Data pipeline done:** row counts per season and game type, preseason
   confirmed excluded, leakage/recomputation tests passing.
2. **Baselines:** LOSO results for home-team, Elo, QB-adjusted Elo.
3. **Week-1 prior + efficiency model:** gate table for each addition, final
   feature list with coefficients.
4. **Injury layer:** status→miss-probability table, position-group values,
   gate results.
5. **Points model:** gate results vs the league-average baseline.
6. **Freeze:** list the exact frozen configuration, then (after I confirm)
   run the one-time 2024–2025 test and write results into the README,
   including results that are unflattering.

At every checkpoint, report numbers, not adjectives. If something doesn't
pass the gate, say so and leave it out. If a result looks too good (e.g.,
beating the closing line by a wide margin), assume leakage and investigate
before reporting it as real.
