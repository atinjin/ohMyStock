import pandas as pd
from ohmystock.config import Config
from ohmystock.core.backtest.result import BacktestResult
from ohmystock.core.validation.walk_forward import walk_forward


def _result(returns):
    idx = pd.date_range("2024-01-01", periods=len(returns), freq="B")
    r = pd.Series(returns, index=idx, dtype=float)
    eq = 100.0 * (1 + r).cumprod()
    trades = pd.DataFrame(columns=["symbol", "entry_date", "exit_date",
                                   "qty", "pnl", "cost"])
    return BacktestResult(equity_curve=eq, returns=r, trades=trades,
                          positions=pd.DataFrame(index=idx))


def test_all_positive_returns_consistent():
    res = _result([0.01] * 30)
    rep = walk_forward(res, Config())
    assert rep.name == "WalkForward"
    assert rep.value == 1.0
    assert rep.passed is True
    assert rep.threshold == 0.6


def test_mostly_negative_returns_inconsistent():
    res = _result([-0.01] * 30)
    rep = walk_forward(res, Config())
    assert rep.value < 0.6
    assert rep.passed is False
    assert rep.threshold == 0.6


def test_insufficient_sample():
    res = _result([0.01, 0.01, 0.01])
    rep = walk_forward(res, Config(), n_folds=5)
    assert rep.value == 0.0
    assert rep.passed is False
    assert rep.message == "표본 부족"
