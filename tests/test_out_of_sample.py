import pandas as pd

from ohmystock.config import Config
from ohmystock.core.backtest.result import BacktestResult
from ohmystock.core.validation.out_of_sample import out_of_sample


def _result(returns):
    """수익률 리스트로 최소 BacktestResult를 구성."""
    idx = pd.date_range("2024-01-01", periods=len(returns), freq="B")
    r = pd.Series(returns, index=idx)
    eq = 100.0 * (1 + r).cumprod()
    trades = pd.DataFrame(
        columns=["symbol", "entry_date", "exit_date", "qty", "pnl", "cost"]
    )
    positions = pd.DataFrame(index=idx)
    return BacktestResult(equity_curve=eq, returns=r, trades=trades, positions=positions)


# n=40, split 0.7 -> IS = 앞 28개, OOS = 뒤 12개.
# 고정 패턴(노이즈 있으나 결정적)으로 std!=0 을 보장해 부동소수점 잡음에 의존하지 않는다.
def test_consistent_positive_passes():
    # 양쪽 반(半)이 동일 패턴(평균 +0.01, 실 변동성) -> IS≈OOS Sharpe -> 통과.
    returns = [0.011, 0.009] * 20  # 40개
    report = out_of_sample(_result(returns), Config())
    assert report.value > 0
    assert report.passed is True
    assert report.name == "OutOfSample"


def test_regime_break_oos_negative_fails():
    # IS 양(+) 패턴, OOS 음(-) 패턴 -> OOS Sharpe 유한 음수 -> 실패(취약한 0-나눗셈 없음).
    is_part = [0.011, 0.009] * 14   # 28개, 평균 +0.01
    oos_part = [-0.009, -0.011] * 6  # 12개, 평균 -0.01
    report = out_of_sample(_result(is_part + oos_part), Config())
    assert report.value < 0
    assert report.passed is False


def test_oos_positive_but_below_degrade_fails():
    # IS는 매우 높은 Sharpe, OOS는 양수지만 변동성 커서 Sharpe가 작음
    # -> oos>0 이지만 oos < degrade*IS 이므로 실패(저하 임계가 실제로 작동).
    is_part = [0.021, 0.019] * 14    # 28개, 평균 +0.02, 작은 변동성 -> 큰 Sharpe
    oos_part = [0.030, -0.022] * 6   # 12개, 평균 +0.004, 큰 변동성 -> 작은 양의 Sharpe
    report = out_of_sample(_result(is_part + oos_part), Config())
    assert report.value > 0          # OOS Sharpe 양수
    assert report.passed is False    # 그러나 IS 대비 크게 저하 -> 실패


def test_too_few_samples_fails():
    res = _result([0.01, 0.02, -0.01])  # n=3 < 4
    report = out_of_sample(res, Config())
    assert report.value == 0.0
    assert report.passed is False
    assert report.threshold == 0.5
    assert report.message == "표본 부족"
    assert report.name == "OutOfSample"
