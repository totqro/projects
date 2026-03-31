"""
Streamlined ML Model - Enhanced with Contextual Features
=========================================================
Uses base team stats + proven contextual features (B2B, rest days,
home/road splits, goalie quality) as ML features.

Factor impact analysis (575 games) showed:
- Away B2B: +11.9% home win boost (STRONG)
- Rest advantage: +10.6% when home rested (STRONG)
- Home/road splits: 74.8% vs 26.8% home win (VERY STRONG, signal: +0.185)
- Goalie quality: +0.54%/point (STRONG)
- Form momentum: signal +0.128 (STRONG)

All factors are fed as ML features so XGBoost learns optimal weights.
NO manual post-model probability adjustments.
"""

from .ml_model import NHLMLModel
import numpy as np

try:
    import xgboost as xgb
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False


class StreamlinedNHLMLModel(NHLMLModel):
    """
    Enhanced model that incorporates contextual features directly into ML.

    Features (52 total):
    - 20 base features (team stats + form)
    - 2 B2B flags (home, away)
    - 2 rest days (home, away)
    - 2 home/road split win% (home at home, away on road)
    - 2 goalie quality scores (home, away)
    - 2 goalie save % (home, away)
    - 2 recent goalie save % (home, away) — last 10 starts
    - 2 injury impact scores (home, away)
    - 4 advanced stats (home/away xGF%, home/away Corsi%)
    - 2 PDO (home, away)
    - 2 streak momentum (home, away)
    - 2 PP% (home, away)
    - 2 PK% (home, away)
    - 2 Fenwick% (home, away)
    - 2 shooting% (home, away)
    - 1 head-to-head win rate
    - 1 form trend (improving/declining)
    """

    FEATURE_NAMES = [
        # Base features (0-19)
        "Home Win %", "Home Points %", "Home GF/G", "Home GA/G", "Home Home Win %",
        "Away Win %", "Away Points %", "Away GF/G", "Away GA/G", "Away Road Win %",
        "Home Form Win %", "Home Form GF", "Home Form GA",
        "Away Form Win %", "Away Form GF", "Away Form GA",
        "Home Goal Diff", "Away Goal Diff", "Win % Diff", "Form Diff",
        # Contextual features (20-29)
        "Home B2B", "Away B2B",
        "Home Rest Days", "Away Rest Days",
        "Home Split Win%", "Away Road Split Win%",
        "Home Goalie Quality", "Away Goalie Quality",
        "Home Goalie SV%", "Away Goalie SV%",
        # Advanced features (30-41)
        "Home Recent Goalie SV%", "Away Recent Goalie SV%",
        "Home Injury Impact", "Away Injury Impact",
        "Home xGF%", "Away xGF%",
        "Home Corsi%", "Away Corsi%",
        "Home PDO", "Away PDO",
        "Home Streak", "Away Streak",
        # New features (42-51)
        "Home PP%", "Away PP%",
        "Home PK%", "Away PK%",
        "Home Fenwick%", "Away Fenwick%",
        "Home Shooting%", "Away Shooting%",
        "H2H Home Win Rate", "Home Form Trend",
    ]

    def extract_features(self, home_stats, away_stats, home_form, away_form, player_data=None):
        """
        Extract base features + contextual features.
        Total: 52 features.
        """
        # Get 20 base features from parent class
        base_features = super().extract_features(home_stats, away_stats, home_form, away_form)[0]

        # Add contextual features
        if player_data is None:
            player_data = {}

        home_goalie = player_data.get('home_goalie_stats', {})
        away_goalie = player_data.get('away_goalie_stats', {})
        home_adv = player_data.get('home_advanced_stats', {})
        away_adv = player_data.get('away_advanced_stats', {})
        home_st = player_data.get('home_special_teams', {})
        away_st = player_data.get('away_special_teams', {})

        context_features = [
            # B2B flags (features 20-21)
            1.0 if player_data.get('home_back_to_back', False) else 0.0,
            1.0 if player_data.get('away_back_to_back', False) else 0.0,

            # Rest days (features 22-23) - capped at 5 for normalization
            min(player_data.get('home_rest_days', 2), 5) / 5.0,
            min(player_data.get('away_rest_days', 2), 5) / 5.0,

            # Home/road split win % (features 24-25)
            player_data.get('home_team_splits', {}).get('win_pct', 0.5),
            player_data.get('away_team_splits', {}).get('win_pct', 0.5),

            # Goalie quality scores (features 26-27) - normalized to 0-1
            home_goalie.get('quality_score',
                player_data.get('home_goalie_quality', 50)) / 100.0,
            away_goalie.get('quality_score',
                player_data.get('away_goalie_quality', 50)) / 100.0,

            # Goalie save % (features 28-29)
            home_goalie.get('save_pct', 0.910),
            away_goalie.get('save_pct', 0.910),

            # Recent goalie form (features 30-31) — last 10 starts
            home_goalie.get('recent_save_pct', home_goalie.get('save_pct', 0.910)),
            away_goalie.get('recent_save_pct', away_goalie.get('save_pct', 0.910)),

            # Injury impact (features 32-33) — higher = more impact (worse)
            # Normalized: typical range 0-30, cap at 50
            min(player_data.get('home_injury_impact', 0), 50) / 50.0,
            min(player_data.get('away_injury_impact', 0), 50) / 50.0,

            # Advanced stats (features 34-37) — xGF% and Corsi% (0-100 scale -> 0-1)
            home_adv.get('xGF_pct', home_adv.get('xGF_per_60', 50)) / 100.0 if home_adv.get('xGF_pct') else
                (home_adv.get('xGF_per_60', 2.5) / 5.0 if home_adv.get('xGF_per_60') else 0.5),
            away_adv.get('xGF_pct', away_adv.get('xGF_per_60', 50)) / 100.0 if away_adv.get('xGF_pct') else
                (away_adv.get('xGF_per_60', 2.5) / 5.0 if away_adv.get('xGF_per_60') else 0.5),
            home_adv.get('corsi_pct', 50) / 100.0,
            away_adv.get('corsi_pct', 50) / 100.0,

            # PDO (features 38-39) — luck indicator, 100 = neutral
            (home_adv.get('pdo', 100) - 95) / 10.0,  # Normalize: 95-105 -> 0-1
            (away_adv.get('pdo', 100) - 95) / 10.0,

            # Streak momentum (features 40-41)
            player_data.get('home_streak', 0) / 10.0,
            player_data.get('away_streak', 0) / 10.0,

            # Special teams (features 42-45) — PP% and PK%
            # PP% typically 15-30%, normalize to 0-1
            home_st.get('pp_pct', 20.0) / 40.0,
            away_st.get('pp_pct', 20.0) / 40.0,
            # PK% typically 70-90%, normalize to 0-1
            home_st.get('pk_pct', 80.0) / 100.0,
            away_st.get('pk_pct', 80.0) / 100.0,

            # Fenwick% (features 46-47) — unblocked shot attempts
            home_adv.get('fenwick_pct', 50.0) / 100.0,
            away_adv.get('fenwick_pct', 50.0) / 100.0,

            # Shooting % (features 48-49) — scoring efficiency
            home_adv.get('shooting_pct', 10.0) / 20.0,  # Typically 5-15%
            away_adv.get('shooting_pct', 10.0) / 20.0,

            # Head-to-head (feature 50) — home team win rate vs this opponent
            player_data.get('h2h_home_win_rate', 0.5),

            # Form trend (feature 51) — is team improving or declining
            # Positive = improving, negative = declining, normalized to ~[-1, 1]
            player_data.get('home_form_trend', 0.0),
        ]

        all_features = np.concatenate([base_features, np.array(context_features)])
        return all_features.reshape(1, -1)

    def train(self, games, standings, team_forms, all_player_data=None):
        """
        Train ML models on historical game data with contextual features.

        Builds B2B/rest data from game schedule automatically.
        Goalie/splits data uses current values as approximation for training.
        """
        if not HAS_XGBOOST:
            print("Cannot train: XGBoost not installed")
            return False

        print("Training enhanced ML model with contextual features...")

        # Build B2B/rest info from game schedule
        from collections import defaultdict
        from datetime import datetime, timedelta

        team_schedule = defaultdict(list)
        for g in games:
            date = g.get("date", "")
            if date:
                team_schedule[g["home_team"]].append(date)
                team_schedule[g["away_team"]].append(date)

        for team in team_schedule:
            team_schedule[team] = sorted(set(team_schedule[team]))

        # Fetch goalie quality scores for all teams (current values as proxy)
        team_goalie_quality = {}
        team_goalie_sv_pct = {}
        try:
            from src.analysis.goalie_tracker import fetch_goalie_stats_nhl_api, get_goalie_quality_score
            for team in standings.keys():
                goalies = fetch_goalie_stats_nhl_api(team)
                if goalies:
                    goalies.sort(key=lambda g: g.get("games_played", 0), reverse=True)
                    primary = goalies[0]
                    team_goalie_quality[team] = get_goalie_quality_score(primary)
                    team_goalie_sv_pct[team] = primary.get("save_pct", 0.910)
        except Exception as e:
            print(f"  Warning: Could not load goalie data: {e}")

        # Calculate splits for all teams
        team_home_splits = {}
        team_road_splits = {}
        try:
            from src.analysis.team_splits import get_team_splits
            for team in standings.keys():
                splits = get_team_splits(team, games, n_recent=10)
                team_home_splits[team] = splits['home_recent']['win_pct']
                team_road_splits[team] = splits['road_recent']['win_pct']
        except Exception as e:
            print(f"  Warning: Could not load splits data: {e}")

        # Fetch advanced stats (single batch fetch, not per-team)
        team_advanced = {}
        try:
            from src.analysis.advanced_stats import get_team_advanced_stats, fetch_moneypuck_team_stats
            # Pre-fetch all teams at once (triggers cache)
            fetch_moneypuck_team_stats()
            for team in standings.keys():
                team_advanced[team] = get_team_advanced_stats(team)
        except Exception as e:
            print(f"  Warning: Could not load advanced stats: {e}")

        # Calculate injury impacts (use empty for training - historical injuries unavailable)
        # Injury impact will be 0 during training but active during prediction

        # Fetch special teams stats
        team_special_teams = {}
        try:
            from src.analysis.advanced_stats import get_special_teams_stats
            from src.data.nhl_data import NHL_TEAMS
            for team in standings.keys():
                team_special_teams[team] = get_special_teams_stats(team)
        except Exception as e:
            print(f"  Warning: Could not load special teams data: {e}")

        # Build streak data from game history
        team_streaks = self._calculate_streaks(games)

        # Build head-to-head records
        h2h_records = self._calculate_h2h(games)

        # Build form trends
        form_trends = self._calculate_form_trends(games)

        X_train = []
        y_win = []
        y_total = []
        y_spread = []
        train_dates = []  # Track dates for recency weighting

        for game in games:
            home = game["home_team"]
            away = game["away_team"]

            if home not in standings or away not in standings:
                continue

            home_stats = standings[home]
            away_stats = standings[away]
            home_form = team_forms.get(home, {"win_pct": 0.5, "avg_gf": 3.0, "avg_ga": 3.0})
            away_form = team_forms.get(away, {"win_pct": 0.5, "avg_gf": 3.0, "avg_ga": 3.0})

            # Build player_data for this game
            game_date = game.get("date", "")
            home_b2b = False
            away_b2b = False
            home_rest = 2
            away_rest = 2

            if game_date:
                try:
                    game_dt = datetime.strptime(game_date, "%Y-%m-%d")
                    prev_day = (game_dt - timedelta(days=1)).strftime("%Y-%m-%d")

                    home_dates = team_schedule.get(home, [])
                    if prev_day in home_dates:
                        home_b2b = True
                        home_rest = 1
                    else:
                        try:
                            idx = home_dates.index(game_date)
                            if idx > 0:
                                prev_dt = datetime.strptime(home_dates[idx - 1], "%Y-%m-%d")
                                home_rest = (game_dt - prev_dt).days
                        except (ValueError, IndexError):
                            pass

                    away_dates = team_schedule.get(away, [])
                    if prev_day in away_dates:
                        away_b2b = True
                        away_rest = 1
                    else:
                        try:
                            idx = away_dates.index(game_date)
                            if idx > 0:
                                prev_dt = datetime.strptime(away_dates[idx - 1], "%Y-%m-%d")
                                away_rest = (game_dt - prev_dt).days
                        except (ValueError, IndexError):
                            pass
                except ValueError:
                    pass

            # Get streak at time of this game
            home_streak = team_streaks.get((home, game_date), 0)
            away_streak = team_streaks.get((away, game_date), 0)

            player_data = {
                'home_back_to_back': home_b2b,
                'away_back_to_back': away_b2b,
                'home_rest_days': home_rest,
                'away_rest_days': away_rest,
                'home_team_splits': {'win_pct': team_home_splits.get(home, 0.5)},
                'away_team_splits': {'win_pct': team_road_splits.get(away, 0.5)},
                'home_goalie_stats': {
                    'quality_score': team_goalie_quality.get(home, 50),
                    'save_pct': team_goalie_sv_pct.get(home, 0.910),
                },
                'away_goalie_stats': {
                    'quality_score': team_goalie_quality.get(away, 50),
                    'save_pct': team_goalie_sv_pct.get(away, 0.910),
                },
                'home_injury_impact': 0,  # Historical injuries not available
                'away_injury_impact': 0,
                'home_advanced_stats': team_advanced.get(home, {}),
                'away_advanced_stats': team_advanced.get(away, {}),
                'home_streak': home_streak,
                'away_streak': away_streak,
                'home_special_teams': team_special_teams.get(home, {}),
                'away_special_teams': team_special_teams.get(away, {}),
                # Point-in-time H2H: use (home, away, date) key to avoid data leakage
                'h2h_home_win_rate': h2h_records.get((home, away, game_date), h2h_records.get((home, away), 0.5)),
                'home_form_trend': form_trends.get(home, 0.0),
            }

            features = self.extract_features(home_stats, away_stats, home_form, away_form, player_data)
            X_train.append(features[0])
            train_dates.append(game_date)

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

        # Recency weighting: recent games count more than old ones
        # Exponential decay with half-life of 30 days
        sample_weights = np.ones(len(X_train))
        today = datetime.now()
        for i, date_str in enumerate(train_dates):
            try:
                game_dt = datetime.strptime(date_str, "%Y-%m-%d")
                days_ago = (today - game_dt).days
                sample_weights[i] = 0.5 ** (days_ago / 30.0)
            except ValueError:
                sample_weights[i] = 0.5
        print(f"  Recency weighting: newest={sample_weights.max():.2f}, oldest={sample_weights.min():.2f}")

        # Train win probability model
        self.model_win = xgb.XGBClassifier(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.04,
            min_child_weight=5,
            subsample=0.8,
            colsample_bytree=0.8,
            gamma=0.15,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=42,
            eval_metric='logloss'
        )
        self.model_win.fit(X_train, y_win, sample_weight=sample_weights)

        # Train total goals model
        self.model_total = xgb.XGBRegressor(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.04,
            min_child_weight=5,
            subsample=0.8,
            colsample_bytree=0.8,
            gamma=0.15,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=42,
        )
        self.model_total.fit(X_train, y_total, sample_weight=sample_weights)

        # Train spread model
        self.model_spread = xgb.XGBRegressor(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.04,
            min_child_weight=5,
            subsample=0.8,
            colsample_bytree=0.8,
            gamma=0.15,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=42,
        )
        self.model_spread.fit(X_train, y_spread, sample_weight=sample_weights)

        self.is_trained = True
        self.save_models()

        print(f"  Trained on {len(X_train)} games with {X_train.shape[1]} features (20 base + {X_train.shape[1]-20} contextual+advanced)")

        # Print feature importance
        self._print_feature_importance()

        return True

    def predict_with_context(self, home_stats, away_stats, home_form, away_form, player_data):
        """
        Make prediction using enhanced ML model with contextual features.
        All adjustments are learned by the model — no manual overrides.
        """
        if not self.is_trained:
            return None

        features = self.extract_features(home_stats, away_stats, home_form, away_form, player_data)

        home_win_prob = self.model_win.predict_proba(features)[0][1]
        expected_total = self.model_total.predict(features)[0]
        expected_spread = self.model_spread.predict(features)[0]

        # Collect active context factors for display
        factors = []
        if player_data:
            if player_data.get('home_back_to_back'):
                factors.append("home_B2B")
            if player_data.get('away_back_to_back'):
                factors.append("away_B2B")
            if player_data.get('home_rest_days', 2) >= 3:
                factors.append("home_rested")
            if player_data.get('away_rest_days', 2) >= 3:
                factors.append("away_rested")

            home_split = player_data.get('home_team_splits', {}).get('win_pct', 0.5)
            away_split = player_data.get('away_team_splits', {}).get('win_pct', 0.5)
            if home_split > 0.7:
                factors.append("strong_home_split")
            if away_split < 0.3:
                factors.append("weak_away_road")

            home_gq = player_data.get('home_goalie_stats', {}).get('quality_score', 50)
            away_gq = player_data.get('away_goalie_stats', {}).get('quality_score', 50)
            if abs(home_gq - away_gq) > 10:
                better = "home" if home_gq > away_gq else "away"
                factors.append(f"{better}_goalie_edge")

            # Recent goalie form
            home_rsv = player_data.get('home_goalie_stats', {}).get('recent_save_pct', 0.910)
            away_rsv = player_data.get('away_goalie_stats', {}).get('recent_save_pct', 0.910)
            if home_rsv > 0.925:
                factors.append("home_goalie_hot")
            if away_rsv > 0.925:
                factors.append("away_goalie_hot")
            if home_rsv < 0.895:
                factors.append("home_goalie_cold")
            if away_rsv < 0.895:
                factors.append("away_goalie_cold")

            # Injury impact
            home_inj = player_data.get('home_injury_impact', 0)
            away_inj = player_data.get('away_injury_impact', 0)
            if home_inj > 10:
                factors.append("home_key_injuries")
            if away_inj > 10:
                factors.append("away_key_injuries")

            # Advanced stats edge
            home_adv = player_data.get('home_advanced_stats', {})
            away_adv = player_data.get('away_advanced_stats', {})
            home_corsi = home_adv.get('corsi_pct', 50)
            away_corsi = away_adv.get('corsi_pct', 50)
            if home_corsi > 53:
                factors.append("home_strong_possession")
            if away_corsi > 53:
                factors.append("away_strong_possession")

            # Streak
            home_streak = player_data.get('home_streak', 0)
            away_streak = player_data.get('away_streak', 0)
            if home_streak > 3:
                factors.append("home_hot_streak")
            elif home_streak < -3:
                factors.append("home_cold_streak")
            if away_streak > 3:
                factors.append("away_hot_streak")
            elif away_streak < -3:
                factors.append("away_cold_streak")

            # Special teams
            home_pp = player_data.get('home_special_teams', {}).get('pp_pct', 20)
            away_pp = player_data.get('away_special_teams', {}).get('pp_pct', 20)
            home_pk = player_data.get('home_special_teams', {}).get('pk_pct', 80)
            away_pk = player_data.get('away_special_teams', {}).get('pk_pct', 80)
            if home_pp > 25:
                factors.append("home_strong_pp")
            if away_pp > 25:
                factors.append("away_strong_pp")
            if home_pk > 85:
                factors.append("home_strong_pk")
            if away_pk > 85:
                factors.append("away_strong_pk")

            # H2H
            h2h_rate = player_data.get('h2h_home_win_rate', 0.5)
            if h2h_rate > 0.7:
                factors.append("home_h2h_dominant")
            elif h2h_rate < 0.3:
                factors.append("away_h2h_dominant")

            # Form trend
            trend = player_data.get('home_form_trend', 0)
            if trend > 0.4:
                factors.append("home_trending_up")
            elif trend < -0.4:
                factors.append("home_trending_down")

        return {
            "home_win_prob": float(home_win_prob),
            "away_win_prob": float(1 - home_win_prob),
            "expected_total": float(expected_total),
            "expected_spread": float(expected_spread),
            "adjustments_applied": {
                "note": "Contextual features integrated into ML model",
                "factors": factors,
                "win_prob_adjustment": 0,  # No manual adjustment
                "total_adjustment": 0,
            },
        }

    @staticmethod
    def _calculate_h2h(games):
        """
        Calculate point-in-time head-to-head records between all team pairs.

        Returns dict: {(home, away, date): home_win_rate}
        For each game date, uses only meetings BEFORE that date.
        Also returns current: {(home, away): home_win_rate} for prediction.
        """
        from collections import defaultdict

        completed = [g for g in games if g.get("game_state") in ("OFF", "FINAL") and g.get("date")]
        completed.sort(key=lambda g: g["date"])

        # Track results chronologically for each matchup pair
        matchup_results = defaultdict(list)  # (teamA, teamB) -> [(date, teamA_won)]
        h2h = {}  # (home, away, date) -> rate OR (home, away) -> rate

        for game in completed:
            home = game["home_team"]
            away = game["away_team"]
            home_won = game.get("home_win", False)
            date = game.get("date", "")

            # Point-in-time: calculate BEFORE adding this game's result
            prior_home = matchup_results.get((home, away), [])
            prior_away = matchup_results.get((away, home), [])
            # Combine: home's wins in any matchup with away
            all_prior = prior_home + [not r for r in prior_away]
            recent = all_prior[-10:]  # last 10 meetings
            if recent:
                h2h[(home, away, date)] = sum(1 for w in recent if w) / len(recent)
            else:
                h2h[(home, away, date)] = 0.5

            # Store result
            matchup_results[(home, away)].append(home_won)

        # Also store current (no date) for prediction time
        for (team_a, team_b), results in matchup_results.items():
            opp_results = matchup_results.get((team_b, team_a), [])
            all_results = results + [not r for r in opp_results]
            recent = all_results[-10:]
            if recent:
                h2h[(team_a, team_b)] = sum(1 for w in recent if w) / len(recent)
            else:
                h2h[(team_a, team_b)] = 0.5

        return h2h

    @staticmethod
    def _calculate_form_trends(games):
        """
        Calculate form trend for each team — is the team improving or declining?

        Compares last 5 games vs previous 5 games win rate.
        Returns dict: {team: trend} where trend is in [-1, 1].
        Positive = improving, negative = declining.
        """
        from collections import defaultdict

        completed = [g for g in games if g.get("game_state") in ("OFF", "FINAL") and g.get("date")]
        completed.sort(key=lambda g: g["date"])

        team_results = defaultdict(list)  # team -> [won, won, lost, ...]

        for game in completed:
            home = game["home_team"]
            away = game["away_team"]
            home_won = game.get("home_win", False)

            team_results[home].append(1 if home_won else 0)
            team_results[away].append(0 if home_won else 1)

        trends = {}
        for team, results in team_results.items():
            if len(results) < 10:
                trends[team] = 0.0
                continue

            recent_5 = results[-5:]
            prev_5 = results[-10:-5]

            recent_wr = sum(recent_5) / 5
            prev_wr = sum(prev_5) / 5

            # Trend: difference in win rates, clamped to [-1, 1]
            trends[team] = max(-1.0, min(1.0, (recent_wr - prev_wr) * 2))

        return trends

    @staticmethod
    def _calculate_streaks(games):
        """
        Calculate win/loss streaks for each team at each game date.
        Uses exponential weighting: recent results matter more.

        Returns dict: {(team, date): streak_value}
        Positive = winning streak, negative = losing streak.
        Weighted so a 3-game win streak = ~2.5 (recent games weighted higher).
        """
        from collections import defaultdict

        completed = [g for g in games if g.get("game_state") in ("OFF", "FINAL") and g.get("date")]
        completed.sort(key=lambda g: g["date"])

        team_results = defaultdict(list)  # team -> list of (date, won)
        streaks = {}

        for game in completed:
            home = game["home_team"]
            away = game["away_team"]
            home_won = game.get("home_win", False)
            date = game["date"]

            team_results[home].append((date, home_won))
            team_results[away].append((date, not home_won))

        # Calculate exponentially-weighted streak at each date
        for team, results in team_results.items():
            for i, (date, _) in enumerate(results):
                # Look at last 10 results before this game
                lookback = results[max(0, i - 10):i]
                if not lookback:
                    streaks[(team, date)] = 0
                    continue

                weighted_streak = 0
                for j, (_, won) in enumerate(lookback):
                    # More recent games get higher weight (exponential decay)
                    weight = 0.85 ** (len(lookback) - 1 - j)
                    weighted_streak += weight * (1 if won else -1)

                streaks[(team, date)] = weighted_streak

        return streaks

    def _print_feature_importance(self):
        """Print feature importance ranking."""
        if not self.is_trained or not hasattr(self.model_win, 'feature_importances_'):
            return

        importance = self.model_win.feature_importances_
        names = self.FEATURE_NAMES[:len(importance)]

        indices = np.argsort(importance)[::-1]

        print("\n  Feature Importance (Win Model):")
        print("  " + "-" * 55)
        for i in range(min(15, len(indices))):
            idx = indices[i]
            name = names[idx] if idx < len(names) else f"Feature {idx}"
            bar = "█" * int(importance[idx] * 100)
            print(f"  {i+1:2d}. {name:25s} {importance[idx]:.4f} {bar}")


def analyze_streamlined_importance(model):
    """Analyze feature importance for the enhanced model."""
    if not model.is_trained:
        print("Model not trained yet")
        return

    importance = model.model_win.feature_importances_
    names = StreamlinedNHLMLModel.FEATURE_NAMES[:len(importance)]

    indices = np.argsort(importance)[::-1]

    print("\nEnhanced Model - Feature Importance:")
    print("=" * 60)
    for i in range(len(indices)):
        idx = indices[i]
        name = names[idx] if idx < len(names) else f"Feature {idx}"
        bar = "█" * int(importance[idx] * 100)
        print(f"{i+1:2d}. {name:25s} {importance[idx]:.4f} {bar}")

    return dict(zip(names, importance))
