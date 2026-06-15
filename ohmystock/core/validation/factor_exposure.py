"""팩터 노출도 검증(test 19) — OLS 회귀로 알파/베타 분해.

전략 일별 수익률을 절편(알파) + 각 팩터(시장 등)에 OLS 회귀하여,
연환산 알파가 양(+)인지로 통과 여부를 판정한다. 베타와 R^2은 참고용
지표로 메시지에 함께 기록한다.
"""
import numpy as np
import pandas as pd

from ohmystock.core.validation.base import ValidationReport
from ohmystock.core.backtest.result import BacktestResult


def factor_exposure(
    result: BacktestResult,
    factors: dict,
    trading_days: int = 252,
) -> ValidationReport:
    """팩터 노출도(알파/베타) 검증.

    `factors`는 이름->수익률 Series 매핑(예: {"market": benchmark_returns}).
    전략 수익률과 모든 팩터를 공통(교집합) 인덱스에 정렬한 뒤, 절편을
    포함한 설계행렬로 OLS 회귀하여 알파와 각 팩터 베타를 추정한다.
    연환산 알파가 0보다 크면 통과로 본다.
    """
    r = result.returns
    names = list(factors.keys())

    common = r.index
    for name in names:
        common = common.intersection(factors[name].index)

    if len(common) < (len(names) + 2):
        return ValidationReport(
            name="FactorExposure",
            value=0.0,
            passed=False,
            threshold=0.0,
            message="표본 부족",
        )

    y = r.loc[common].to_numpy()
    n = len(common)
    cols = [np.ones(n)]
    for name in names:
        cols.append(factors[name].loc[common].to_numpy())
    X = np.column_stack(cols)

    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    alpha = coef[0]
    betas = coef[1:]

    resid = y - X @ coef
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 0.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot

    ann_alpha = alpha * trading_days
    value = float(ann_alpha)
    # 부동소수점 잔차로 인한 미세 양수(예: 정확 복제 전략의 ~1e-16)를
    # 양(+)의 알파로 오판하지 않도록 작은 허용오차를 둔다.
    passed = bool(ann_alpha > 1e-12)

    beta_parts = ", ".join(
        f"beta[{name}]={betas[i]:.2f}" for i, name in enumerate(names)
    )
    message = f"연알파 {ann_alpha:.1%}, {beta_parts}, R2={r2:.2f}"

    return ValidationReport(
        name="FactorExposure",
        value=value,
        passed=passed,
        threshold=0.0,
        message=message,
    )
