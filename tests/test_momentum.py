import numpy as np
import pandas as pd
import pytest
from ohmystock.core.strategy.momentum import Momentum

N = 130


def _trend_df(gain: float) -> pd.DataFrame:
    closes = np.linspace(10, 10 + gain, N)
    idx = pd.date_range("2024-01-01", periods=N, freq="B")
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes,
         "close": closes, "volume": [100] * N}, index=idx)


def _five_symbol_bars() -> dict[str, pd.DataFrame]:
    # A strongest uptrend, B second, ... E weakest.
    return {
        "A": _trend_df(50),
        "B": _trend_df(40),
        "C": _trend_df(30),
        "D": _trend_df(20),
        "E": _trend_df(10),
    }


def test_selects_strongest_momentum_symbols():
    bars = _five_symbol_bars()
    strat = Momentum(lookback=20, top_k=2)
    sig = strat.generate_signals(bars)

    assert list(sig.columns) == ["A", "B", "C", "D", "E"]
    assert len(sig) == N

    last = sig.iloc[-1]
    # The two strongest momentum symbols are A and B, each at weight 0.5.
    assert last["A"] == 0.5
    assert last["B"] == 0.5
    assert last["C"] == 0.0
    assert last["D"] == 0.0
    assert last["E"] == 0.0

    # Active rows (any non-zero weight) sum to 1.0.
    active = sig[sig.sum(axis=1) > 0]
    assert len(active) > 0
    assert np.allclose(active.sum(axis=1), 1.0)


def test_first_row_is_zero_lookahead():
    bars = _five_symbol_bars()
    sig = Momentum(lookback=20, top_k=2).generate_signals(bars)
    assert (sig.iloc[0] == 0.0).all()


def test_top_k_larger_than_universe_still_sums_to_one():
    bars = _five_symbol_bars()
    # top_k larger than the number of symbols.
    sig = Momentum(lookback=20, top_k=10).generate_signals(bars)
    active = sig[sig.sum(axis=1) > 0]
    assert len(active) > 0
    assert np.allclose(active.sum(axis=1), 1.0)


def test_constructor_rejects_invalid_params():
    with pytest.raises(ValueError):
        Momentum(lookback=0, top_k=2)
    with pytest.raises(ValueError):
        Momentum(lookback=-5, top_k=2)
    with pytest.raises(ValueError):
        Momentum(lookback=20, top_k=0)
    with pytest.raises(ValueError):
        Momentum(lookback=20, top_k=-1)
