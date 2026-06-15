from ohmystock.config import Config
from ohmystock.core.backtest.result import BacktestResult
from ohmystock.core.validation.base import ValidationReport
from ohmystock.core.validation._stats import annualized_sharpe


def out_of_sample(
    result: BacktestResult,
    config: Config,
    split: float = 0.7,
    degrade: float = 0.5,
) -> ValidationReport:
    """표본 외(out-of-sample) 검증.

    수익률을 앞쪽 split 비율의 인-샘플(IS)과 나머지 아웃-오브-샘플(OOS)로
    나눠 각각의 연환산 Sharpe를 비교한다. OOS가 양수이고, IS 대비
    degrade 비율 이상의 성과를 유지하면 통과로 본다(과최적화 경계).
    """
    r = result.returns.dropna()
    n = len(r)
    if n < 4:
        return ValidationReport(
            name="OutOfSample",
            value=0.0,
            passed=False,
            threshold=degrade,
            message="표본 부족",
        )

    k = int(n * split)
    is_returns = r.iloc[:k]
    oos_returns = r.iloc[k:]

    is_sharpe = annualized_sharpe(
        is_returns, config.trading_days, config.risk_free_rate
    )
    oos_sharpe = annualized_sharpe(
        oos_returns, config.trading_days, config.risk_free_rate
    )

    value = float(oos_sharpe)
    passed = bool(
        oos_sharpe > 0 and (is_sharpe <= 0 or oos_sharpe >= degrade * is_sharpe)
    )
    message = (
        f"IS Sharpe {is_sharpe:.2f} -> OOS Sharpe {oos_sharpe:.2f} "
        f"(저하허용 {degrade})"
    )
    return ValidationReport(
        name="OutOfSample",
        value=value,
        passed=passed,
        threshold=degrade,
        message=message,
    )
