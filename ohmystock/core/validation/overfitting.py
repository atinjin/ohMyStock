"""과최적화 검증(test 2): 인-샘플 최적화 격차.

파라미터 그리드를 인-샘플(IS) 구간에서 최적화한 뒤, 같은 파라미터의
아웃-오브-샘플(OOS) 성능을 비교한다. IS에서만 좋고 OOS에서 무너지면
과최적화 신호이므로, (IS Sharpe - OOS Sharpe) 격차로 판정한다.
"""
from typing import Callable

from ohmystock.config import Config
from ohmystock.core.backtest.runner import backtest as run_bt
from ohmystock.core.validation._stats import annualized_sharpe
from ohmystock.core.validation.base import ValidationReport


def overfitting(
    strategy_factory: Callable,
    param_grid: list,
    bars,
    config: Config,
    split: float = 0.7,
    gap_limit: float = 1.0,
) -> ValidationReport:
    """인-샘플 최적화 격차로 과최적화를 검증한다.

    각 파라미터로 백테스트하여 수익률을 IS/OOS로 나누고 Sharpe를 잰다.
    IS Sharpe가 가장 높은(최적) 파라미터를 고른 뒤, 그 파라미터의
    OOS Sharpe와의 격차가 gap_limit 이하이고 OOS가 양수면 통과.
    """
    if not param_grid:
        return ValidationReport(
            name="Overfitting",
            value=0.0,
            passed=False,
            threshold=gap_limit,
            message="파라미터 그리드 비어있음",
        )

    records = []
    for params in param_grid:
        strat = strategy_factory(params)
        res = run_bt(strat, bars, config)
        r = res.returns.dropna()
        n = len(r)
        k = int(n * split)
        is_sh = annualized_sharpe(
            r.iloc[:k], config.trading_days, config.risk_free_rate)
        oos_sh = annualized_sharpe(
            r.iloc[k:], config.trading_days, config.risk_free_rate)
        records.append((params, is_sh, oos_sh))

    best_params, best_is, best_oos = max(records, key=lambda rec: rec[1])

    gap = best_is - best_oos
    value = float(gap)
    passed = bool(best_oos > 0 and gap <= gap_limit)
    message = (
        f"최적 IS Sharpe {best_is:.2f} -> OOS {best_oos:.2f}, "
        f"격차 {gap:.2f} (params={best_params})"
    )
    return ValidationReport(
        name="Overfitting",
        value=value,
        passed=passed,
        threshold=gap_limit,
        message=message,
    )
