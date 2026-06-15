import numpy as np
import pandas as pd
from ohmystock.core.strategy.ma_crossover import MACrossover

def _trend_df(closes):
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="B")
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes,
         "close": closes, "volume": [100] * len(closes)}, index=idx)

def test_signals_shape_and_weights():
    closes = list(np.linspace(10, 30, 40))
    bars = {"AAPL": _trend_df(closes)}
    strat = MACrossover(short=3, long=10)
    sig = strat.generate_signals(bars)
    assert list(sig.columns) == ["AAPL"]
    assert len(sig) == 40
    assert sig["AAPL"].iloc[-1] == 1.0

def test_no_lookahead_first_row_is_zero_or_nan_filled():
    closes = list(np.linspace(10, 30, 40))
    sig = MACrossover(short=3, long=10).generate_signals({"AAPL": _trend_df(closes)})
    assert sig["AAPL"].iloc[0] == 0.0

def test_equal_weight_across_symbols():
    closes = list(np.linspace(10, 30, 40))
    bars = {"AAPL": _trend_df(closes), "MSFT": _trend_df(closes)}
    sig = MACrossover(short=3, long=10).generate_signals(bars)
    assert sig.iloc[-1].sum() == 1.0
    assert sig["AAPL"].iloc[-1] == 0.5
