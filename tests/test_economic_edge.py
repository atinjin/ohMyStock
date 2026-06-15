import pandas as pd

from ohmystock.config import Config
from ohmystock.core.backtest.result import BacktestResult
from ohmystock.core.validation.economic_edge import economic_edge


def _result(returns):
    """수익률 리스트로 최소 BacktestResult를 구성."""
    idx = pd.date_range("2024-01-01", periods=len(returns), freq="B")
    r = pd.Series(returns, index=idx)
    eq = 100.0 * (1 + r).cumprod()
    trades = pd.DataFrame(
        columns=["symbol", "entry_date", "exit_date", "qty", "pnl", "cost"]
    )
    positions = pd.DataFrame(index=idx)
    return BacktestResult(
        equity_curve=eq, returns=r, trades=trades, positions=positions
    )


def _bench(returns):
    """전략과 동일 인덱스의 벤치마크 수익률 시리즈."""
    idx = pd.date_range("2024-01-01", periods=len(returns), freq="B")
    return pd.Series(returns, index=idx)


def test_higher_risk_adjusted_return_passes():
    # 전략: 꾸준한 저변동 양수 -> 높은 Sharpe, 총수익 양수.
    # 벤치마크: 출렁이는(choppy) 패턴 -> 낮은/0에 가까운 Sharpe.
    strat = [0.006, 0.005] * 20          # 40개, 꾸준한 양수, 저변동
    bench = [0.03, -0.029] * 20          # 40개, 큰 변동, 평균 거의 0
    report = economic_edge(_result(strat), _bench(bench), Config())
    assert report.value > 0
    assert report.passed is True
    assert report.name == "EconomicEdge"
    assert report.threshold == 0.0


def test_worse_than_benchmark_fails():
    # 전략 Sharpe < 벤치마크 Sharpe -> 실패.
    strat = [0.03, -0.029] * 20          # 큰 변동, 평균 거의 0 -> 낮은 Sharpe
    bench = [0.006, 0.005] * 20          # 꾸준한 양수, 저변동 -> 높은 Sharpe
    report = economic_edge(_result(strat), _bench(bench), Config())
    assert report.passed is False
    assert report.name == "EconomicEdge"


def test_too_few_samples_fails():
    strat = [0.01]                       # 공통 인덱스 길이 1 < 2
    bench = [0.01]
    report = economic_edge(_result(strat), _bench(bench), Config())
    assert report.value == 0.0
    assert report.passed is False
    assert report.threshold == 0.0
    assert report.message == "표본 부족"
    assert report.name == "EconomicEdge"
