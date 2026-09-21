"""Hard rule 2: the data split is what the README says it is."""
from src.data import nflverse as nv


def test_split_constants():
    assert nv.WARM_START_SEASON == 2014
    assert nv.TRAIN_SEASONS == tuple(range(2015, 2024))
    assert nv.TEST_SEASONS == (2024, 2025)
    assert not set(nv.TRAIN_SEASONS) & set(nv.TEST_SEASONS)
