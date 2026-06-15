import pandas as pd

from ohmystock.core.backtest.result import BacktestResult
from ohmystock.core.validation.factor_exposure import factor_exposure


def _result(returns):
    idx = pd.date_range("2024-01-01", periods=len(returns), freq="B")
    r = pd.Series(returns, index=idx, dtype=float)
    eq = 100.0 * (1 + r).cumprod()
    trades = pd.DataFrame(columns=["symbol", "entry_date", "exit_date",
                                   "qty", "pnl", "cost"])
    return BacktestResult(equity_curve=eq, returns=r, trades=trades,
                          positions=pd.DataFrame(index=idx))


def _series(values, periods=None):
    n = periods if periods is not None else len(values)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.Series(values, index=idx, dtype=float)


def test_recovers_beta_and_positive_alpha():
    # 시장 팩터 m, 전략 r = 0.5*m + 0.001 (일정 일별 알파)
    base = [0.01, -0.005, 0.02, 0.008, -0.012, 0.015, -0.003, 0.006,
            0.011, -0.009, 0.004, 0.018, -0.007, 0.002, 0.013]
    m = _series(base)
    r = 0.5 * m + 0.001
    res = _result(r.to_numpy())
    rep = factor_exposure(res, {"market": m})

    assert rep.name == "FactorExposure"
    # 회복된 beta ~ 0.5
    assert abs(float(rep.message.split("beta[market]=")[1].split(",")[0]) - 0.5) < 1e-6
    # 연알파 ~ 0.252 > 0 -> 통과
    assert abs(rep.value - 0.252) < 1e-6
    assert rep.passed is True
    assert rep.threshold == 0.0


def test_no_alpha_fails():
    # 전략 r = 1.0*m 정확히 (알파 없음) -> 연알파 ~0 (<=0) -> 실패
    base = [0.01, -0.005, 0.02, 0.008, -0.012, 0.015, -0.003, 0.006,
            0.011, -0.009, 0.004, 0.018, -0.007, 0.002, 0.013]
    m = _series(base)
    r = 1.0 * m
    res = _result(r.to_numpy())
    rep = factor_exposure(res, {"market": m})

    assert abs(rep.value) < 1e-9
    assert rep.passed is False


def test_too_few_points():
    # 2개 점, 팩터 1개는 >=3 필요 -> "표본 부족", 실패
    m = _series([0.01, -0.005])
    r = _series([0.006, 0.001])
    res = _result(r.to_numpy())
    rep = factor_exposure(res, {"market": m})

    assert rep.passed is False
    assert "표본 부족" in rep.message
    assert rep.value == 0.0
