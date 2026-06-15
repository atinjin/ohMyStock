import numpy as np
from ohmystock.core.validation.base import ValidationReport
from ohmystock.core.backtest.result import BacktestResult


def ruin_probability(
    result: BacktestResult,
    ruin_threshold: float = 0.5,
    allowed: float = 0.05,
    n_sims: int = 10000,
    seed: int = 0,
) -> ValidationReport:
    """부트스트랩 몬테카를로 파산확률(test 16).

    일별 수익률을 복원추출로 재표본하여 누적 자산 경로를 만들고,
    경로의 최저 누적수익이 시작 대비 (1 - ruin_threshold) 이하로
    떨어지면 '파산'으로 간주한다.
    """
    r = result.returns.dropna().to_numpy()
    if len(r) == 0:
        return ValidationReport(
            name="RuinProbability",
            value=1.0,
            passed=False,
            threshold=allowed,
            message="수익률 데이터 없음",
        )

    n = len(r)
    rng = np.random.default_rng(seed)
    samples = rng.choice(r, size=(n_sims, n), replace=True)
    cum = np.cumprod(1.0 + samples, axis=1)
    ruin_level = 1.0 - ruin_threshold
    ruined = int(np.count_nonzero(cum.min(axis=1) <= ruin_level))

    prob = ruined / n_sims
    value = float(prob)
    passed = bool(prob <= allowed)
    message = (
        f"파산확률 {prob * 100:.2f}% "
        f"(임계 {-ruin_threshold * 100:.0f}% 손실, "
        f"허용 {allowed * 100:.2f}%)"
    )
    return ValidationReport(
        name="RuinProbability",
        value=value,
        passed=passed,
        threshold=allowed,
        message=message,
    )
