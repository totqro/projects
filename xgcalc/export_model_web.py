#!/usr/bin/env python3
"""
Dump the saved logistic pipeline to JSON so the browser can score shots.

    python export_model_web.py        # writes web/xg_model.json and .js

The five-feature logistic model is a scaler, two one-hot maps and 26
coefficients — small enough to ship as static JSON and evaluate in a few
lines of JavaScript, which is what web/scatter.html does. Nothing here is
approximated: the numbers are lifted straight off the fitted pipeline, and
`--check` reruns both paths on the same rows to prove they agree.

Not included: the isotonic calibrator in data/xg_calibrator.json. The CLI
(score_tagged.py) does not apply it either, so the web page matches the CLI.
"""

import json
import sys
from pathlib import Path

import joblib
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from xg_model import CATEGORICAL, FEATURES, MODEL_PATH, NUMERIC, SHOT_TYPE_MERGE
from zone_tagging import GOAL_X, ZONE16_NAMES

OUT = ROOT / "web" / "xg_model.json"
# Same model as a script, for web/tracker.html: it runs from file:// at the
# rink with no network, where fetch() of a local JSON file is refused.
OUT_JS = ROOT / "web" / "xg_model.js"


def export() -> dict:
    model = joblib.load(MODEL_PATH)
    prep, clf = model.named_steps["prep"], model.named_steps["clf"]
    scaler = prep.named_transformers_["num"]
    onehot = prep.named_transformers_["cat"]
    names = list(prep.get_feature_names_out())

    # Map every category to the column it lands in. Categories folded into
    # sklearn's infrequent bucket point at that shared column; categories the
    # encoder never saw are absent, and score as all-zeros (handle_unknown
    #="ignore"), which is what the pipeline does.
    cat_columns = {}
    infrequent = onehot.infrequent_categories_
    for i, feature in enumerate(CATEGORICAL):
        shared = f"cat__{feature}_infrequent_sklearn"
        rare = set(infrequent[i]) if infrequent[i] is not None else set()
        mapping = {}
        for category in onehot.categories_[i]:
            column = shared if category in rare else f"cat__{feature}_{category}"
            if column in names:
                mapping[str(category)] = column
        cat_columns[feature] = mapping

    # Merged-away types (SNAP) score as the level they were folded into, the
    # same thing predict_xg does before the pipeline sees them.
    shot_map = cat_columns["shot_type"]
    for alias, target in SHOT_TYPE_MERGE.items():
        if target in shot_map:
            shot_map[alias] = shot_map[target]

    return {
        "features": FEATURES,
        "numeric": {
            "names": NUMERIC,
            "mean": scaler.mean_.tolist(),
            "scale": scaler.scale_.tolist(),
        },
        "categorical": {"names": CATEGORICAL, "columns": cat_columns},
        "columns": names,
        "coef": clf.coef_[0].tolist(),
        "intercept": float(clf.intercept_[0]),
        "geometry": {"goal_x": GOAL_X, "zone_names": ZONE16_NAMES},
    }


def score_js_style(spec: dict, row: dict) -> float:
    """The JavaScript scorer, in Python — the reference the web page copies."""
    index = {name: i for i, name in enumerate(spec["columns"])}
    x = [0.0] * len(spec["columns"])
    for i, name in enumerate(spec["numeric"]["names"]):
        mean, scale = spec["numeric"]["mean"][i], spec["numeric"]["scale"][i]
        x[index[f"num__{name}"]] = (float(row[name]) - mean) / scale
    for name in spec["categorical"]["names"]:
        column = spec["categorical"]["columns"][name].get(str(row[name]))
        if column is not None:
            x[index[column]] = 1.0
    z = spec["intercept"] + sum(c * v for c, v in zip(spec["coef"], x))
    return 1.0 / (1.0 + np.exp(-z))


def check(spec: dict) -> None:
    """Both paths, same rows. Any drift here means the page is lying."""
    import pandas as pd
    from xg_model import predict_xg

    rng = np.random.default_rng(0)
    rows = pd.DataFrame({
        "distance": rng.uniform(3, 80, 400),
        "angle_from_net": rng.uniform(0, 150, 400),
        "is_rebound": rng.integers(0, 2, 400),
        "shot_type": rng.choice(["WRIST", "SNAP", "SLAP", "TIP", "BACK",
                                 "DEFL", "WRAP", "UNKNOWN", "NOT_A_TYPE"], 400),
        "situation": rng.choice(["EV_5v5", "PP_5v4", "SH_4v5", "EV_3v3",
                                 "EN_AGAINST", "OTHER", "NOT_A_SITUATION"], 400),
    })
    truth = predict_xg(joblib.load(MODEL_PATH), rows)
    ours = np.array([score_js_style(spec, r) for _, r in rows.iterrows()])
    worst = float(np.abs(truth - ours).max())
    print(f"  max |sklearn - exported| over {len(rows)} rows: {worst:.3e}")
    if worst > 1e-9:
        sys.exit("  exported model does not reproduce the pipeline")
    print("  exported model reproduces the pipeline")


def main():
    spec = export()
    text = json.dumps(spec, separators=(",", ":"))
    OUT.write_text(text)
    OUT_JS.write_text(f"window.XG_MODEL={text};\n")
    print(f"Wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size/1000:.1f} KB) "
          f"and {OUT_JS.relative_to(ROOT)}, {len(spec['columns'])} columns")
    check(spec)


if __name__ == "__main__":
    main()
