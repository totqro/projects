# Feature search (Nov 2026)

Which of the win model's variables are worth keeping? This folder searched
every way we could afford, on a bigger dataset than the shipped model was fit
on. The winner, **core4**, runs as a shadow for the 2026-27 season.

## Setup

- **Data:** every regular-season game 2015-16 to 2025-26 (14,742 with the
  2014-15 warm-up season), point-in-time features, MoneyPuck xG for every
  game, actual starting goalies for every game, pregame Elo.
  `build_dataset.py` rebuilds `data/` (not committed, about 20 MB).
- **Rows:** both teams have played at least 5 games, the regime the xG model
  serves in.
- **Choosing:** leave-one-season-out over 2015-16 to 2023-24. Score =
  pooled log loss over the 7 normal seasons (2019-20 and 2020-21 are trained
  on but not scored, as in `model_gate.py`).
- **Locked test:** 2024-25 and 2025-26, touched once by `final.py`, walk-forward
  (each season predicted by a fit on every season before it).
- **Model:** L2 logistic on standardised features, C=0.1 (the shipped
  settings), fit exactly by Newton's method (`harness.py`).
- **Candidates:** 52 variables without goalies (the shipped 44, `elo_diff`,
  8 engineered differences), 64 with them.

## What was searched

`search.py <method>`; `run_all.sh` runs all of them. Results are in
`results_nogoalie/` and `results/` (with goalies), logs in `results/*.txt`.

| Method | Sets scored | Best LOSO log loss |
|---|---|---|
| Elo (4 vars) | 1 | 0.66686 |
| Shipped 44 | 1 | 0.67016 |
| Every subset up to 5 vars (4 with goalies) | 2.9M + 0.68M | 0.66389 (k=5) |
| Every combination of variable groups | 8,191 + 4,095 | 0.66390 |
| Forward, backward, floating stepwise | ~8k | 0.66356 |
| Lasso path | 30 | 0.66474 |
| Simulated annealing, 100 runs x 3,000 steps | ~300k | 0.66352 |
| Genetic, 300 x 250 | ~75k | 0.66341 |
| Gradient boosting (reference) | 4 | 0.66712 |

What it found:

- Every method converges on the same core: `elo_diff`, `xg_diff_rate_diff`,
  `home_b2b`, `away_b2b`. The exhaustive search's best set at each size 1-5
  is exactly forward selection's path.
- Gains stop around 6 variables and reverse past about 12. The top sets
  differ by 0.0002, which is noise.
- Raw goals per game, last-10 form, head-to-head, goalie stats and
  non-linear models add nothing.
- Early season (under 5 GP): last season's xG does not improve on Elo
  (`early.py`).

## Locked test (`final.py`, run once)

Log loss, lower is better. P = bootstrap probability of beating Elo.

| Set | Vars | 2024-25 | 2025-26 | Both | P(beats Elo) |
|---|---|---|---|---|---|
| Elo | 4 | 0.6663 | 0.6923 | 0.6793 | |
| Shipped 44 | 44 | 0.6673 | 0.6831 | 0.6752 | 0.94 |
| **core4** | 4 | 0.6636 | 0.6875 | 0.6756 | 1.00 |
| core6 | 6 | 0.6631 | 0.6889 | 0.6760 | 0.99 |
| Best LOSO set (genetic) | 12 | 0.6652 | 0.6902 | 0.6777 | 0.84 |

The best set on the search seasons did worse on the locked ones than core4,
the selection overfit the locked test exists to catch. The shipped 44's
2025-26 number flatters it: its variables were picked on that season.

## The shadow

`fit_core4.py` fits core4 on 2015-16 to 2025-26 and writes
`ml_models/core4_coefficients.json`, frozen for the season.
`src/models/core4_shadow.py` serves it; `main.py` logs it to
`data/shadow_core4_log.jsonl` for every game where both teams have 5 GP, and
`scorecard.py` prints a "SHADOW (shadow core4)" section. Decide at the
January scorecard, once it has 200+ games.
