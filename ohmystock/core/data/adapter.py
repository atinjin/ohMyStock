from datetime import date
from typing import Protocol
import pandas as pd


class MarketDataAdapter(Protocol):
    def get_daily_bars(
        self, symbols: list[str], start: date, end: date
    ) -> dict[str, pd.DataFrame]:
        """심볼별 일봉. 컬럼 open/high/low/close/volume, index=거래일(DatetimeIndex)."""
        ...
