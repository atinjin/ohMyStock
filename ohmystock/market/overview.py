"""주요 지수·환율 시장 개요 계산(순수함수). provider 로 현재가 묶음을 받아 카드 데이터를 만든다."""

_ITEMS = [
    {"key": "nasdaq", "label": "나스닥", "symbol": "^IXIC", "vix": False},
    {"key": "sp500", "label": "S&P 500", "symbol": "^GSPC", "vix": False},
    {"key": "dow", "label": "다우존스", "symbol": "^DJI", "vix": False},
    {"key": "vix", "label": "VIX", "symbol": "^VIX", "vix": True},
    {"key": "kospi", "label": "코스피", "symbol": "^KS11", "vix": False},
    {"key": "usdkrw", "label": "달러 환율", "symbol": "USDKRW=X", "vix": False},
    {"key": "nasdaq_fut", "label": "나스닥 100 선물", "symbol": "NQ=F", "vix": False},
]


def _badge(cfg, value, hi, lo):
    if cfg.get("vix") and value >= 20:
        return "고변동성"
    if hi > 0 and value >= 0.98 * hi:
        return "52주 고점 근접"
    if lo > 0 and value <= 1.02 * lo:
        return "52주 저점 근접"
    return None


def build_overview(provider, *, kr_cal, us_cal, now, items=_ITEMS):
    out_items = []
    for cfg in items:
        try:
            q = provider(cfg["symbol"])
            last = float(q["last"])
            prev = float(q["prev_close"])
            change = last - prev
            change_pct = (change / prev * 100.0) if prev else 0.0
            spark = [round(float(x), 2) for x in (q.get("sparkline") or [])[-30:]]
            out_items.append({
                "key": cfg["key"],
                "label": cfg["label"],
                "value": round(last, 2),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
                "sparkline": spark,
                "badge": _badge(cfg, last, float(q["year_high"]), float(q["year_low"])),
            })
        except Exception:
            continue
    return {
        "markets": {
            "kr": {"open": bool(kr_cal.is_open(now))},
            "us": {"open": bool(us_cal.is_open(now))},
        },
        "items": out_items,
    }
