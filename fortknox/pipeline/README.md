# High Slot scoring pipeline

Scores every NHL shot with a full-data expected-goals model and writes the
game sheets, team and player tables the High Slot site is built from. It
moved here from `xgcalc/`, whose five-feature tagger model is a separate
model for shots a person tags from the stands.

It is trained on the NHL's own feed so it scores tonight's games from exactly
the data it learned on.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

```bash
.venv/bin/python nhl_backfill.py --seasons 2015-2026   # raw feed -> cache/nhl/ (~400 MB, once)
```

```bash
.venv/bin/python build_nhl_dataset.py             # -> data/nhl_shots.parquet (1.7M attempts)
```

```bash
.venv/bin/python train_nhl_xg.py                  # honest evaluation
```

```bash
.venv/bin/python train_nhl_xg.py --production     # the served model -> data/nhl_xg_model.joblib
```

```bash
.venv/bin/python nhl_sheets.py                    # game sheets + team/player/lines tables -> ../data/
.venv/bin/python nhl_live.py --sheets ../data     # tonight's games so far -> ../data/live/
```

**Shooter baselines.** Vs. Expected measures each shooter against his own
finishing history, not against zero: `fit_shooter_baseline.py` scores every
cached season's shots (`build_nhl_dataset.py` first), shrinks each shooter's
career GAx per shot toward zero by how much of it chance explains, and tests
the result on every season since 2018 against the seasons before it (it beat
zero by 12.8% on 2018-2026). It writes `data/shooter_baseline.json`, which
`nhl_sheets.py` reads for each skater's `gax_exp`. The file covers the season in
progress and the one before: refit at the start of each season, or the new
season's page falls back to plain GAx.

```bash
.venv/bin/python nhl_backfill.py --seasons 2015-2026 && .venv/bin/python build_nhl_dataset.py
.venv/bin/python fit_shooter_baseline.py          # -> data/shooter_baseline.json
```

**Predictive check.** `fit_validation.py` asks, for every season since 2015-16,
how well each team number over the first N games (points %, goal share, xG
share, 5v5 xG share, deserved points %) predicts points % over the rest of
the season, and writes `../app/model/validation.json` for the Model page's
chart. Rerun it after a refit.

```bash
.venv/bin/python fit_validation.py                # -> ../app/model/validation.json
```

**Lines.** `src/data/nhl_units.py` rebuilds which five skaters each team had
on the ice for every 5v5 second, and `nhl_sheets.py` adds up time, xG, goals
and attempts for every forward trio, defence pair and pair of teammates
(`lines.json`), plus each skater's team numbers with him on the bench (the
`*_off` keys in `players.json`). Units with under a minute together are
dropped.

**Data.** Play-by-play and shift charts for every final regular-season and
playoff game since 2015-16. When the shift-chart API has nothing for a game
(57 games of 2024-25 and the first ~50 of 2026-27), the backfill rebuilds it
from the NHL's HTML time-on-ice reports, which match the API shift for shift
where both exist. Shot coordinates and types agree with MoneyPuck's to within
0.3 ft (median) on the 98% of 2018+ shots that join.

**What the public feed can't give.** Passes and zone entries are not logged,
so cross-ice feeds and true rushes are invisible. The model gets proxies
built from the event trail instead (`src/data/nhl_events.py`): seconds since
the play was last outside the offensive zone and since the shooting team won
the puck, lateral movement and middle-crossings from the previous event, and
rebounds split by what came before (save, miss, block). Shift charts add
fatigue: how long the shooter and each unit had been on.

**Drift.** Logging changes season to season — a shot within 3 s of another
was 4% of non-goals in 2015 and 10% in 2025, and goal rates in tight fell
while mid-range rose. A model weighted evenly over 2015-2022 overstated
2023-25 goals by 9-16%. Seasons are now weighted 0.6× per year back and the
model is recalibrated (isotonic) on the latest season; measurements are in
`src/models/nhl_xg.py`.

| train ≤2022, calibrate 2023 | AUC | log loss | xG/goals |
|---|---|---|---|
| full model, test 2024 | 0.7671 | 0.22055 | 1.005 |
| full model, test 2025 | 0.7572 | 0.22644 | 1.062 |
| MoneyPuck-equivalent features, 2025 | 0.7540 | 0.22704 | 1.062 |
| MoneyPuck's own xG, 2025 | 0.7774 | 0.22256 | 1.004 |

MoneyPuck still ranks shots better; our inputs match theirs, so the gap is
their model, and how much of it is out-of-sample isn't knowable from here.
The production model (train 2015-2024, calibrate 2025) scores the 2026-27
games it has never seen at AUC 0.776 and 851 xG for 849 goals (139 games).

**After every game.** `.github/workflows/xg-game-sheets.yml` runs every 20
minutes from noon to 4am ET, fetches newly final games (the raw cache rides
in the Actions cache), rebuilds the season with `nhl_sheets.py`, force-pushes
the output as one commit to the orphan branch `xg-sheets-data`, and
dispatches `fortknox-deploy.yml`, which builds the site from it. While games
are on, each run also scores them so far with `nhl_live.py` into `live/` on
the same branch (games still waiting on their official sheet included), and
the site shows those as live or provisional game pages.
