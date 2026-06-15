import numpy as np

from ohmystock.config import Config
from ohmystock.core.backtest.result import BacktestResult
from ohmystock.core.validation.base import ValidationReport
from ohmystock.core.validation._stats import total_return


def walk_forward(result: BacktestResult, config: Config, n_folds: int = 5,
                 min_positive: float = 0.6) -> ValidationReport:
    """워크포워드 일관성 검증. 표본을 n_folds로 나눠 양(+)수익 폴드 비율을 본다."""
    r = result.returns.dropna()
    n = len(r)
    if n < n_folds:
        return ValidationReport("WalkForward", 0.0, False, min_positive, "표본 부족")

    folds = np.array_split(r.to_numpy(), n_folds)
    positive = sum(1 for fold in folds if total_return(fold) > 0)
    ratio = positive / n_folds

    value = float(ratio)
    passed = bool(ratio >= min_positive)
    message = f"{positive}/{n_folds} 폴드 양(+)수익 (일관성 {ratio:.0%})"
    return ValidationReport(
        name="WalkForward",
        value=value,
        passed=passed,
        threshold=min_positive,
        message=message,
    )
