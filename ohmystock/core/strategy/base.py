from typing import Protocol
import pandas as pd


class Strategy(Protocol):
    def generate_signals(self, bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """일자×심볼 목표 비중 행렬. 0=미보유. 행 합계 <= 1. lookahead 금지."""
        ...
