from datetime import date
import pandas as pd
from ohmystock.core.data.cache import ParquetCache

_COLS = ["open", "high", "low", "close", "volume"]


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """yfinance가 ('Close','AAPL') 형태의 MultiIndex 컬럼을 주므로 단일 레벨로 평탄화."""
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)
    return df[_COLS]


def _default_downloader(symbol: str, start: date, end: date) -> pd.DataFrame:
    import yfinance as yf
    df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
    return _normalize_columns(df)


class YFinanceAdapter:
    """미국 일봉 어댑터. downloader는 테스트를 위해 주입 가능."""

    def __init__(self, cache: ParquetCache, downloader=_default_downloader):
        self.cache = cache
        self.downloader = downloader

    def get_daily_bars(
        self, symbols: list[str], start: date, end: date
    ) -> dict[str, pd.DataFrame]:
        out: dict[str, pd.DataFrame] = {}
        for sym in symbols:
            cached = self.cache.get(sym)
            if cached is not None:
                out[sym] = cached
                continue
            df = self.downloader(sym, start, end)
            if df is None or df.empty:
                raise ValueError(f"데이터 없음: {sym} {start}~{end}")
            df = df[_COLS]
            self.cache.put(sym, df)
            out[sym] = df
        return out
