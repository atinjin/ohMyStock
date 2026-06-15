import numpy as np
from ohmystock.core.validation.base import ValidationReport
from ohmystock.core.backtest.result import BacktestResult


def monte_carlo(
    result: BacktestResult,
    n_sims: int = 10000,
    seed: int = 0,
) -> ValidationReport:
    """부트스트랩 몬테카를로 총수익 분포(test 5).

    일별 수익률을 복원추출로 재표본하여 시뮬레이션 경로별 총수익을 만들고,
    그 분포의 5/50/95 백분위로 하방 위험을 평가한다. 5% 백분위가
    0보다 크면(최악권 경로도 흑자) 통과로 간주한다.
    """
    r = result.returns.dropna().to_numpy()
    n = len(r)
    if n == 0:
        return ValidationReport(
            name="MonteCarlo",
            value=0.0,
            passed=False,
            threshold=0.0,
            message="수익률 데이터 없음",
        )

    rng = np.random.default_rng(seed)
    samples = rng.choice(r, size=(n_sims, n), replace=True)
    finals = np.prod(1.0 + samples, axis=1) - 1.0
    p5, p50, p95 = np.percentile(finals, [5, 50, 95])

    value = float(p5)
    passed = bool(p5 > 0.0)
    message = f"총수익 분포 5%={p5:.1%} 50%={p50:.1%} 95%={p95:.1%}"
    return ValidationReport(
        name="MonteCarlo",
        value=value,
        passed=passed,
        threshold=0.0,
        message=message,
    )
