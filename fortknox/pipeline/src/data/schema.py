"""Held-out seasons for evaluating the full-data xG model.

Copied from xgcalc/src/data/schema.py when the game-sheet pipeline moved out
of xgcalc: the two models share this protocol. Keep the two in step.
"""

HOLDOUT_SEASONS = frozenset({2024, 2025})


def assert_no_holdout_leak(train_df) -> None:
    """Raise if a training frame contains a held-out season.

    Called by every script that fits a model. A guard rather than a comment
    because "remember not to train on 2024" is exactly the kind of rule that
    quietly breaks six months later.
    """
    leaked = sorted(set(train_df["season"].unique()) & HOLDOUT_SEASONS)
    if leaked:
        raise ValueError(
            f"Training data contains held-out season(s) {leaked}. "
            f"{sorted(HOLDOUT_SEASONS)} are reserved for evaluation and must "
            f"never be trained on — see HOLDOUT_SEASONS in schema.py."
        )
