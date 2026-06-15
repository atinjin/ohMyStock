from dataclasses import dataclass, field
import pandas as pd

_PRICE_COLS = ["open", "high", "low", "close"]


@dataclass
class DataValidationReport:
    passed: bool
    issues: list[str] = field(default_factory=list)   # 치명적 문제
    warnings: list[str] = field(default_factory=list)  # 경고(통과는 가능)


def validate_bars(bars: dict[str, pd.DataFrame]) -> DataValidationReport:
    """① 데이터 검증: 결측·중복·0/음수·이상치 탐지, 생존편향 경고."""
    issues: list[str] = []
    warnings: list[str] = []

    for sym, df in bars.items():
        if df[_PRICE_COLS + ["volume"]].isna().any().any():
            issues.append(f"{sym}: 결측치 존재")
        if df.index.duplicated().any():
            issues.append(f"{sym}: 중복된 날짜 인덱스")
        if (df[_PRICE_COLS] <= 0).any().any():
            issues.append(f"{sym}: 0/음수 가격 존재")
        # 이상치: 일간 종가 변동 절대값 > 50%
        ret = df["close"].pct_change().abs()
        if (ret > 0.5).any():
            warnings.append(f"{sym}: 일간 50% 초과 변동(이상치 가능)")
        # 거래정지 의심: volume 0 구간
        if (df["volume"] == 0).any():
            warnings.append(f"{sym}: 거래량 0 구간(거래정지 가능)")

    warnings.append("생존편향 주의: 상장폐지 종목이 누락됐을 수 있음")
    return DataValidationReport(passed=len(issues) == 0, issues=issues, warnings=warnings)
