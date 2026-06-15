from pathlib import Path
import pandas as pd


class ParquetCache:
    """심볼 단위 일봉 parquet 캐시. 키 = 심볼."""

    def __init__(self, cache_dir):
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, symbol: str) -> Path:
        return self.dir / f"{symbol}.parquet"

    def get(self, symbol: str) -> pd.DataFrame | None:
        p = self._path(symbol)
        if not p.exists():
            return None
        return pd.read_parquet(p)

    def put(self, symbol: str, df: pd.DataFrame) -> None:
        df.to_parquet(self._path(symbol))
