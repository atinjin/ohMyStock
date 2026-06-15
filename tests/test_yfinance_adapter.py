from datetime import date
import pandas as pd
from ohmystock.core.data.yfinance_adapter import YFinanceAdapter
from ohmystock.core.data.cache import ParquetCache

def _fake_download(symbol, start, end):
    idx = pd.to_datetime(["2024-01-02", "2024-01-03"])
    return pd.DataFrame(
        {"open": [10.0, 11.0], "high": [12.0, 12.0], "low": [9.0, 10.0],
         "close": [11.0, 12.0], "volume": [100, 120]}, index=idx)

def test_fetches_and_normalizes(tmp_path):
    adapter = YFinanceAdapter(cache=ParquetCache(tmp_path), downloader=_fake_download)
    bars = adapter.get_daily_bars(["AAPL"], date(2024, 1, 1), date(2024, 1, 4))
    df = bars["AAPL"]
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df["close"].iloc[-1] == 12.0

def test_second_call_uses_cache(tmp_path):
    calls = {"n": 0}
    def counting_dl(symbol, start, end):
        calls["n"] += 1
        return _fake_download(symbol, start, end)
    adapter = YFinanceAdapter(cache=ParquetCache(tmp_path), downloader=counting_dl)
    adapter.get_daily_bars(["AAPL"], date(2024, 1, 1), date(2024, 1, 4))
    adapter.get_daily_bars(["AAPL"], date(2024, 1, 1), date(2024, 1, 4))
    assert calls["n"] == 1   # 두 번째는 캐시
