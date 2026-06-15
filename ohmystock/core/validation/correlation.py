"""시장구조 검증(G4): 전략-벤치마크 상관(독립성) 검증."""
import numpy as np
import pandas as pd

from ohmystock.core.backtest.result import BacktestResult
from ohmystock.core.validation.base import ValidationReport


def correlation(
    result: BacktestResult,
    benchmark_returns,
    max_abs: float = 0.95,
) -> ValidationReport:
    """전략 수익률과 시장 벤치마크의 상관계수가 충분히 낮은지(독립성) 검증한다.

    공통(교집합) 인덱스에서 정렬한 뒤 피어슨 상관을 계산한다. 표본이 2 미만이거나
    한쪽 변동성이 0(또는 NaN)이면 상관을 계산할 수 없어 실패로 처리한다.
    """
    r = result.returns
    b = pd.Series(benchmark_returns)
    common = r.index.intersection(b.index)
    r = r.loc[common]
    b = b.loc[common]

    if (
        len(common) < 2
        or r.std() == 0
        or b.std() == 0
        or np.isnan(r.std())
        or np.isnan(b.std())
    ):
        return ValidationReport(
            name="Correlation",
            value=0.0,
            passed=False,
            threshold=max_abs,
            message="상관 계산 불가",
        )

    corr = float(r.corr(b))
    if np.isnan(corr):
        return ValidationReport(
            name="Correlation",
            value=0.0,
            passed=False,
            threshold=max_abs,
            message="상관 계산 불가",
        )

    value = corr
    passed = bool(abs(corr) < max_abs)
    message = f"시장 상관 {corr:.2f} (|.|<{max_abs} 독립성)"
    return ValidationReport(
        name="Correlation",
        value=value,
        passed=passed,
        threshold=max_abs,
        message=message,
    )
