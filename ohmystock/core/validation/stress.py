"""역사적 위기 구간 스트레스 테스트(test 6).

전략의 자산 곡선을 알려진 위기 구간(COVID 2020, 2022 약세장, 2018 Q4)에
겹쳐 보고, 각 구간에서의 구간 수익률과 최대 낙폭(MDD)을 계산한다.
가장 심한 구간 MDD가 `severe` 임계 미만이면 통과로 본다.
"""
import pandas as pd

from ohmystock.core.validation.base import ValidationReport
from ohmystock.core.backtest.result import BacktestResult


DEFAULT_CRISES = [
    ("COVID 2020", "2020-02-19", "2020-03-23"),
    ("2022 약세장", "2022-01-01", "2022-10-12"),
    ("2018 Q4", "2018-10-01", "2018-12-24"),
]


def stress_test(
    result: BacktestResult,
    windows=None,
    severe: float = 0.5,
) -> ValidationReport:
    """역사적 위기 구간 스트레스 테스트.

    각 위기 구간에 대해 자산 곡선을 슬라이스하여 구간 수익률과 MDD를
    구하고, 가장 큰 MDD(worst)가 `severe` 미만이면 통과로 판정한다.
    겹치는 구간이 하나도 없으면 통과(데이터 없음)로 처리한다.
    """
    if windows is None:
        windows = DEFAULT_CRISES

    eq = result.equity_curve

    results = []  # (name, win_ret, win_mdd)
    for name, s, e in windows:
        mask = (eq.index >= pd.Timestamp(s)) & (eq.index <= pd.Timestamp(e))
        seg = eq[mask]
        if len(seg) < 2:
            continue
        win_ret = float(seg.iloc[-1] / seg.iloc[0] - 1.0)
        peak = seg.cummax()
        dd = (seg - peak) / peak
        win_mdd = float(-dd.min())
        results.append((name, win_ret, win_mdd))

    if not results:
        return ValidationReport(
            name="StressTest",
            value=0.0,
            passed=True,
            threshold=severe,
            message="위기 구간 데이터 없음",
        )

    worst = max(win_mdd for _, _, win_mdd in results)
    value = float(worst)
    passed = bool(worst < severe)

    parts = [
        f"{name}: ret {win_ret * 100:.1f}% mdd {win_mdd * 100:.1f}%"
        for name, win_ret, win_mdd in results
    ]
    message = (
        "; ".join(parts)
        + f" | 최악 MDD {worst * 100:.1f}% (임계 {severe * 100:.0f}%)"
    )

    return ValidationReport(
        name="StressTest",
        value=value,
        passed=passed,
        threshold=severe,
        message=message,
    )
