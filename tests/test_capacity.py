import math

import pandas as pd

from ohmystock.config import Config
from ohmystock.core.backtest.result import BacktestResult
from ohmystock.core.validation.capacity import capacity_analysis


def _bars(close, volume, n):
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {"close": [float(close)] * n, "volume": [float(volume)] * n}, index=idx
    )


def _result(weights_by_symbol, n):
    """weights_by_symbol: {symbol: held weight (constant over sample)}."""
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    positions = pd.DataFrame(
        {sym: [float(w)] * n for sym, w in weights_by_symbol.items()}, index=idx
    )
    r = pd.Series([0.0] * n, index=idx)
    eq = pd.Series([100.0] * n, index=idx)
    trades = pd.DataFrame(columns=["symbol", "entry_date", "exit_date", "qty", "pnl", "cost"])
    return BacktestResult(equity_curve=eq, returns=r, trades=trades, positions=positions)


def test_single_symbol_known_capacity():
    # volume=1000, close=10 -> adv_dollar=10000; weight 1.0; p=0.1
    bars = {"AAA": _bars(close=10, volume=1000, n=5)}
    res = _result({"AAA": 1.0}, n=5)
    report = capacity_analysis(res, bars, Config(), max_participation=0.1)
    assert abs(report.value - 1000.0) < 1e-6  # 0.1*10000/1.0


def test_capacity_scales_inversely_with_weight():
    bars = {"AAA": _bars(close=10, volume=1000, n=5)}
    res_full = _result({"AAA": 1.0}, n=5)
    res_half = _result({"AAA": 0.5}, n=5)
    cap_full = capacity_analysis(res_full, bars, Config(), max_participation=0.1).value
    cap_half = capacity_analysis(res_half, bars, Config(), max_participation=0.1).value
    assert abs(cap_half - 2.0 * cap_full) < 1e-6  # weight halved -> capacity doubles
    assert abs(cap_half - 2000.0) < 1e-6


def test_no_symbol_ever_held_is_infinite_and_passes():
    bars = {"AAA": _bars(close=10, volume=1000, n=5)}
    res = _result({"AAA": 0.0}, n=5)
    report = capacity_analysis(res, bars, Config(), max_participation=0.1)
    assert math.isinf(report.value)
    assert report.passed is True
    assert report.message == "보유 포지션 없음"


def test_pass_when_initial_capital_below_capacity():
    bars = {"AAA": _bars(close=10, volume=1000, n=5)}
    res = _result({"AAA": 1.0}, n=5)  # capacity == 1000.0
    report = capacity_analysis(res, bars, Config(initial_capital=500), max_participation=0.1)
    assert report.passed is True
    assert report.threshold == 500.0


def test_fail_when_initial_capital_above_capacity():
    bars = {"AAA": _bars(close=10, volume=1000, n=5)}
    res = _result({"AAA": 1.0}, n=5)  # capacity == 1000.0
    report = capacity_analysis(res, bars, Config(initial_capital=5000), max_participation=0.1)
    assert report.passed is False
    assert report.threshold == 5000.0


def test_capacity_is_min_over_held_symbols():
    bars = {
        "AAA": _bars(close=10, volume=1000, n=5),  # adv=10000 -> cap 1000 at w=1
        "BBB": _bars(close=10, volume=5000, n=5),  # adv=50000 -> cap 5000 at w=1
    }
    res = _result({"AAA": 1.0, "BBB": 1.0}, n=5)
    report = capacity_analysis(res, bars, Config(), max_participation=0.1)
    assert abs(report.value - 1000.0) < 1e-6  # min(1000, 5000)


def test_name_is_capacity():
    bars = {"AAA": _bars(close=10, volume=1000, n=5)}
    res = _result({"AAA": 1.0}, n=5)
    report = capacity_analysis(res, bars, Config(), max_participation=0.1)
    assert report.name == "Capacity"
