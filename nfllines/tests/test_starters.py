import pandas as pd

from src.starters import serving_starter

# PHI 2026 week 7 in miniature: the schedule lists the starter, who is on IR;
# the backup started week 6; a running back threw a trick pass in week 5.
QB_GAMES = pd.DataFrame([
    {"season": 2026, "week": 5, "team": "PHI", "qb_id": "starter", "dropbacks": 41},
    {"season": 2026, "week": 5, "team": "PHI", "qb_id": "rb", "dropbacks": 1},
    {"season": 2026, "week": 6, "team": "PHI", "qb_id": "backup", "dropbacks": 48},
    {"season": 2026, "week": 6, "team": "DAL", "qb_id": "dak", "dropbacks": 56},
])
QBS = {"starter", "backup", "third", "dak"}


def _serve(listed, rosters, injuries=None, team="PHI"):
    return serving_starter(listed, team, 2026, 7, QB_GAMES, rosters, injuries or {}, QBS)


def test_healthy_starter_stands():
    assert _serve("starter", {(2026, 7, "PHI"): {"starter": "ACT", "backup": "ACT"}}) == ("starter", None)
    assert _serve("starter", {}) == ("starter", None)          # no roster yet: nothing says he's out


def test_injured_reserve_uses_last_starter():
    qb, note = _serve("starter", {(2026, 7, "PHI"): {"starter": "RES", "backup": "ACT"}})
    assert qb == "backup" and "RES" in note


def test_report_out_and_doubtful():
    rosters = {(2026, 7, "PHI"): {"starter": "ACT", "backup": "ACT"}}
    for status in ("Out", "Doubtful"):
        assert _serve("starter", rosters, {(2026, 7, "PHI"): {"starter": (status, "DNP")}})[0] == "backup"
    assert _serve("starter", rosters, {(2026, 7, "PHI"): {"starter": ("Questionable", "DNP")}})[0] == "starter"


def test_replacement_must_be_available_qb_on_roster():
    # backup also out -> nobody else who started is a QB on the roster: keep listed, say so
    qb, note = _serve("starter", {(2026, 7, "PHI"): {"starter": "RES", "backup": "RES", "rb": "ACT"}})
    assert qb == "starter" and "no available replacement" in note
    # backup gone from the roster (released/traded) -> not chosen
    assert _serve("starter", {(2026, 7, "PHI"): {"starter": "RES", "rb": "ACT"}})[0] == "starter"


def test_other_teams_starters_ignored():
    qb, _ = _serve("x", {(2026, 7, "NYG"): {"x": "RES"}}, team="NYG")
    assert qb == "x"


def test_no_listed_starter_uses_last_starter():
    # nflverse leaves future weeks blank; a blank used to mean replacement level
    qb, note = _serve(float("nan"), {(2026, 7, "PHI"): {"starter": "ACT", "backup": "ACT"}})
    assert qb == "backup" and "no starter listed" in note


def test_correct_listed_starters():
    from src.data.team_games import correct_listed_starters
    games = pd.DataFrame([
        # listed QB never threw a pass -> the main passer replaces him
        {"game_id": "g1", "home_team": "WAS", "away_team": "PHI", "home_qb_id": "mariota", "away_qb_id": "hurts", "home_score": 20.0},
        # listed QB started and was hurt (threw passes) -> kept
        {"game_id": "g2", "home_team": "WAS", "away_team": "PHI", "home_qb_id": "daniels", "away_qb_id": "hurts", "home_score": 17.0},
        # upcoming game -> untouched
        {"game_id": "g3", "home_team": "WAS", "away_team": "PHI", "home_qb_id": "mariota", "away_qb_id": "hurts", "home_score": None},
    ])
    qbg = pd.DataFrame([
        {"game_id": "g1", "team": "WAS", "qb_id": "daniels", "dropbacks": 35},
        {"game_id": "g1", "team": "PHI", "qb_id": "hurts", "dropbacks": 30},
        {"game_id": "g2", "team": "WAS", "qb_id": "daniels", "dropbacks": 4},
        {"game_id": "g2", "team": "WAS", "qb_id": "mariota", "dropbacks": 30},
        {"game_id": "g2", "team": "PHI", "qb_id": "hurts", "dropbacks": 30},
    ])
    fixed, n = correct_listed_starters(games, qbg)
    assert n == 1
    assert list(fixed.home_qb_id) == ["daniels", "daniels", "mariota"]
    assert list(fixed.away_qb_id) == ["hurts"] * 3
