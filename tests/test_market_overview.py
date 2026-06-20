import pandas as pd

from ohmystock.market.overview import build_overview


class _Cal:
    def __init__(self, is_open):
        self._open = is_open

    def is_open(self, now):
        return self._open


def _df(closes):
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="B")
    return pd.DataFrame({"open": closes, "high": closes, "low": closes,
                         "close": closes, "volume": [1] * len(closes)}, index=idx)


def test_build_overview_value_change_sparkline_and_market_status():
    closes = [100.0] * 40 + [110.0, 121.0]   # 직전 110, 최근 121
    items = [{"key": "x", "label": "X", "symbol": "^X", "vix": False}]
    res = build_overview(lambda s: _df(closes), kr_cal=_Cal(False),
                         us_cal=_Cal(True), now=None, items=items)
    it = res["items"][0]
    assert it["key"] == "x" and it["label"] == "X"
    assert it["value"] == 121.0
    assert it["change"] == 11.0
    assert it["change_pct"] == 10.0
    assert it["sparkline"][-1] == 121.0
    assert len(it["sparkline"]) == 30
    assert res["markets"]["us"]["open"] is True
    assert res["markets"]["kr"]["open"] is False


def test_build_overview_badge_52w_high():
    closes = [50.0] * 50 + [98.0, 99.0]      # 52주 고가 99, 최근 99 ≥ 0.98*99
    items = [{"key": "x", "label": "X", "symbol": "^X", "vix": False}]
    res = build_overview(lambda s: _df(closes), kr_cal=_Cal(True),
                         us_cal=_Cal(True), now=None, items=items)
    assert res["items"][0]["badge"] == "52주 고점 근접"


def test_build_overview_badge_52w_low():
    closes = [100.0] * 50 + [62.0, 61.0]     # 52주 저가 61, 최근 61 ≤ 1.02*61
    items = [{"key": "x", "label": "X", "symbol": "^X", "vix": False}]
    res = build_overview(lambda s: _df(closes), kr_cal=_Cal(True),
                         us_cal=_Cal(True), now=None, items=items)
    assert res["items"][0]["badge"] == "52주 저점 근접"


def test_build_overview_badge_vix_high_volatility():
    closes = [12.0] * 50 + [19.0, 25.0]      # VIX 최근 25 ≥ 20
    items = [{"key": "vix", "label": "VIX", "symbol": "^VIX", "vix": True}]
    res = build_overview(lambda s: _df(closes), kr_cal=_Cal(True),
                         us_cal=_Cal(True), now=None, items=items)
    assert res["items"][0]["badge"] == "고변동성"


def test_build_overview_skips_failing_symbol():
    def provider(symbol):
        raise RuntimeError("no data")
    items = [{"key": "x", "label": "X", "symbol": "^X", "vix": False}]
    res = build_overview(provider, kr_cal=_Cal(True), us_cal=_Cal(True),
                         now=None, items=items)
    assert res["items"] == []


def test_default_items_has_seven():
    from ohmystock.market.overview import _ITEMS
    assert len(_ITEMS) == 7
    assert {i["symbol"] for i in _ITEMS} >= {"^IXIC", "^GSPC", "USDKRW=X"}
