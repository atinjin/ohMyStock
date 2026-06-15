import pandas as pd

from ohmystock.config import Config
from ohmystock.core.backtest.result import BacktestResult
from ohmystock.core.validation.base import ValidationReport
from ohmystock.core.validation._stats import annualized_sharpe, total_return


def economic_edge(
    result: BacktestResult,
    benchmark_returns,
    config: Config,
) -> ValidationReport:
    """경제적 우위(Economic Edge) 검증.

    전략 수익률을 시장(벤치마크) 수익률과 공통 인덱스에서 비교한다.
    위험조정수익(연환산 Sharpe)이 시장보다 높고 총수익이 양수일 때만
    통과로 본다. 단순히 시장을 추종하거나 변동성만 키운 전략을 걸러낸다.
    """
    r = result.returns
    b = pd.Series(benchmark_returns)

    common = r.index.intersection(b.index)
    if len(common) < 2:
        return ValidationReport(
            name="EconomicEdge",
            value=0.0,
            passed=False,
            threshold=0.0,
            message="표본 부족",
        )

    r = r.loc[common]
    b = b.loc[common]

    strat_sharpe = annualized_sharpe(
        r, config.trading_days, config.risk_free_rate
    )
    bench_sharpe = annualized_sharpe(
        b, config.trading_days, config.risk_free_rate
    )
    strat_total = total_return(r)
    bench_total = total_return(b)

    edge = strat_sharpe - bench_sharpe
    value = float(edge)
    passed = bool(strat_sharpe > bench_sharpe and strat_total > 0)
    message = (
        f"전략 Sharpe {strat_sharpe:.2f} vs 시장 {bench_sharpe:.2f} "
        f"(초과 {edge:.2f}); 총수익 {strat_total:.1%} vs {bench_total:.1%}"
    )
    return ValidationReport(
        name="EconomicEdge",
        value=value,
        passed=passed,
        threshold=0.0,
        message=message,
    )
