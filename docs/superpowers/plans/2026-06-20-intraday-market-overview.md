# 시장 개요 인트라데이(준실시간) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 시장 개요가 장중엔 현재가(준실시간)로, 마감엔 종가로 값·등락을 갱신하게 한다.

**Architecture:** `build_overview`의 provider 계약을 일봉 DataFrame → "현재가 묶음 dict"로 바꿔 `value`=현재가·`change`=현재가−전일종가로 계산한다. 기본 provider는 yfinance `fast_info`(현재가·전일종가·52주)와 스파크라인(인트라데이 5분봉 우선, 없으면 일봉)을 모은다. 캐시 TTL을 60초로 줄이고, 프론트에 "지연 시세" 라벨을 단다. API 응답 형태는 불변.

**Tech Stack:** Python 3.11, FastAPI, yfinance, pytest, React/Vite/TypeScript, uv.

## Global Constraints

- 백엔드 테스트 `uv run pytest <path> -q`(VIRTUAL_ENV 3.9.11 경고 무해). 프론트 빌드 `cd web && npm run build`.
- provider 계약: `provider(symbol) -> {"last": float, "prev_close": float, "year_high": float, "year_low": float, "sparkline": list[float]}`.
- `build_overview` 계산: value=`last`, change=`last-prev_close`, change_pct=`change/prev_close*100`(prev 0이면 0), sparkline=`sparkline`의 최근 30개, badge=`_badge(cfg, last, year_high, year_low)`(기존 로직 불변).
- 기본 provider: yfinance `fast_info.last_price/previous_close/year_high/year_low` + 스파크라인(인트라데이 `period="1d",interval="5m"` close ≥2개면 사용, 아니면 일봉 최근 30).
- 캐시 TTL `_MARKET_TTL = 60`. API 응답 형태(`{markets, items:[{key,label,value,change,change_pct,sparkline,badge}]}`) 불변.
- yfinance는 약 15분 지연 → 준실시간. 각 태스크 끝 커밋(atinjin).

---

### Task 1: 백엔드 — provider 계약(현재가 묶음) + 기본 provider + TTL

**Files:**
- Modify: `ohmystock/market/overview.py` (`build_overview` 본문)
- Modify: `server/app.py` (`_default_market_provider` 재작성, `_MARKET_TTL` 60)
- Test: `tests/test_market_overview.py` (quote-dict 형태로 교체), `tests/test_server.py` (market 테스트 provider 교체)

**Interfaces:**
- Produces: `build_overview(provider, *, kr_cal, us_cal, now, items=_ITEMS)` — provider가 quote dict 반환. 응답 형태 불변.
- Consumes: `_badge`(기존), yfinance `fast_info`/`download`, `_default_downloader`(일봉 폴백).

- [ ] **Step 1: 테스트 교체(quote dict)**

`tests/test_market_overview.py` 전체를 아래로 **교체**:
```python
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
```

`tests/test_server.py` 의 `test_market_overview_endpoint_and_cache` 안 `provider` 를 아래로 **교체**(나머지 단언은 그대로):
```python
    def provider(symbol):
        calls["n"] += 1
        return {"last": 121.0, "prev_close": 110.0, "year_high": 130.0,
                "year_low": 90.0, "sparkline": [110.0, 121.0]}
```
(그 위의 `import pandas as pd` 줄은 더 이상 필요 없으면 지워도 되고 둬도 됨.)

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_market_overview.py tests/test_server.py::test_market_overview_endpoint_and_cache -q`
Expected: FAIL (`build_overview`가 아직 DataFrame `df["close"]`를 기대 → quote dict에서 KeyError로 항목 스킵 → 단언 불일치).

- [ ] **Step 3: `build_overview` 본문 교체**

`ohmystock/market/overview.py` 의 `build_overview` 를 아래로 교체(`_ITEMS`·`_badge`는 그대로):
```python
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
```
그리고 모듈 docstring 첫 줄을 갱신:
```python
"""주요 지수·환율 시장 개요 계산(순수함수). provider 로 현재가 묶음을 받아 카드 데이터를 만든다."""
```

- [ ] **Step 4: 통과 확인(build_overview)**

Run: `uv run pytest tests/test_market_overview.py -q`
Expected: PASS (7개).

- [ ] **Step 5: 기본 provider 재작성 + TTL**

`server/app.py` 의 `_MARKET_TTL = 300` 을 `60` 으로 바꾸고, `_default_market_provider` 를 아래로 교체:
```python
def _default_market_provider(symbol):
    """yfinance fast_info(현재가·전일종가·52주) + 스파크라인(인트라데이 우선, 없으면 일봉)."""
    import yfinance as yf

    t = yf.Ticker(symbol)
    fi = t.fast_info
    last = float(fi.last_price)
    prev = float(fi.previous_close)
    try:
        year_high = float(fi.year_high)
        year_low = float(fi.year_low)
    except Exception:
        year_high, year_low = last, last

    sparkline = []
    try:
        intraday = yf.download(symbol, period="1d", interval="5m",
                               progress=False, auto_adjust=True)
        if getattr(intraday.columns, "nlevels", 1) > 1:
            intraday.columns = intraday.columns.get_level_values(0)
        if not intraday.empty:
            sparkline = [float(c) for c in intraday["Close"].dropna().tolist()]
    except Exception:
        sparkline = []
    if len(sparkline) < 2:
        today = date.today()
        daily = _default_downloader(symbol, today - timedelta(days=45),
                                    today + timedelta(days=1))
        sparkline = [float(c) for c in daily["close"].dropna().tolist()][-30:]

    return {"last": last, "prev_close": prev, "year_high": year_high,
            "year_low": year_low, "sparkline": sparkline}
```
(`_default_downloader`·`date`·`timedelta` 는 이미 import됨.)

- [ ] **Step 6: 통과 확인 + 전체 스위트**

Run: `uv run pytest tests/test_server.py -q` → PASS(엔드포인트·캐시).
Run: `uv run pytest -q` → 전 프로젝트 그린.

- [ ] **Step 7: 커밋**

```bash
git add ohmystock/market/overview.py server/app.py tests/test_market_overview.py tests/test_server.py
git commit -m "feat(market): intraday live quote (fast_info last/prev), 60s cache"
```

---

### Task 2: 프론트 — "지연 시세" 라벨

**Files:**
- Modify: `web/src/components/MarketOverviewPanel.tsx`

**Interfaces:**
- Consumes: 기존 `/api/market/overview`(형태 불변). 표시만 추가.

- [ ] **Step 1: 라벨 추가**

`web/src/components/MarketOverviewPanel.tsx` 의 제목 `<h2 ...>시장 개요</h2>` 바로 다음 줄에 라벨 추가:
```tsx
        <h2 className="card-title" style={{ margin: 0 }}>시장 개요</h2>
        <span style={{ fontSize: 11, color: 'var(--text-dim)', border: '1px solid var(--border)', borderRadius: 4, padding: '1px 6px' }}>
          지연 시세 · 약 15분
        </span>
```

- [ ] **Step 2: 빌드 확인**

Run: `cd web && npm run build`
Expected: 빌드 성공.

- [ ] **Step 3: 커밋**

```bash
git add web/src/components/MarketOverviewPanel.tsx
git commit -m "feat(web): label market overview as delayed quote (~15min)"
```

---

## 완료 후

- 실 서버로 확인(장중이면 value가 전일 종가와 달라짐; 주말/마감이면 v1과 동일). 시장 개요 카드가 60초마다 갱신, "지연 시세" 라벨 표시.
- ROADMAP v2 "인트라데이 실시간 지수" 항목 완료 표기.
