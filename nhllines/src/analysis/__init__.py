"""Analysis modules"""
from .ev_calculator import (
    evaluate_all_bets,
    format_recommendations,
    kelly_criterion,
    calculate_ev,
)
from .bet_tracker import get_performance_stats
from .analysis_history import save_analysis, get_history_stats
from .goalie_tracker import get_todays_starters, get_goalie_matchup_analysis
from .injury_tracker import get_todays_injuries, get_injury_impact_for_game
from .advanced_stats import get_team_advanced_stats
from .team_splits import get_team_splits

__all__ = [
    'evaluate_all_bets',
    'format_recommendations',
    'kelly_criterion',
    'calculate_ev',
    'get_performance_stats',
    'save_analysis',
    'get_history_stats',
    'get_todays_starters',
    'get_goalie_matchup_analysis',
    'get_todays_injuries',
    'get_injury_impact_for_game',
    'get_team_advanced_stats',
    'get_team_splits',
]
