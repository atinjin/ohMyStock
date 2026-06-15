import pandas as pd

from ohmystock.core.backtest.result import BacktestResult
from ohmystock.core.validation.correlation import correlation


def _result(returns):
    idx = pd.date_range("2024-01-01", periods=len(returns), freq="B")
    r = pd.Series(returns, index=idx)
    eq = 100.0 * (1.0 + r).cumprod()
    trades = pd.DataFrame(
        columns=["symbol", "entry_date", "exit_date", "qty", "pnl", "cost"]
    )
    positions = pd.DataFrame(index=idx)
    return BacktestResult(equity_curve=eq, returns=r, trades=trades, positions=positions)


def _benchmark(returns):
    idx = pd.date_range("2024-01-01", periods=len(returns), freq="B")
    return pd.Series(returns, index=idx)


def test_identical_to_benchmark_fails():
    rets = [0.01, -0.02, 0.03, -0.01, 0.02, -0.015]
    res = _result(rets)
    bench = _benchmark(rets)
    report = correlation(res, bench, max_abs=0.95)
    assert report.name == "Correlation"
    assert abs(report.value - 1.0) < 1e-9
    assert report.passed is False
    assert report.threshold == 0.95


def test_low_correlation_passes():
    bench = _benchmark([0.01, -0.01, 0.01, -0.01, 0.01, -0.01, 0.01, -0.01])
    res = _result([0.01, 0.01, -0.01, -0.01, 0.01, 0.01, -0.01, -0.01])
    report = correlation(res, bench, max_abs=0.95)
    assert abs(report.value) < 0.95
    assert report.passed is True
    assert report.name == "Correlation"


def test_zero_variance_strategy_cannot_compute():
    res = _result([0.0, 0.0, 0.0, 0.0, 0.0])
    bench = _benchmark([0.01, -0.02, 0.03, -0.01, 0.02])
    report = correlation(res, bench, max_abs=0.95)
    assert report.value == 0.0
    assert report.passed is False
    assert report.message == "상관 계산 불가"
    assert report.name == "Correlation"
