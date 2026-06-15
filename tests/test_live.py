import numpy as np
import pandas as pd
from datetime import date

from ohmystock.config import Config
from ohmystock.core.data.cache import ParquetCache
from ohmystock.core.data.yfinance_adapter import YFinanceAdapter
from ohmystock.core.strategy.momentum import Momentum
from ohmystock.live import live_preview


def _fake_dl(symbol, start, end):
    # 종목마다 다른 추세 -> 모멘텀이 일부를 선택
    seed = sum(ord(c) for c in symbol)
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.001, 0.01, 200)
    closes = 100.0 * np.cumprod(1.0 + steps)
    idx = pd.date_range("2023-01-01", periods=200, freq="B")
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes,
         "close": closes, "volume": [1_000_000] * 200}, index=idx)


def test_live_preview_generates_buy_orders_from_flat(tmp_path):
    adapter = YFinanceAdapter(cache=ParquetCache(tmp_path), downloader=_fake_dl)
    preview = live_preview(
        symbols=["AAPL", "MSFT", "GOOGL", "AMZN", "META"],
        start=date(2023, 1, 1), end=date(2023, 12, 31),
        adapter=adapter, strategy=Momentum(lookback=20, top_k=2), config=Config())

    assert preview["strategy"] == "Momentum"
    # 평지(flat) 시작 -> 목표 비중 도달을 위한 매수 주문 발생
    assert len(preview["orders"]) >= 1
    assert all(o["side"] == "buy" for o in preview["orders"])
    # 매수 총액은 초기 자금 이내
    total = sum(o["notional"] for o in preview["orders"])
    assert total <= Config().initial_capital + 1.0
    assert preview["risk"]["in_breach"] is False


def test_live_preview_serializable(tmp_path):
    import json
    adapter = YFinanceAdapter(cache=ParquetCache(tmp_path), downloader=_fake_dl)
    preview = live_preview(
        symbols=["AAPL", "MSFT"], start=date(2023, 1, 1), end=date(2023, 12, 31),
        adapter=adapter, strategy=Momentum(lookback=20, top_k=2), config=Config())
    json.dumps(preview)  # 직렬화 가능해야 함
