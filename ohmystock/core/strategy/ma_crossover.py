import pandas as pd


class MACrossover:
    """단기 이동평균 > 장기 이동평균이면 매수(동일가중)."""

    def __init__(self, short: int = 20, long: int = 60):
        if short >= long:
            raise ValueError("short는 long보다 작아야 함")
        self.short = short
        self.long = long

    def generate_signals(self, bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
        closes = pd.DataFrame({sym: df["close"] for sym, df in bars.items()})
        short_ma = closes.rolling(self.short).mean()
        long_ma = closes.rolling(self.long).mean()
        holding = (short_ma > long_ma).fillna(False)
        # lookahead 방지: 오늘까지 본 신호는 내일부터 적용
        holding = holding.shift(1).fillna(False).astype(float)
        # 동일가중 정규화 (그 날 보유 종목 수로 나눔)
        counts = holding.sum(axis=1).replace(0, 1)
        weights = holding.div(counts, axis=0)
        return weights
