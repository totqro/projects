# xgcalc — NHL expected goals

Shot-level xG for the NHL, built from MoneyPuck's public shots data.

**Status: data layer complete.** 905,483 cleaned shots across seasons
2018–2025, with 37 model features and a validated benchmark column. The model
itself is not built yet.

## Quick start

```bash
./.venv/bin/python build_dataset.py      # build data/shots.parquet
```

```bash
./.venv/bin/python validate_dataset.py   # sanity-check it
```

```bash
./.venv/bin/python xg_model.py           # train + evaluate the xG model
```

The builder reads MoneyPuck season CSVs already cached by the `nhllines` win
predictor (`../nhllines/cache/moneypuck_shots_{year}.csv`, ~65 MB each) rather
than re-downloading half a gigabyte. Pass `--raw-dir` to point elsewhere, or
`--download` to fetch seasons that aren't cached.

Useful flags: `--seasons 2023 2024 2025`, `--exclude-empty-net`, `--out-dir`.

## What's in the dataset

`data/shots.parquet` — one row per unblocked shot attempt (SHOT, MISS, GOAL;
MoneyPuck's file excludes blocked shots), 37.3 MB.

| Group | Columns |
|---|---|
| **Label** | `goal` (0/1) — 63,697 goals, 7.03% base rate |
| **Coordinates** | `x_adj`, `y_adj`, `y_abs` (attacking net always at x=+89), `x_raw`/`y_raw`, arena-bias-corrected `x_arena_adj`/`y_arena_adj` |
| **Geometry** | `distance`, `distance_arena_adj`, `angle_abs`, `angle_from_net`, `is_behind_net` |
| **Shot** | `shot_type` (WRIST/SNAP/SLAP/TIP/BACK/DEFL/WRAP/UNKNOWN), `shot_type_missing` |
| **Play context** | `is_rebound`, `prev_event`, `prev_event_zone`, `prev_event_x`/`_y`, `time_since_last_event`, `distance_from_last_event`, `speed_from_last_event`, `speed_imputed` |
| **Strength** | `strength_state` (raw, e.g. `5v4`), `strength_bucket` (EV/PP/SH, goalie-adjusted), `shooting_skaters`, `defending_skaters`, `skater_differential`, `is_empty_net`, `shooter_net_empty`, `pulled_goalie_state` |
| **Shooter** | `shooter_id`, `shooter_name`, `shooter_hand`, `off_wing`, `shooter_position`, `shooter_toi` |
| **Game state** | `period`, `period_format` (REGULATION/OT_3v3/OT_5v5), `is_overtime`, `time_seconds`, `time_since_faceoff`, `score_differential`, `is_home`, `is_playoff` |
| **Benchmark** | `mp_xg` — MoneyPuck's own xG. **Never a feature.** Our model gets measured against it. |

`src/data/schema.py` is the single source of truth: `FEATURE_COLUMNS` lists
what a model may train on, `LEAKY_COLUMNS` lists what it must not touch
(`goal`, `mp_xg`, `was_on_goal`).

The cleaned data behaves like hockey — goal rate falls monotonically from
14.9% inside 10 ft to 1.1% beyond 60 ft, and falls as the angle sharpens.
MoneyPuck's xG sums to 63,700 against 63,697 actual goals on our rows
(ratio 1.0001), which confirms no rows were dropped or duplicated in cleaning.

## Data quality — what we found and fixed

The raw feed has real defects. Each is handled explicitly, never silently.

**1. `shotAngle` mirrors shots taken from behind the net.** MoneyPuck computes
the angle against `|89 − x|`, so a shot from six feet *behind* the goal line
reports the same 57.5° as one from in front. This affects ~1.1% of shots
(10,100). Their column is kept as `mp_shot_angle`; we add `angle_from_net`
(0–180°, where >90° means behind the goal line) and `is_behind_net`. The fix
earns its keep — behind-net shots score at 4.5%, a rate the mirrored
convention can't express.

**2. `shotRush` is unusable — do not use it.** Its rate decays from 0.25%
(2018) to 0.06% (2025); real rush-shot rates are one to two orders of
magnitude higher, so the flag is either broken or means something far
narrower than "rush". Carried through as `is_rush_mp` for documentation only
and **excluded from `FEATURE_COLUMNS`**. Rush detection needs to be engineered
from the prev-event columns at modelling time. Fair warning: the obvious proxy
(last event outside the offensive zone within 4 seconds) shows *no* goal-rate
lift — 0.0702 vs 0.0703 — so this needs real work, not a one-liner.

**3. Skaters-on-ice is not strength state.** A pulled goalie puts a sixth
skater on the ice without earning a man advantage, so bucketing on raw skater
counts labels `5v6` (empty net) as shorthanded and `6v5` (own net pulled) as a
power play. On 2024 alone that misfiled 937 empty-net shots into "SH" and
inflated its apparent goal rate to **20.1%** against 7.3% for genuine
penalty-kill shots. `strength_bucket` subtracts the pulled goalie from each
side before comparing; `strength_state` keeps the raw count for description.
`validate_dataset.py` guards against this regressing.

**4. `speedFromLastEvent` divides by zero-second gaps.** When
`timeSinceLastEvent == 0` (~1% of shots) MoneyPuck reports speed equal to the
raw distance — an implicit divide-by-1, not a speed. We reproduce the same
value so the column stays comparable to theirs, and flag it with
`speed_imputed` so a model can learn to distrust those rows.

**5. `shotType` is missing on 0.1–1% of shots, and the missingness is
informative.** Missing-type shots sit at a median 9.1 ft from the net (vs 32.3
overall) and are rebounds 42% of the time (vs 6.6%) — net-front scrambles the
scorer couldn't classify. They score at 13.3%. Filled with `UNKNOWN` and
flagged rather than dropped; dropping would have thrown away the most
dangerous shots in the file and biased against recent seasons.

**6. Team codes change style mid-archive.** Seasons 2018–2020 use `L.A`,
`N.J`, `S.J`, `T.B`; 2021+ use `LAK`, `NJD`, `SJS`, `TBL` — the same four
franchises under two labels across 38,361 shots, which silently halves every
team-level split. Normalised to the NHL-API form; an unrecognised code raises
at build time rather than becoming a silent 38th team. `ARI` and `UTA` stay
distinct on purpose.

**7. The period number does not identify the game situation.** Regular-season
overtime is five minutes of 3-on-3 on open ice; playoff overtime is full
20-minute 5-on-5. Both are "period 4". At even strength they are opposite
environments — 3v3 OT scores at **13.1%** from a median 24 ft, playoff OT at
**5.3%** from 35 ft, against 6.4% in regulation. Raw `period` asks a model to
untangle a 2.5x swing in danger from an interaction with `is_playoff`;
`period_format` (REGULATION / OT_3v3 / OT_5v5) names it directly.

Regular-season period 5 would be the **shootout** — penalty shots from a
standing start, no defenders, no rebounds, converted around a third of the
time. MoneyPuck already excludes them (zero such rows across 2018–2025), but
the builder drops and *counts* them so a future archive that includes them
can't quietly poison the training set.

**8. `shooterLeftRight` is missing on ~3% of shots.** Filled with `"U"`.

### Known, not yet handled

- `shooter_toi` reaches 1,197 s — a 20-minute continuous shift is a tracking
  artifact, not a shift. 141 rows exceed 300 s. It's a live feature; consider
  clipping at modelling time.
- `y_arena_adj` reaches 55 ft against a rink half-width of 42.5 (3,153 rows) —
  the arena-bias rescaling can push coordinates off the ice. Not in the
  feature list; `y_adj`/`y_abs` are the safe ones.

Rows are only ever dropped for hard invalidity (bad event type, impossible
coordinates, out-of-range skater counts, non-binary label), and every drop is
counted and printed per season. Across 2018–2025 that is **32 rows out of
905,515** — all bad strength states in 2018–2021.

## Layout

```
xg_model.py            THE MODEL — 5 features; train, evaluate, save, score one shot
build_dataset.py       CLI: raw seasons -> data/shots.parquet, with drop accounting
validate_dataset.py    17 sanity checks; exits non-zero on failure
ablate_features.py     feature-count vs accuracy vs training time
train_logistic.py      strength-encoding comparison (--strength situation|state|bucket|none)
src/data/schema.py     source columns, feature/label/leak definitions, rink geometry
src/data/clean.py      all cleaning transforms, each documented with what was measured
src/data/shots.py      locating, downloading and reading raw season files
data/                  built dataset + saved model (gitignored — regenerable)
```

Using the model from your own code:

```python
import joblib, pandas as pd
from xg_model import predict_xg, FEATURES

model = joblib.load("data/xg_model.joblib")
shots = pd.DataFrame([{ "distance": 8, "angle_from_net": 10,
                        "shot_type": "WRIST", "is_rebound": 0,
                        "situation": "EV_5v5" }])
shots["xg"] = predict_xg(model, shots)     # 0.1937
```

## Evaluation protocol

**2024 and 2025 are never trained on.** Training is seasons 2018–2023
(666,342 shots); 2024 is the selection/validation season and 2025 the final
test. This is enforced in code, not by convention — `assert_no_holdout_leak()`
in `src/data/schema.py` raises if a training frame contains a held-out season,
and every script that fits a model calls it:

```python
HOLDOUT_SEASONS = frozenset({2024, 2025})
```

Honest accounting of what has already been looked at: the five-feature choice
and the strength-encoding choice were originally made against 2025, then
re-checked on 2024. Both have therefore informed decisions, so **neither is a
virgin holdout any more** and published numbers on them are optimistic by a
small margin. Seal a genuinely fresh season before making a claim that has to
survive outside scrutiny.

The cost of this protocol is recency: the model never sees the two most recent
seasons, and the drift documented below means recency matters. That is a
deliberate trade — a model that cannot be honestly evaluated is worth less
than one trained on two fewer seasons. For an operational refit (as opposed to
an evaluated one), retrain on everything and say so explicitly.

## The model

```bash
./.venv/bin/python xg_model.py                       # train, evaluate, save
```

```bash
./.venv/bin/python xg_model.py --shot 8 10 WRIST 0 EV_5v5    # score one shot
```

**Five features**, chosen because they carry ~99% of what a linear model can
extract from this data (see the ablation below) and because a five-term model
can be explained to someone who will never read the code:

| Feature | |
|---|---|
| `distance` | feet from the net |
| `angle_from_net` | 0° straight on, 90° on the goal line, >90° behind it |
| `shot_type` | WRIST / SNAP / SLAP / TIP / BACK / DEFL / WRAP / UNKNOWN |
| `is_rebound` | shot within 3 s of, and close to, a prior shot |
| `situation` | strength state, with 6v5 split by cause |

Default is **logistic regression, not the tree**: better per-situation
calibration (0.1256 vs 0.1543), a readable coefficient for every level, and it
gives up only 0.008 AUC. Calibration is what an xG model is for — the totals
have to be right. `--model tree` switches if ranking matters more.

| | AUC | log loss | sum(xG)/goals |
|---|---|---|---|
| ours, valid 2024 | 0.7582 | 0.22540 | **0.9989** |
| ours, test 2025 | 0.7422 | 0.23369 | 1.0732 |
| MoneyPuck, valid 2024 | 0.7785 | 0.21825 | 1.0231 |
| MoneyPuck, test 2025 | 0.7764 | 0.22215 | 1.0150 |

On 2024 the model totals goals almost exactly (0.9989) and beats MoneyPuck on
calibration while trailing it on AUC — MoneyPuck ranks individual shots
better, we total them better.

### What it learned

Coefficients are in log-odds, and the useful ones are not the obvious ones:

- `distance` −1.040 — by far the strongest single term, as it should be.
- `angle_from_net` −0.303.
- `SLAP` **+0.397**, the highest of any shot type — even though slap shots
  have the *lowest* raw goal rate in the dataset (4.8%). Once distance is
  controlled for, that reverses: slap shots look bad only because they are
  taken from far out. From the same spot a slapper beats a wrist shot
  (35 ft, 55°: .046 vs .029). This is the kind of thing a five-term model
  can show you and a 40-feature one cannot.
- `EN_AGAINST` +3.520 — shooting at an empty net, the single largest effect.

### Known weaknesses

- **Test-season over-prediction (1.0732).** 2024 calibrates at 0.999, 2025 at
  1.073, so this is drift, not bias — see the drift section below. Refit
  before using on a new season.
- **The top decile is over-valued** (predicts .258, actual .193). The model
  over-rates its best chances, driven partly by `EN_AGAINST` (1.211). Shrinking
  extreme predictions, or an isotonic recalibration layer, would help.
- **Not usable for shot sequences.** One-step lookback only; no rush term.

## Calibration

```bash
./.venv/bin/python train_formula.py
```

Fits the specified spec —
`goal ~ distance + angle + shotType + shotRebound + shotRush + strength_state`
— then runs the raw probabilities through `src/models/calibration.py`, ported
from and kept API-compatible with the win predictor's calibration module (same
three calibrator classes, same reliability/ECE helpers, same adoption gate).

Three disjoint, time-ordered slices, exactly the win model's protocol:

| | | |
|---|---|---|
| train the model | 2018–2023 | 666,342 shots |
| fit the calibrator | 2024 | model has never seen it |
| score everything | 2025 | neither has seen it |

Fitting the calibrator on 2024 does **not** violate the never-train-on-2024
rule: `assert_no_holdout_leak` guards the *model's* training set, and the
calibrator is a separate map fit on the model's *outputs*. A calibrator fit on
the model's own training data would be fit to its overconfidence.

### Result, scored on 2025

| method | log loss | Brier | ECE | sum/goals | AUC |
|---|---|---|---|---|---|
| uncalibrated | 0.23382 | 0.06333 | 0.00549 | 1.0710 | 0.7412 |
| platt | 0.23343 | 0.06314 | 0.00551 | 1.0690 | 0.7412 |
| **isotonic** | **0.23217** | **0.06279** | **0.00512** | 1.0709 | 0.7408 |

Both methods clear the gate (beat raw on log loss *and* Brier). **Isotonic is
adopted** — with ~120k shots per season there is far more data here than the
win model's ~1,300 games, so the flexibility pays instead of overfitting.

### Where the miscalibration actually is

Aggregate metrics almost completely hide it. ECE is 0.005 because 89,226 of
119,271 shots sit in the 0–0.1 bin and are well calibrated. The problem is at
the top, binned by raw prediction so every column describes the same shots:

| raw bin | n | raw | platt | isotonic | actual |
|---|---|---|---|---|---|
| 0.0–0.1 | 89,226 | .0434 | .0451 | .0446 | .0436 |
| 0.2–0.3 | 5,053 | .2386 | .2274 | **.1999** | .1775 |
| 0.3–0.4 | 1,058 | .3393 | .3190 | **.2338** | .2240 |
| 0.5–0.6 | 114 | .5509 | .5153 | .4667 | .3596 |
| 0.6–0.7 | 144 | .6521 | .6130 | .5533 | .3681 |
| 0.8–1.0 | 241 | .8850 | .8576 | .7601 | .6763 |

**Platt barely moves anything.** Two parameters cannot bend a sigmoid enough:
where the model says .339 and reality is .224, Platt offers .319. This is the
main reason the gate picks isotonic — worth knowing if Platt was the intended
choice.

**Isotonic fixes the mid-range and only partly fixes the top.** On the 0.2–0.4
band it lands almost exactly (.234 vs .224 actual), and that band holds 6,000
shots. Above 0.5 it still over-predicts, because that region is dominated by
empty-net shots whose conversion *collapsed in 2025* (49.4%, against 55.6% in
2024). A calibrator fit on 2024 cannot anticipate that. On 2024 in-sample
isotonic is near-exact all the way up (0.8–1.0 bin: .744 predicted vs .742
actual), which confirms the residual 2025 error is drift, not a limit of the
method.

### On `shotRush`

Included as specified. Its fitted coefficient is **+0.0179** — indistinguishable
from zero, consistent with the field being broken (data-quality note 2). It
costs nothing to keep and contributes nothing.

This spec also scores marginally below the five-feature model (AUC 0.7412 vs
0.7422) because `strength_state` is a weaker encoding than `situation` — see
the appendix below.

## Appendix: choosing the strength encoding

```bash
./.venv/bin/python train_logistic.py --compare
```

Logistic regression, trained on 2018–2023, validated on 2024, tested on 2025.
The strength term is a **selectable option** (`--strength`) so encodings can be
compared like for like — all other strength columns are stripped before the
chosen one is added back, or the comparison would be meaningless.

| Strength option | Valid 2024 AUC | Test 2025 AUC | Valid log loss |
|---|---|---|---|
| `situation` (15 levels, 6v5 split by cause) | 0.7580 | 0.7424 | 0.22503 |
| `state` (raw skater counts) | **0.7584** | **0.7427** | **0.22492** |
| `bucket` (EV/PP/SH) | 0.7576 | 0.7422 | 0.22511 |
| `none` | 0.7558 | 0.7418 | 0.22539 |
| *MoneyPuck's own xG* | *0.7785* | *0.7764* | *0.21825* |

**Global metrics hide the strength effect — do not judge the term by AUC.**
The table above says every strength encoding is worth ~0.002 AUC over none.
That is true and misleading: AUC is a ranking metric over 119k mostly-even-
strength shots, and it cannot see a systematic goal-total error inside a
situation. Per-situation calibration can:

| Level | n | goals | `none` | `bucket` | `situation` |
|---|---|---|---|---|---|
| EV_5v5 | 188,312 | 11,339 | 1.100 | 1.045 | **1.039** |
| PP_5v4 | 31,032 | 3,018 | 0.905 | 1.136 | 1.124 |
| PP_5v3 | 1,037 | 179 | **0.550** | 0.658 | **0.908** |
| SH_4v5 | 5,184 | 373 | 1.004 | 0.940 | 0.997 |
| EV_3v3 | 2,468 | 337 | 0.996 | 0.971 | 0.986 |
| *mean abs. error* | | | *0.1163* | *0.1331* | ***0.1023*** |

A location-only model **under-predicts power-play goals and over-predicts
even-strength ones** — it moves goals from the PP to 5v5. On 5v3 it misses
45% of them. Adding `situation` pulls 5v3 from 0.550 to 0.908 and gives the
best mean calibration error. Note `bucket` is *worse than nothing* (0.1331):
lumping 5v4 with 5v3 is more harmful than omitting strength entirely.

### Why strength is not already in the shot location

The intuitive argument is that a power play scores more only because it
generates better chances, so location features already capture it and a
strength term double-counts. Tested directly — comparing conversion inside
matched distance x angle bins — that holds only for the very best chances:

| Distance | Angle | EV_5v5 | PP_5v4 | ratio |
|---|---|---|---|---|
| 0–10 ft | 0–20° | .1640 | .1678 | **1.02** |
| 10–20 ft | 40–60° | .0903 | .1340 | 1.48 |
| 20–30 ft | 60–180° | .0262 | .0906 | 3.45 |
| 30–40 ft | 60–180° | .0142 | .0618 | **4.35** |
| 40–60 ft | 20–40° | .0176 | .0454 | 2.59 |

Median ratio across bins: **1.76**. Point-blank and straight on, a power-play
shot is worth the same as an even-strength one — the goalie cannot recover
either way, and location explains everything. From distance or a sharp angle,
the same coordinates are worth up to **4x more** on the power play, because
the goalie has been moved laterally by a cross-ice pass or is screened. That
is goalie *positioning*, and no x/y coordinate can express it. It is exactly
the residual the strength term carries.

### Calibration drift

Test-season calibration is off by 10% (predicts 9,449 goals against 8,565
actual) versus 1.4% on validation. This is real distribution drift, not a
bug — it is spread across `EV_5v5` and `PP_5v4` rather than concentrated in
one situation, and empty-net conversion genuinely collapsed in 2025 (49.4%,
against 55–65% in every prior season; MoneyPuck over-predicts there too, at
57.1%). A model trained through 2023 and applied to 2025 needs recency
weighting or recalibration. Worth fixing before anyone bets on the output.

## How many features do we need?

```bash
./.venv/bin/python ablate_features.py
```

Nested tiers, smallest to largest, on a linear and a tree model, tested on
held-out 2025. Fit time is on 666,342 training shots.

| Tier | n | fit (log / tree) | AUC log | AUC tree | ΔAUC tree | cal err (log) |
|---|---|---|---|---|---|---|
| geometry — distance, angle | 2 | 0.1s / 0.6s | 0.6937 | 0.7008 | — | 0.2353 |
| +shot_type, is_rebound | 4 | 0.4s / 0.9s | 0.7101 | 0.7192 | +0.0184 | 0.2207 |
| **+situation** | **5** | **0.7s / 1.1s** | **0.7422** | **0.7504** | **+0.0312** | **0.1256** |
| +location detail | 10 | 1.1s / 1.3s | 0.7435 | 0.7522 | +0.0018 | 0.1295 |
| +sequence | 15 | 1.7s / 1.6s | 0.7420 | 0.7549 | +0.0027 | 0.1271 |
| +game state | 22 | 2.0s / 2.8s | 0.7423 | 0.7558 | +0.0009 | 0.1301 |
| all | 40 | 3.6s / 3.2s | 0.7426 | 0.7588 | +0.0030 | 0.1550 |
| *MoneyPuck* | | | | *0.7764* | | *0.1778* |

**Training time is not a real constraint here.** The full 40-feature model
fits in 3.6s on two-thirds of a million shots. Going from 2 features to 40
costs about 3 seconds. Do not trade accuracy for training time at this scale;
if a feature helps, keep it.

**Five features carry almost everything.** `distance`, `angle_from_net`,
`shot_type`, `is_rebound`, `situation` reach AUC 0.7422 linear / 0.7504 tree.
The remaining 35 features add **+0.0004 to the linear model** — nothing — and
**+0.0084 to the tree**. The single largest jump in the whole table is adding
`situation` (+0.031), larger than shot type, which is further evidence for
keeping the granular level list.

**Does adding features hurt calibration? It does not replicate — the effect
is season-specific noise.** Evaluating the same tiers on 2024, the season that
informed no design decision:

| Tier | n | AUC 2024 | AUC 2025 | cal err 2024 | cal err 2025 |
|---|---|---|---|---|---|
| geometry | 2 | 0.7069 | 0.6937 | 0.2796 | 0.2353 |
| +shot | 4 | 0.7203 | 0.7101 | 0.2648 | 0.2207 |
| **+situation** | **5** | **0.7582** | **0.7422** | **0.1250** | **0.1256** |
| +location | 10 | 0.7599 | 0.7435 | 0.1182 | 0.1295 |
| +sequence | 15 | 0.7570 | 0.7420 | 0.1185 | 0.1271 |
| +game state | 22 | 0.7574 | 0.7423 | 0.1208 | 0.1301 |
| all | 40 | 0.7582 | 0.7426 | 0.1155 | 0.1550 |

On 2025 the 40-feature model has the *worst* calibration (0.1550); on 2024 it
has the *best* (0.1155). The sign flips, so that is variance, not a real
penalty for extra features. An earlier version of this README claimed
otherwise from the 2025 column alone — that claim was wrong.

**What does hold, on both seasons, is stability.** The five-feature model
calibrates at 0.1250 / 0.1256 across the two held-out seasons — essentially
identical. The 40-feature model swings 0.1155 / 0.1550. Same mean, far more
variance: it is fitting season-specific composition that does not carry
forward. For a model that has to be trusted on a season it has never seen,
consistency is the property worth buying, and it is the honest argument for
five features. The other two are that the accuracy is equivalent (AUC is flat
from tier 3 onward on *both* seasons) and that five terms can be explained.

**The linear model saturates; the tree does not.** After 5 features the
logistic model gains nothing and the sequence tier actively hurts it
(−0.0015), because it cannot represent the interactions. The tree keeps
gaining, which is where the remaining headroom is.

## Next

- Gradient boosting properly tuned — the tree already leads the linear model
  at every tier and has not saturated at 40 features.
- Recency weighting or recalibration for the drift documented above.
- Rush detection from reconstructed play-by-play sequences. The single
  prev-event lookback in this dataset cannot see a multi-event rush pattern,
  which is why the naive proxy showed no lift.
