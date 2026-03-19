"""
MLB Machine Learning Model
XGBoost-based model for predicting MLB game outcomes.
~62 features including pitcher stats, park factors, bullpen quality,
L/R splits, rest days, and team form.
"""

import pickle
from pathlib import Path
import numpy as np

try:
    import xgboost as xgb
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False
    print("Warning: XGBoost not installed. ML features disabled.")


class MLBMLModel:
    """MLB game prediction model with ~62 features."""

    FEATURE_NAMES = [
        # Team season stats (0-9)
        "Home Win%", "Home RS/G", "Home RA/G", "Home Run Diff/G", "Home Home Win%",
        "Away Win%", "Away RS/G", "Away RA/G", "Away Run Diff/G", "Away Road Win%",
        # Team recent form (10-15)
        "Home Form Win%", "Home Form RS", "Home Form RA",
        "Away Form Win%", "Away Form RS", "Away Form RA",
        # Derived differentials (16-19)
        "Win% Diff", "RS Diff", "RA Diff", "Form Win% Diff",
        # Home pitcher stats (20-29)
        "Home P ERA", "Home P WHIP", "Home P K/9", "Home P BB/9",
        "Home P HR/9", "Home P FIP", "Home P Quality", "Home P IP",
        "Home P GS", "Home P Handedness",
        # Away pitcher stats (30-39)
        "Away P ERA", "Away P WHIP", "Away P K/9", "Away P BB/9",
        "Away P HR/9", "Away P FIP", "Away P Quality", "Away P IP",
        "Away P GS", "Away P Handedness",
        # Park & context (40-45)
        "Park Factor", "Home Rest Days", "Away Rest Days",
        "Home B2B", "Away B2B", "Day/Night",
        # Bullpen stats (46-49)
        "Home Bullpen ERA", "Home Bullpen Quality",
        "Away Bullpen ERA", "Away Bullpen Quality",
        # Home/road splits (50-53)
        "Home Split RS", "Home Split RA",
        "Away Road Split RS", "Away Road Split RA",
        # L/R matchup features (54-57)
        "Home Bat vs Opp Hand OPS", "Away Bat vs Opp Hand OPS",
        "Home P Avg Against", "Away P Avg Against",
        # Streaks & momentum (58-61)
        "Home Streak", "Away Streak",
        "Home Form Trend", "Away Form Trend",
    ]

    def __init__(self):
        self.model_win = None
        self.model_total = None
        self.model_spread = None
        self.is_trained = False
        self.model_path = Path(__file__).parent.parent.parent / "ml_models"
        self.model_path.mkdir(exist_ok=True)

    def extract_features(self, home_stats, away_stats, home_form, away_form,
                         home_pitcher=None, away_pitcher=None, context=None):
        """
        Extract ~62 features for prediction.

        Args:
            home_stats: Season standings dict
            away_stats: Season standings dict
            home_form: Recent form dict
            away_form: Recent form dict
            home_pitcher: Pitcher stats dict
            away_pitcher: Pitcher stats dict
            context: Additional context (park, rest, bullpen, splits, etc.)
        """
        if home_pitcher is None:
            home_pitcher = {}
        if away_pitcher is None:
            away_pitcher = {}
        if context is None:
            context = {}

        hp = home_pitcher
        ap = away_pitcher

        # Home/away win percentages for splits
        h_gp = max(home_stats.get("games_played", 1), 1)
        a_gp = max(away_stats.get("games_played", 1), 1)
        h_home_w = home_stats.get("home_wins", 0)
        h_home_l = home_stats.get("home_losses", 0)
        h_home_gp = max(h_home_w + h_home_l, 1)
        a_away_w = away_stats.get("away_wins", 0)
        a_away_l = away_stats.get("away_losses", 0)
        a_away_gp = max(a_away_w + a_away_l, 1)

        features = [
            # Team season stats (0-9)
            home_stats.get("win_pct", 0.5),
            home_stats.get("runs_scored_pg", 4.5),
            home_stats.get("runs_allowed_pg", 4.5),
            home_stats.get("run_diff_pg", 0.0),
            h_home_w / h_home_gp,
            away_stats.get("win_pct", 0.5),
            away_stats.get("runs_scored_pg", 4.5),
            away_stats.get("runs_allowed_pg", 4.5),
            away_stats.get("run_diff_pg", 0.0),
            a_away_w / a_away_gp,

            # Recent form (10-15)
            home_form.get("win_pct", 0.5),
            home_form.get("avg_rs", 4.5),
            home_form.get("avg_ra", 4.5),
            away_form.get("win_pct", 0.5),
            away_form.get("avg_rs", 4.5),
            away_form.get("avg_ra", 4.5),

            # Differentials (16-19)
            home_stats.get("win_pct", 0.5) - away_stats.get("win_pct", 0.5),
            home_stats.get("runs_scored_pg", 4.5) - away_stats.get("runs_scored_pg", 4.5),
            home_stats.get("runs_allowed_pg", 4.5) - away_stats.get("runs_allowed_pg", 4.5),
            home_form.get("win_pct", 0.5) - away_form.get("win_pct", 0.5),

            # Home pitcher (20-29)
            hp.get("era", 4.50),
            hp.get("whip", 1.30),
            hp.get("k_per_9", 8.0),
            hp.get("bb_per_9", 3.2),
            hp.get("hr_per_9", 1.2),
            hp.get("fip", 4.30),
            hp.get("quality_score", 50) / 100.0,
            min(hp.get("innings_pitched", 0) / 200.0, 1.0),  # Normalized
            min(hp.get("games_started", 0) / 32.0, 1.0),
            1.0 if hp.get("handedness") == "L" else 0.0,

            # Away pitcher (30-39)
            ap.get("era", 4.50),
            ap.get("whip", 1.30),
            ap.get("k_per_9", 8.0),
            ap.get("bb_per_9", 3.2),
            ap.get("hr_per_9", 1.2),
            ap.get("fip", 4.30),
            ap.get("quality_score", 50) / 100.0,
            min(ap.get("innings_pitched", 0) / 200.0, 1.0),
            min(ap.get("games_started", 0) / 32.0, 1.0),
            1.0 if ap.get("handedness") == "L" else 0.0,

            # Park & context (40-45)
            context.get("park_factor", 100) / 100.0,
            min(context.get("home_rest_days", 1) / 5.0, 1.0),
            min(context.get("away_rest_days", 1) / 5.0, 1.0),
            1.0 if context.get("home_rest_days", 1) == 1 else 0.0,  # B2B
            1.0 if context.get("away_rest_days", 1) == 1 else 0.0,
            context.get("is_night", 1.0),

            # Bullpen (46-49)
            context.get("home_bullpen_era", 4.00),
            context.get("home_bullpen_quality", 50) / 100.0,
            context.get("away_bullpen_era", 4.00),
            context.get("away_bullpen_quality", 50) / 100.0,

            # Home/road splits (50-53)
            context.get("home_split_rs", 4.5),
            context.get("home_split_ra", 4.5),
            context.get("away_road_split_rs", 4.5),
            context.get("away_road_split_ra", 4.5),

            # L/R matchup (54-57)
            context.get("home_bat_vs_opp_hand_ops", 0.725),
            context.get("away_bat_vs_opp_hand_ops", 0.725),
            hp.get("avg_against", 0.250),
            ap.get("avg_against", 0.250),

            # Streaks (58-61)
            context.get("home_streak", 0) / 10.0,
            context.get("away_streak", 0) / 10.0,
            context.get("home_form_trend", 0.0),
            context.get("away_form_trend", 0.0),
        ]

        return np.array(features).reshape(1, -1)

    def train(self, games, standings, team_forms, pitcher_cache=None, bullpen_cache=None):
        """Train ML models on historical game data."""
        if not HAS_XGBOOST:
            print("Cannot train: XGBoost not installed")
            return False

        print("Training MLB ML models on historical data...")

        X_train = []
        y_win = []
        y_total = []
        y_spread = []

        for game in games:
            home = game["home_team"]
            away = game["away_team"]

            if home not in standings or away not in standings:
                continue

            home_stats = standings[home]
            away_stats = standings[away]
            home_form = team_forms.get(home, {"win_pct": 0.5, "avg_rs": 4.5, "avg_ra": 4.5})
            away_form = team_forms.get(away, {"win_pct": 0.5, "avg_rs": 4.5, "avg_ra": 4.5})

            # Get pitcher stats from cache if available
            hp = {}
            ap = {}
            if pitcher_cache:
                hp = pitcher_cache.get(game.get("home_pitcher_id"), {})
                ap = pitcher_cache.get(game.get("away_pitcher_id"), {})

            # Context with defaults for historical games
            ctx = {
                "park_factor": home_stats.get("park_factor", 100),
                "home_rest_days": 1,
                "away_rest_days": 1,
                "is_night": 1.0,
                "home_bullpen_era": bullpen_cache.get(home, {}).get("bullpen_era", 4.00) if bullpen_cache else 4.00,
                "home_bullpen_quality": bullpen_cache.get(home, {}).get("bullpen_quality", 50) if bullpen_cache else 50,
                "away_bullpen_era": bullpen_cache.get(away, {}).get("bullpen_era", 4.00) if bullpen_cache else 4.00,
                "away_bullpen_quality": bullpen_cache.get(away, {}).get("bullpen_quality", 50) if bullpen_cache else 50,
                "home_split_rs": home_stats.get("runs_scored_pg", 4.5),
                "home_split_ra": home_stats.get("runs_allowed_pg", 4.5),
                "away_road_split_rs": away_stats.get("runs_scored_pg", 4.5),
                "away_road_split_ra": away_stats.get("runs_allowed_pg", 4.5),
                "home_bat_vs_opp_hand_ops": 0.725,
                "away_bat_vs_opp_hand_ops": 0.725,
                "home_streak": 0,
                "away_streak": 0,
                "home_form_trend": 0.0,
                "away_form_trend": 0.0,
            }

            features = self.extract_features(home_stats, away_stats, home_form, away_form,
                                             hp, ap, ctx)
            X_train.append(features[0])
            y_win.append(1 if game.get("home_win") else 0)
            y_total.append(game.get("total_runs", 9))
            y_spread.append(game.get("run_diff", 0))

        if len(X_train) < 50:
            print(f"Not enough training data: {len(X_train)} games")
            return False

        X_train = np.array(X_train)
        y_win = np.array(y_win)
        y_total = np.array(y_total)
        y_spread = np.array(y_spread)

        # Win probability model
        self.model_win = xgb.XGBClassifier(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.04,
            min_child_weight=3,
            subsample=0.8,
            colsample_bytree=0.75,
            gamma=0.1,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=42,
            eval_metric='logloss',
        )
        self.model_win.fit(X_train, y_win)

        # Total runs model
        self.model_total = xgb.XGBRegressor(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.04,
            min_child_weight=3,
            subsample=0.8,
            colsample_bytree=0.75,
            gamma=0.1,
            random_state=42,
        )
        self.model_total.fit(X_train, y_total)

        # Run line (spread) model
        self.model_spread = xgb.XGBRegressor(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.04,
            min_child_weight=3,
            subsample=0.8,
            colsample_bytree=0.75,
            gamma=0.1,
            random_state=42,
        )
        self.model_spread.fit(X_train, y_spread)

        self.is_trained = True
        self.save_models()
        print(f"  MLB ML models trained on {len(X_train)} games ({len(self.FEATURE_NAMES)} features)")
        return True

    def predict(self, home_stats, away_stats, home_form, away_form,
                home_pitcher=None, away_pitcher=None, context=None):
        """Predict game outcome."""
        if not self.is_trained or not HAS_XGBOOST:
            return None

        features = self.extract_features(home_stats, away_stats, home_form, away_form,
                                         home_pitcher, away_pitcher, context)

        home_win_prob = self.model_win.predict_proba(features)[0][1]
        expected_total = self.model_total.predict(features)[0]
        expected_spread = self.model_spread.predict(features)[0]

        return {
            "home_win_prob": float(home_win_prob),
            "away_win_prob": float(1 - home_win_prob),
            "expected_total": float(expected_total),
            "expected_spread": float(expected_spread),
        }

    def save_models(self):
        if not self.is_trained:
            return
        for name, model in [("win_model.pkl", self.model_win),
                            ("total_model.pkl", self.model_total),
                            ("spread_model.pkl", self.model_spread)]:
            with open(self.model_path / name, "wb") as f:
                pickle.dump(model, f)

    def load_models(self):
        try:
            with open(self.model_path / "win_model.pkl", "rb") as f:
                self.model_win = pickle.load(f)
            with open(self.model_path / "total_model.pkl", "rb") as f:
                self.model_total = pickle.load(f)
            with open(self.model_path / "spread_model.pkl", "rb") as f:
                self.model_spread = pickle.load(f)
            self.is_trained = True
            return True
        except FileNotFoundError:
            return False


def blend_ml_and_similarity(ml_pred, similarity_pred, ml_weight=0.45):
    """
    Blend ML predictions with similarity-based predictions.
    Default 45% ML, 55% similarity for baseball (pitching matchups
    introduce more variance than hockey).
    """
    if ml_pred is None:
        return similarity_pred

    return {
        "home_win_prob": ml_weight * ml_pred["home_win_prob"] + (1 - ml_weight) * similarity_pred["home_win_prob"],
        "away_win_prob": ml_weight * ml_pred["away_win_prob"] + (1 - ml_weight) * similarity_pred["away_win_prob"],
        "expected_total": ml_weight * ml_pred["expected_total"] + (1 - ml_weight) * similarity_pred["expected_total"],
    }
