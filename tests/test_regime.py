import pandas as pd

from ohmystock.core.backtest.result import BacktestResult
from ohmystock.core.validation.regime import regime_test


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


def _benchmark(values):
    """전략과 동일한 인덱스 위의 벤치마크 수익률 시리즈."""
    idx = pd.date_range("2024-01-01", periods=len(values), freq="B")
    return pd.Series(values, index=idx)


# window=20. 앞 40일 상승 국면(+0.01), 뒤 40일 하락 국면(-0.01).
# rolling(20) 평균이 양/음으로 갈리는 구간이 모두 존재하도록 충분히 길게 잡는다.
def test_up_regime_positive_down_regime_cash_passes():
    bench_vals = [0.01] * 40 + [-0.01] * 40
    # 전략: 상승국면에는 +0.01, 하락국면에는 현금(0.0).
    strat_vals = [0.01] * 40 + [0.0] * 40
    report = regime_test(_result(strat_vals), _benchmark(bench_vals))
    assert report.name == "Regime"
    assert report.passed is True
    # 하락국면 손실이 바닥보다 낫다.
    assert report.value >= -0.20
    # 두 국면 모두 메시지에 언급.
    assert "상승국면" in report.message
    assert "하락국면" in report.message


def test_heavy_loss_in_down_regime_fails():
    bench_vals = [0.01] * 40 + [-0.01] * 40
    # 전략: 하락국면마다 -0.05씩 -> 누적 손실이 바닥(-0.20) 아래.
    strat_vals = [0.01] * 40 + [-0.05] * 40
    report = regime_test(_result(strat_vals), _benchmark(bench_vals))
    assert report.value < -0.20
    assert report.passed is False
    assert report.name == "Regime"


def test_too_few_samples_fails():
    # 길이 < window(20) -> rolling 평균이 모두 NaN -> 표본 부족.
    bench_vals = [0.01] * 10
    strat_vals = [0.01] * 10
    report = regime_test(_result(strat_vals), _benchmark(bench_vals))
    assert report.value == 0.0
    assert report.passed is False
    assert report.threshold == -0.20
    assert report.message == "표본 부족"
    assert report.name == "Regime"
