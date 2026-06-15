"""시장구조 검증(G4)이 공유하는 벤치마크 헬퍼."""
import pandas as pd


def equal_weight_benchmark(bars: dict) -> pd.Series:
    """유니버스 동일가중 매수보유(buy&hold)의 일별 수익률.

    각 종목 종가의 일간 변화율을 종목 평균낸 시장 프록시.
    """
    closes = pd.DataFrame({sym: df["close"] for sym, df in bars.items()})
    daily = closes.pct_change().fillna(0.0)
    return daily.mean(axis=1)
