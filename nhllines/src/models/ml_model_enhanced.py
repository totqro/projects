"""
Enhanced ML Model with Player-Level Features
Extends the base ML model to include goalie stats, injuries, and situational data.
"""

from .ml_model import NHLMLModel
import numpy as np


class EnhancedNHLMLModel(NHLMLModel):
    """
    Enhanced ML model that includes player-level features.
    Inherits from base NHLMLModel and adds more features.
    """
    
    def extract_features(self, home_stats, away_stats, home_form, away_form, player_data=None):
        """
        Override base extract_features to include player data.
        For training, player_data will be None (uses defaults).
        For prediction, player_data can be provided.
        """
        # Start with base features (20 features)
        base_features = super().extract_features(home_stats, away_stats, home_form, away_form)[0]
        
        # Add player-level features
        if player_data:
            player_features = self._extract_player_features(player_data)
        else:
            # Use default values if no player data (for training on historical games)
            player_features = np.zeros(30)  # 30 additional features with neutral defaults
        
        all_features = np.concatenate([base_features, player_features])
        return all_features.reshape(1, -1)
    
    def extract_features_enhanced(self, home_stats, away_stats, home_form, away_form, 
                                  player_data=None):
        """
        Alias for extract_features for backward compatibility.
        """
        return self.extract_features(home_stats, away_stats, home_form, away_form, player_data)
    
    def _extract_player_features(self, player_data):
        """
        Extract features from player-level data.
        
        Returns 30 additional features:
        1-2: Home/Away goalie save % (season)
        3-4: Home/Away goalie GAA (season)
        5-6: Home/Away goalie recent save % (last 10 starts)
        7-8: Home/Away goalie recent GAA (last 10 starts)
        9-10: Home/Away goalie quality starts (last 10)
        11-12: Home/Away injury impact (0-10 scale)
        13-14: Home/Away back-to-back indicator
        15-16: Home/Away rest days
        17-18: Home/Away xGF% (expected goals for %)
        19-20: Home/Away Corsi%
        21-22: Home/Away PDO (luck indicator)
        23-24: Home/Away shooting %
        25-26: Home/Away home/road win % (last 10)
        27-28: Home/Away home/road GF/G (last 10)
        29-30: Home/Away home/road GA/G (last 10)
        """
        features = []
        
        # Goalie stats - season (home)
        home_goalie = player_data.get("home_goalie_stats", {})
        features.append(home_goalie.get("save_pct", 0.910))  # League average default
        features.append(home_goalie.get("gaa", 2.80))
        
        # Goalie stats - season (away)
        away_goalie = player_data.get("away_goalie_stats", {})
        features.append(away_goalie.get("save_pct", 0.910))
        features.append(away_goalie.get("gaa", 2.80))
        
        # Goalie recent form (last 10 starts) - home
        features.append(home_goalie.get("recent_save_pct", 0.910))
        features.append(home_goalie.get("recent_gaa", 2.80))
        features.append(home_goalie.get("recent_quality_starts", 5) / 10)  # Normalize to 0-1
        
        # Goalie recent form (last 10 starts) - away
        features.append(away_goalie.get("recent_save_pct", 0.910))
        features.append(away_goalie.get("recent_gaa", 2.80))
        features.append(away_goalie.get("recent_quality_starts", 5) / 10)
        
        # Injuries (0-10 scale, higher = more impact/worse)
        features.append(player_data.get("home_injury_impact", 0))
        features.append(player_data.get("away_injury_impact", 0))
        
        # Fatigue factors
        features.append(1 if player_data.get("home_back_to_back", False) else 0)
        features.append(1 if player_data.get("away_back_to_back", False) else 0)
        
        # Rest days (capped at 5)
        features.append(min(player_data.get("home_rest_days", 1), 5))
        features.append(min(player_data.get("away_rest_days", 1), 5))
        
        # Advanced stats (home)
        home_advanced = player_data.get("home_advanced_stats", {})
        features.append(home_advanced.get("xGF_pct", 50.0) / 100)  # Normalize to 0-1
        features.append(home_advanced.get("corsi_pct", 50.0) / 100)
        features.append(home_advanced.get("pdo", 100.0) / 100)
        features.append(home_advanced.get("shooting_pct", 10.0) / 100)
        
        # Advanced stats (away)
        away_advanced = player_data.get("away_advanced_stats", {})
        features.append(away_advanced.get("xGF_pct", 50.0) / 100)
        features.append(away_advanced.get("corsi_pct", 50.0) / 100)
        features.append(away_advanced.get("pdo", 100.0) / 100)
        features.append(away_advanced.get("shooting_pct", 10.0) / 100)
        
        # Home/Road splits (home team at home, last 10)
        home_splits = player_data.get("home_team_splits", {})
        features.append(home_splits.get("win_pct", 0.500))
        features.append(home_splits.get("gf_pg", 3.0))
        features.append(home_splits.get("ga_pg", 3.0))
        
        # Home/Road splits (away team on road, last 10)
        away_splits = player_data.get("away_team_splits", {})
        features.append(away_splits.get("win_pct", 0.500))
        features.append(away_splits.get("gf_pg", 3.0))
        features.append(away_splits.get("ga_pg", 3.0))
        
        return np.array(features)
    
    def predict_with_players(self, home_stats, away_stats, home_form, away_form, player_data):
        """
        Make prediction using enhanced features with player data.
        """
        if not self.is_trained:
            return None
        
        features = self.extract_features(home_stats, away_stats, home_form, away_form, player_data)
        
        # Predict
        home_win_prob = self.model_win.predict_proba(features)[0][1]
        expected_total = self.model_total.predict(features)[0]
        expected_spread = self.model_spread.predict(features)[0]
        
        return {
            "home_win_prob": float(home_win_prob),
            "away_win_prob": float(1 - home_win_prob),
            "expected_total": float(expected_total),
            "expected_spread": float(expected_spread),
            "used_player_data": True,
        }


# Feature importance analysis
def analyze_feature_importance(model):
    """
    Analyze which features are most important for predictions.
    Useful for understanding what drives the model.
    """
    if not model.is_trained:
        print("Model not trained yet")
        return
    
    feature_names = [
        # Base features (20)
        "Home Win %", "Home Points %", "Home GF/G", "Home GA/G", "Home Home Win %",
        "Away Win %", "Away Points %", "Away GF/G", "Away GA/G", "Away Road Win %",
        "Home Form Win %", "Home Form GF", "Home Form GA",
        "Away Form Win %", "Away Form GF", "Away Form GA",
        "Home Goal Diff", "Away Goal Diff", "Win % Diff", "Form Diff",
        # Player features (30)
        "Home Goalie Save %", "Home Goalie GAA",
        "Away Goalie Save %", "Away Goalie GAA",
        "Home Goalie Recent SV%", "Home Goalie Recent GAA", "Home Goalie QS",
        "Away Goalie Recent SV%", "Away Goalie Recent GAA", "Away Goalie QS",
        "Home Injuries", "Away Injuries",
        "Home Back-to-Back", "Away Back-to-Back",
        "Home Rest Days", "Away Rest Days",
        "Home xGF%", "Home Corsi%", "Home PDO", "Home Shooting%",
        "Away xGF%", "Away Corsi%", "Away PDO", "Away Shooting%",
        "Home Team Home Win%", "Home Team Home GF/G", "Home Team Home GA/G",
        "Away Team Road Win%", "Away Team Road GF/G", "Away Team Road GA/G",
    ]
    
    # Get feature importance from win probability model
    importance = model.model_win.feature_importances_
    
    # Sort by importance
    indices = np.argsort(importance)[::-1]
    
    print("\nTop 10 Most Important Features:")
    print("=" * 50)
    for i in range(min(10, len(indices))):
        idx = indices[i]
        if idx < len(feature_names):
            print(f"{i+1}. {feature_names[idx]}: {importance[idx]:.4f}")
    
    return dict(zip(feature_names, importance))
