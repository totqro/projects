"""
Machine Learning Model for NHL Predictions
Uses XGBoost to predict game outcomes based on team statistics.
Blends with similarity-based model for improved accuracy.
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
    print("Install with: pip install xgboost")


class NHLMLModel:
    """Machine learning model for NHL game predictions."""
    
    def __init__(self):
        self.model_win = None
        self.model_total = None
        self.model_spread = None
        self.is_trained = False
        self.model_path = Path(__file__).parent.parent.parent / "ml_models"
        self.model_path.mkdir(exist_ok=True)
        
    def extract_features(self, home_stats, away_stats, home_form, away_form):
        """
        Extract features for ML model from team statistics.
        Returns numpy array of features.
        """
        features = [
            # Home team stats
            home_stats.get("win_pct", 0.5),
            home_stats.get("points_pct", 0.5),
            home_stats.get("goals_for_pg", 3.0),
            home_stats.get("goals_against_pg", 3.0),
            home_stats.get("home_wins", 0) / max(home_stats.get("games_played", 1), 1),
            
            # Away team stats
            away_stats.get("win_pct", 0.5),
            away_stats.get("points_pct", 0.5),
            away_stats.get("goals_for_pg", 3.0),
            away_stats.get("goals_against_pg", 3.0),
            away_stats.get("road_wins", 0) / max(away_stats.get("games_played", 1), 1),
            
            # Recent form (last 10 games)
            home_form.get("win_pct", 0.5),
            home_form.get("avg_gf", 3.0),
            home_form.get("avg_ga", 3.0),
            away_form.get("win_pct", 0.5),
            away_form.get("avg_gf", 3.0),
            away_form.get("avg_ga", 3.0),
            
            # Derived features
            home_stats.get("goals_for_pg", 3.0) - home_stats.get("goals_against_pg", 3.0),  # Home goal diff
            away_stats.get("goals_for_pg", 3.0) - away_stats.get("goals_against_pg", 3.0),  # Away goal diff
            home_stats.get("win_pct", 0.5) - away_stats.get("win_pct", 0.5),  # Win % differential
            home_form.get("win_pct", 0.5) - away_form.get("win_pct", 0.5),  # Form differential
        ]
        
        return np.array(features).reshape(1, -1)
    
    def train(self, games, standings, team_forms):
        """
        Train ML models on historical game data.
        
        Args:
            games: List of completed games with outcomes
            standings: Current team standings
            team_forms: Recent form for all teams
        """
        if not HAS_XGBOOST:
            print("Cannot train: XGBoost not installed")
            return False
        
        print("Training ML models on historical data...")
        
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
            home_form = team_forms.get(home, {"win_pct": 0.5, "avg_gf": 3.0, "avg_ga": 3.0})
            away_form = team_forms.get(away, {"win_pct": 0.5, "avg_gf": 3.0, "avg_ga": 3.0})
            
            features = self.extract_features(home_stats, away_stats, home_form, away_form)
            X_train.append(features[0])
            
            # Labels
            y_win.append(1 if game.get("home_win") else 0)
            y_total.append(game.get("total_goals", 6))
            y_spread.append(game.get("goal_diff", 0))
        
        if len(X_train) < 50:
            print(f"Not enough training data: {len(X_train)} games")
            return False
        
        X_train = np.array(X_train)
        y_win = np.array(y_win)
        y_total = np.array(y_total)
        y_spread = np.array(y_spread)
        
        # Train win probability model (classification)
        # Optimized hyperparameters for better accuracy
        self.model_win = xgb.XGBClassifier(
            n_estimators=150,  # Increased for better learning
            max_depth=6,  # Slightly deeper for complex patterns
            learning_rate=0.05,  # Lower for more stable learning
            min_child_weight=3,  # Prevent overfitting
            subsample=0.8,  # Row sampling for robustness
            colsample_bytree=0.8,  # Feature sampling
            gamma=0.1,  # Minimum loss reduction
            random_state=42,
            eval_metric='logloss'
        )
        self.model_win.fit(X_train, y_win)
        
        # Train total goals model (regression)
        # Optimized for predicting continuous values
        self.model_total = xgb.XGBRegressor(
            n_estimators=150,
            max_depth=6,
            learning_rate=0.05,
            min_child_weight=3,
            subsample=0.8,
            colsample_bytree=0.8,
            gamma=0.1,
            random_state=42
        )
        self.model_total.fit(X_train, y_total)
        
        # Train spread model (regression)
        # Optimized for goal differential prediction
        self.model_spread = xgb.XGBRegressor(
            n_estimators=150,
            max_depth=6,
            learning_rate=0.05,
            min_child_weight=3,
            subsample=0.8,
            colsample_bytree=0.8,
            gamma=0.1,
            random_state=42
        )
        self.model_spread.fit(X_train, y_spread)
        
        self.is_trained = True
        
        # Save models
        self.save_models()
        
        print(f"✅ ML models trained on {len(X_train)} games")
        return True
    
    def predict(self, home_stats, away_stats, home_form, away_form):
        """
        Predict game outcome using trained ML models.
        
        Returns dict with predictions:
        - home_win_prob: Probability home team wins
        - expected_total: Expected total goals
        - expected_spread: Expected goal differential (home - away)
        """
        if not self.is_trained or not HAS_XGBOOST:
            return None
        
        features = self.extract_features(home_stats, away_stats, home_form, away_form)
        
        # Predict
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
        """Save trained models to disk."""
        if not self.is_trained:
            return
        
        with open(self.model_path / "win_model.pkl", "wb") as f:
            pickle.dump(self.model_win, f)
        with open(self.model_path / "total_model.pkl", "wb") as f:
            pickle.dump(self.model_total, f)
        with open(self.model_path / "spread_model.pkl", "wb") as f:
            pickle.dump(self.model_spread, f)
    
    def load_models(self):
        """Load trained models from disk."""
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


def blend_ml_and_similarity(ml_pred, similarity_pred, ml_weight=0.4):
    """
    Blend ML predictions with similarity-based predictions.
    
    Args:
        ml_pred: Predictions from ML model
        similarity_pred: Predictions from similarity model
        ml_weight: Weight for ML model (0-1), similarity gets (1-ml_weight)
    
    Returns:
        Blended predictions dict
    """
    if ml_pred is None:
        return similarity_pred
    
    return {
        "home_win_prob": ml_weight * ml_pred["home_win_prob"] + (1 - ml_weight) * similarity_pred["home_win_prob"],
        "away_win_prob": ml_weight * ml_pred["away_win_prob"] + (1 - ml_weight) * similarity_pred["away_win_prob"],
        "expected_total": ml_weight * ml_pred["expected_total"] + (1 - ml_weight) * similarity_pred["expected_total"],
    }
