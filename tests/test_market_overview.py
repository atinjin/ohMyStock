from ohmystock.market.overview import build_overview


class _Cal:
    def __init__(self, is_open):
        self._open = is_open

    def is_open(self, now):
        return self._open


def _q(last, prev, sparkline=None, year_high=None, year_low=None):
    spark = sparkline if sparkline is not None else [prev, last]
    return {
        "last": last,
        "prev_close": prev,
        "year_high": year_high if year_high is not None else max(spark + [last]),
        "year_low": year_low if year_low is not None else min(spark + [last]),
        "sparkline": spark,
    }


def test_build_overview_value_change_sparkline_and_market_status():
    spark = [100.0] * 28 + [110.0, 121.0]  # 30개
    items = [{"key": "x", "label": "X", "symbol": "^X", "vix": False}]
    res = build_overview(lambda s: _q(121.0, 110.0, sparkline=spark),
                         kr_cal=_Cal(False), us_cal=_Cal(True), now=None, items=items)
    it = res["items"][0]
    assert it["key"] == "x" and it["label"] == "X"
    assert it["value"] == 121.0
    assert it["change"] == 11.0
    assert it["change_pct"] == 10.0
    assert it["sparkline"][-1] == 121.0
    assert len(it["sparkline"]) == 30
    assert res["markets"]["us"]["open"] is True
    assert res["markets"]["kr"]["open"] is False


def test_build_overview_trims_sparkline_to_30():
    spark = [float(i) for i in range(50)]  # 50개 → 30개로 잘림
    items = [{"key": "x", "label": "X", "symbol": "^X", "vix": False}]
    res = build_overview(lambda s: _q(49.0, 48.0, sparkline=spark),
                         kr_cal=_Cal(True), us_cal=_Cal(True), now=None, items=items)
    assert len(res["items"][0]["sparkline"]) == 30
    assert res["items"][0]["sparkline"][-1] == 49.0


def test_build_overview_badge_52w_high():
    items = [{"key": "x", "label": "X", "symbol": "^X", "vix": False}]
    res = build_overview(lambda s: _q(99.0, 98.0, year_high=99.0, year_low=50.0),
                         kr_cal=_Cal(True), us_cal=_Cal(True), now=None, items=items)
    assert res["items"][0]["badge"] == "52주 고점 근접"


def test_build_overview_badge_52w_low():
    items = [{"key": "x", "label": "X", "symbol": "^X", "vix": False}]
    res = build_overview(lambda s: _q(61.0, 62.0, year_high=100.0, year_low=61.0),
                         kr_cal=_Cal(True), us_cal=_Cal(True), now=None, items=items)
    assert res["items"][0]["badge"] == "52주 저점 근접"


def test_build_overview_badge_vix_high_volatility():
    items = [{"key": "vix", "label": "VIX", "symbol": "^VIX", "vix": True}]
    res = build_overview(lambda s: _q(25.0, 19.0, year_high=30.0, year_low=10.0),
                         kr_cal=_Cal(True), us_cal=_Cal(True), now=None, items=items)
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
