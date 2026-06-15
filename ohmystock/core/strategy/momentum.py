import pandas as pd


class Momentum:
    """과거 lookback일 수익률 상위 top_k 종목을 동일가중 보유."""

    def __init__(self, lookback: int = 90, top_k: int = 3):
        if lookback <= 0:
            raise ValueError("lookback은 0보다 커야 함")
        if top_k <= 0:
            raise ValueError("top_k는 0보다 커야 함")
        self.lookback = lookback
        self.top_k = top_k

    def generate_signals(self, bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
        closes = pd.DataFrame({sym: df["close"] for sym, df in bars.items()})
        # lookback일 추세 수익률
        mom = closes / closes.shift(self.lookback) - 1

        weights = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
        for date, row in mom.iterrows():
            eligible = row.dropna()
            if eligible.empty:
                continue
            n = min(self.top_k, len(eligible))
            selected = eligible.nlargest(n).index
            weights.loc[date, selected] = 1.0 / len(selected)

        # lookahead 방지: 오늘까지 본 신호는 내일부터 적용
        weights = weights.shift(1).fillna(0.0)
        return weights
