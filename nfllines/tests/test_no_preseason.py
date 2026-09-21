"""Hard rule 3: no preseason anywhere."""
import pandas as pd
import pytest

from src.data import nflverse as nv


def test_game_types_constant():
    assert "PRE" not in nv.GAME_TYPES
    assert set(nv.GAME_TYPES) == {"REG", "WC", "DIV", "CON", "SB"}


def test_filter_drops_preseason():
    df = pd.DataFrame({"game_type": ["PRE", "REG", "WC", "DIV", "CON", "SB", "PRE"], "x": range(7)})
    out = nv.filter_game_types(df)
    assert set(out.game_type) == {"REG", "WC", "DIV", "CON", "SB"} and len(out) == 5


def test_filter_refuses_frame_without_game_type():
    with pytest.raises(KeyError):
        nv.filter_game_types(pd.DataFrame({"x": [1]}))


def test_loaded_tables_have_no_preseason():
    for loader in (nv.load_games, nv.load_injuries, nv.load_snap_counts):
        df = loader([2023])
        assert set(df.game_type) <= set(nv.GAME_TYPES), loader.__name__
    pbp = nv.load_pbp([2023])
    assert set(pbp._season_type) <= {"REG", "POST"}
