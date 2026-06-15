import pandas as pd
from ohmystock.core.data.cache import ParquetCache

def _sample_df():
    idx = pd.to_datetime(["2024-01-02", "2024-01-03"])
    return pd.DataFrame(
        {"open": [10, 11], "high": [12, 12], "low": [9, 10],
         "close": [11, 12], "volume": [100, 120]}, index=idx)

def test_cache_roundtrip(tmp_path):
    cache = ParquetCache(tmp_path)
    df = _sample_df()
    assert cache.get("AAPL") is None        # miss
    cache.put("AAPL", df)
    loaded = cache.get("AAPL")              # hit
    pd.testing.assert_frame_equal(loaded, df)
