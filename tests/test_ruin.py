import pandas as pd
from ohmystock.core.backtest.result import BacktestResult
from ohmystock.core.validation.ruin import ruin_probability


def _result(returns):
    idx = pd.date_range("2024-01-01", periods=len(returns), freq="B")
    r = pd.Series(returns, index=idx, dtype=float)
    eq = 100.0 * (1 + r).cumprod()
    trades = pd.DataFrame(columns=["symbol", "entry_date", "exit_date",
                                   "qty", "pnl", "cost"])
    return BacktestResult(equity_curve=eq, returns=r, trades=trades,
                          positions=pd.DataFrame(index=idx))


def test_all_positive_returns_no_ruin():
    res = _result([0.01] * 50)
    rep = ruin_probability(res)
    assert rep.name == "RuinProbability"
    assert rep.value == 0.0
    assert rep.passed is True
    assert rep.threshold == 0.05


# 손실 3, 이익 3로 구성 -> 부트스트랩 경로 일부만 -50%를 깨므로
# 파산확률이 0과 1 사이(약 0.5)로 나온다. (1.0 포화를 피해 시드 의존성을 검증 가능)
_FRACTIONAL = [-0.25, 0.05, -0.25, 0.05, -0.25, 0.05]


def test_fractional_ruin_probability_strictly_interior():
    res = _result(_FRACTIONAL)
    rep = ruin_probability(res, n_sims=4000, seed=1)
    # 전부 파산도 아니고 전부 생존도 아님
    assert 0.0 < rep.value < 1.0


def test_determinism_same_seed():
    # 포화되지 않는 데이터로 동일 시드 재현성을 의미있게 검증
    res = _result(_FRACTIONAL)
    a = ruin_probability(res, n_sims=4000, seed=7)
    b = ruin_probability(res, n_sims=4000, seed=7)
    assert a.value == b.value
    assert 0.0 < a.value < 1.0   # 비자명한 값에서의 일치


def test_seed_drives_rng():
    # 서로 다른 시드는 서로 다른 몬테카를로 추정치를 내야 한다(시드가 RNG를 구동).
    res = _result(_FRACTIONAL)
    values = {ruin_probability(res, n_sims=4000, seed=s).value for s in range(8)}
    assert len(values) > 1


def test_empty_returns():
    res = _result([])
    rep = ruin_probability(res)
    assert rep.value == 1.0
    assert rep.passed is False
    assert rep.threshold == 0.05
