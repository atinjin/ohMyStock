import pandas as pd

from ohmystock.core.backtest.result import BacktestResult
from ohmystock.core.validation.base import ValidationReport
from ohmystock.core.validation._stats import total_return


def regime_test(
    result: BacktestResult,
    benchmark_returns,
    window: int = 20,
    floor: float = -0.20,
) -> ValidationReport:
    """국면(regime) 검증.

    벤치마크 수익률의 rolling 평균으로 상승/하락 국면을 구분한 뒤,
    전략이 하락 국면에서 입은 누적 손실이 바닥(floor) 이상인지 본다.
    하락장에서의 방어력(꼬리 위험)을 점검한다.
    """
    r = result.returns
    b = pd.Series(benchmark_returns)
    common = r.index.intersection(b.index)
    r = r.loc[common]
    b = b.loc[common]

    regime = b.rolling(window).mean()
    valid = regime.dropna().index
    if len(valid) == 0:
        return ValidationReport(
            name="Regime",
            value=0.0,
            passed=False,
            threshold=floor,
            message="표본 부족",
        )

    up_mask = regime.loc[valid] > 0
    down_mask = ~up_mask

    up_ret = total_return(r.loc[valid][up_mask.values])
    down_ret = total_return(r.loc[valid][down_mask.values])

    value = float(down_ret)
    passed = bool(down_ret >= floor)
    message = (
        f"상승국면 {up_ret:.1%} / 하락국면 {down_ret:.1%} "
        f"(floor {floor:.0%})"
    )
    return ValidationReport(
        name="Regime",
        value=value,
        passed=passed,
        threshold=floor,
        message=message,
    )
