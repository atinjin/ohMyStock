import pandas as pd
from ohmystock.core.backtest.result import BacktestResult
from ohmystock.core.validation.monte_carlo import monte_carlo


def _result(returns):
    idx = pd.date_range("2024-01-01", periods=len(returns), freq="B")
    r = pd.Series(returns, index=idx, dtype=float)
    eq = 100.0 * (1 + r).cumprod()
    trades = pd.DataFrame(columns=["symbol", "entry_date", "exit_date",
                                   "qty", "pnl", "cost"])
    return BacktestResult(equity_curve=eq, returns=r, trades=trades,
                          positions=pd.DataFrame(index=idx))


def test_strongly_positive_returns_pass():
    res = _result([0.01] * 60)
    rep = monte_carlo(res)
    assert rep.name == "MonteCarlo"
    assert rep.threshold == 0.0
    assert rep.value > 0.0
    assert rep.passed is True


# 손익이 섞인 비자명(non-degenerate) 분포로 시드 의존성과 재현성을 의미있게 검증한다.
_MIXED = [0.05, -0.03, 0.04, -0.06, 0.02, 0.03, -0.04, 0.05] * 5


def test_determinism_same_seed():
    res = _result(_MIXED)
    a = monte_carlo(res, n_sims=3000, seed=4)
    b = monte_carlo(res, n_sims=3000, seed=4)
    assert a.value == b.value


def test_seed_drives_rng():
    res = _result(_MIXED)
    values = {monte_carlo(res, n_sims=3000, seed=s).value for s in range(6)}
    assert len(values) > 1


def test_empty_returns():
    res = _result([])
    rep = monte_carlo(res)
    assert rep.name == "MonteCarlo"
    assert rep.value == 0.0
    assert rep.passed is False
    assert rep.threshold == 0.0
