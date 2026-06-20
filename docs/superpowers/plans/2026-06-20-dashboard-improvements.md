# 대시보드 개선 v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 대시보드에 시장 개요 패널(지수·환율 카드)을 추가하고, 실 계좌 패널 종목명·원화 환산·캘린더 색 구분을 개선한다.

**Architecture:** 신규 `ohmystock/market/overview.py`의 순수함수 `build_overview`(주입 provider로 yfinance 지수 데이터 → 값/등락/스파크라인/배지)를 `GET /api/market/overview`가 TTL 캐시와 함께 노출하고, 프론트 `MarketOverviewPanel`이 카드로 표시. 별도로 KIS/TOSS에 `get_holdings`(종목명 포함)·`TossBroker.exchange_rate`를 추가해 실 계좌 패널을 보강하고, 캘린더 색을 CSS로 강화한다.

**Tech Stack:** Python 3.11, FastAPI, yfinance, exchange_calendars, pytest, React/Vite/TypeScript, uv.

## Global Constraints

- 백엔드 테스트 `uv run pytest <path> -q`(VIRTUAL_ENV 3.9.11 경고 무해). 프론트 빌드 `cd web && npm run build`.
- 지수/환율 yfinance 심볼: 나스닥 `^IXIC`, S&P500 `^GSPC`, 다우 `^DJI`, VIX `^VIX`, 코스피 `^KS11`, 달러환율 `USDKRW=X`, 나스닥선물 `NQ=F`.
- 계산형 배지: VIX이고 value≥20 → `"고변동성"`; value ≥ 0.98×52주고가 → `"52주 고점 근접"`; value ≤ 1.02×52주저가 → `"52주 저점 근접"`; 그 외 `None`.
- 장 상태: `ExchangeMarketCalendar.is_open(tz-aware now)` — US `XNYS`, KR `XKRX`.
- 색: 상승=빨강 `#e5484d`, 하락=파랑 `#3b82f6`(한국식).
- v1은 일봉(EOD) 종가 기준. 뉴스/인트라데이는 v2(비범위).
- 각 태스크 끝 커밋(atinjin).

---

### Task 1: `build_overview` 순수함수

**Files:**
- Create: `ohmystock/market/__init__.py`, `ohmystock/market/overview.py`
- Test: `tests/test_market_overview.py`

**Interfaces:**
- Produces: `build_overview(provider, *, kr_cal, us_cal, now, items=_ITEMS) -> dict`. `provider(symbol: str) -> pandas.DataFrame`(close 컬럼 포함, 최근 1년 일봉). 반환 `{"markets":{"kr":{"open":bool},"us":{"open":bool}}, "items":[{key,label,value,change,change_pct,sparkline,badge}]}`. `_ITEMS`(7개 지수 config: `{key,label,symbol,vix}`).
- Consumes: 캘린더 객체는 `.is_open(now) -> bool` 메서드만 사용.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_market_overview.py`:
```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_market_overview.py -q`
Expected: FAIL (`ModuleNotFoundError: ohmystock.market.overview`).

- [ ] **Step 3: 구현**

`ohmystock/market/__init__.py`: 빈 파일(생성만).

`ohmystock/market/overview.py`:
```python
"""주요 지수·환율 시장 개요 계산(순수함수). provider 로 일봉을 받아 카드 데이터를 만든다."""

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
            df = provider(cfg["symbol"])
            closes = [float(c) for c in df["close"].dropna().tolist()]
            if len(closes) < 2:
                continue
            value, prev = closes[-1], closes[-2]
            change = value - prev
            change_pct = (change / prev * 100.0) if prev else 0.0
            out_items.append({
                "key": cfg["key"],
                "label": cfg["label"],
                "value": round(value, 2),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
                "sparkline": [round(x, 2) for x in closes[-30:]],
                "badge": _badge(cfg, value, max(closes), min(closes)),
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

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_market_overview.py -q`
Expected: PASS (6개).

- [ ] **Step 5: 커밋**

```bash
git add ohmystock/market/__init__.py ohmystock/market/overview.py tests/test_market_overview.py
git commit -m "feat(market): add build_overview (indices value/change/sparkline/badge)"
```

---

### Task 2: KR 캘린더 + `/api/market/overview` 엔드포인트

**Files:**
- Modify: `ohmystock/core/calendar/exchange.py` (`kr_market_calendar` 추가)
- Modify: `server/app.py` (import, `_default_market_provider`, `create_app`에 `market_provider` 파라미터 + app.state, 엔드포인트)
- Test: `tests/test_calendar.py`(KR 캘린더), `tests/test_server.py`(엔드포인트)

**Interfaces:**
- Consumes: Task 1의 `build_overview`, `ohmystock.core.data.yfinance_adapter._default_downloader`.
- Produces: `kr_market_calendar() -> ExchangeMarketCalendar`; `GET /api/market/overview`; `create_app(..., market_provider=None)`.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_calendar.py` 끝에 추가(파일 없으면 생성, import는 기존 스타일 따름):
```python
def test_kr_market_calendar_is_xkrx():
    from ohmystock.core.calendar.exchange import kr_market_calendar
    cal = kr_market_calendar()
    # 2024-06-06 현충일(한국 공휴일) 휴장
    from datetime import date
    assert cal.is_trading_day(date(2024, 6, 6)) is False
    # 2024-06-05(수) 거래일
    assert cal.is_trading_day(date(2024, 6, 5)) is True
```

`tests/test_server.py` 끝에 추가:
```python
def test_market_overview_endpoint_and_cache(tmp_path):
    import pandas as pd
    calls = {"n": 0}

    def provider(symbol):
        calls["n"] += 1
        closes = [100.0] * 40 + [110.0, 121.0]
        idx = pd.date_range("2025-01-01", periods=len(closes), freq="B")
        return pd.DataFrame({"open": closes, "high": closes, "low": closes,
                             "close": closes, "volume": [1] * len(closes)}, index=idx)

    adapter = YFinanceAdapter(cache=ParquetCache(tmp_path), downloader=_fake_dl)
    client = TestClient(create_app(adapter=adapter, market_provider=provider))
    resp = client.get("/api/market/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["markets"]["us"]["open"], bool)
    assert isinstance(body["markets"]["kr"]["open"], bool)
    assert len(body["items"]) == 7
    after_first = calls["n"]
    assert after_first == 7            # 심볼 7개 1회씩
    client.get("/api/market/overview")  # TTL 내 → 캐시
    assert calls["n"] == after_first    # provider 재호출 없음
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_calendar.py::test_kr_market_calendar_is_xkrx tests/test_server.py::test_market_overview_endpoint_and_cache -q`
Expected: FAIL (`kr_market_calendar` 없음 / 404 / `market_provider` 인자 없음).

- [ ] **Step 3: 구현**

`ohmystock/core/calendar/exchange.py` 끝의 `us_market_calendar` 아래에 추가:
```python
def kr_market_calendar() -> ExchangeMarketCalendar:
    """한국(KRX/XKRX) 캘린더."""
    return ExchangeMarketCalendar("XKRX")
```

`server/app.py` 상단 import에 추가:
```python
import time
from datetime import datetime, timezone, timedelta

from ohmystock.core.calendar.exchange import kr_market_calendar
from ohmystock.core.data.yfinance_adapter import _default_downloader
from ohmystock.market.overview import build_overview
```
(`us_market_calendar`·`date`·`os`·`HTTPException`는 이미 import됨.)

모듈 수준(`create_app` 위)에 추가:
```python
_MARKET_TTL = 300  # 초


def _default_market_provider(symbol):
    today = date.today()
    return _default_downloader(symbol, today - timedelta(days=365), today + timedelta(days=1))
```

`create_app` 시그니처와 app.state 초기화 수정:
```python
def create_app(adapter=None, paper_db="state/paper.db", broker_factory=None,
               market_provider=None) -> FastAPI:
    if adapter is None:
        adapter = YFinanceAdapter(cache=ParquetCache(".cache"))

    app = FastAPI(title="OhMyStock API")
    app.state.adapter = adapter
    app.state.paper_db = paper_db
    app.state.calendar = None
    app.state.broker_factory = broker_factory or _read_only_broker
    app.state.brokers = {}
    app.state.market_provider = market_provider or _default_market_provider
    app.state.market_cache = {}
    app.state.market_cal_kr = None
    app.state.market_cal_us = None
```
(기존 `app.state.broker_factory`/`brokers` 줄이 이미 있으면 중복 추가하지 말 것; market_* 4줄만 추가.)

`return app` 직전에 엔드포인트 추가:
```python
    @app.get("/api/market/overview")
    def market_overview():
        """주요 지수·환율 시장 개요(읽기 전용, TTL 캐시)."""
        cache = app.state.market_cache
        now_ts = time.time()
        if cache.get("data") is not None and now_ts - cache.get("ts", 0) < _MARKET_TTL:
            return cache["data"]
        if app.state.market_cal_kr is None:
            app.state.market_cal_kr = kr_market_calendar()
            app.state.market_cal_us = us_market_calendar()
        try:
            data = build_overview(
                app.state.market_provider,
                kr_cal=app.state.market_cal_kr,
                us_cal=app.state.market_cal_us,
                now=datetime.now(timezone.utc),
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        if not data["items"]:
            raise HTTPException(status_code=502, detail="시장 데이터를 가져오지 못했습니다")
        cache["data"] = data
        cache["ts"] = now_ts
        return data
```

- [ ] **Step 4: 통과 확인 + 전체 스위트**

Run: `uv run pytest tests/test_calendar.py tests/test_server.py -q`
Expected: PASS.
Run: `uv run pytest -q`
Expected: PASS (전 프로젝트 그린).

- [ ] **Step 5: 커밋**

```bash
git add ohmystock/core/calendar/exchange.py server/app.py tests/test_calendar.py tests/test_server.py
git commit -m "feat(server): GET /api/market/overview (indices, XKRX/XNYS status, TTL cache)"
```

---

### Task 3: 프론트 — MarketOverviewPanel

**Files:**
- Modify: `web/src/api.ts` (타입 + `getMarketOverview`)
- Create: `web/src/components/MarketOverviewPanel.tsx`
- Modify: `web/src/App.tsx` (import + 배치)

**Interfaces:**
- Consumes: Task 2의 `GET /api/market/overview`.
- Produces: `getMarketOverview()`, `<MarketOverviewPanel />`.

- [ ] **Step 1: api.ts 추가**

`web/src/api.ts` 끝에 추가:
```typescript
// 시장 개요

export interface MarketItem {
  key: string
  label: string
  value: number
  change: number
  change_pct: number
  sparkline: number[]
  badge: string | null
}

export interface MarketOverview {
  markets: { kr: { open: boolean }; us: { open: boolean } }
  items: MarketItem[]
}

export async function getMarketOverview(): Promise<MarketOverview> {
  const res = await fetch('/api/market/overview')
  if (!res.ok) {
    return parseError(res)
  }
  return (await res.json()) as MarketOverview
}
```

- [ ] **Step 2: 패널 컴포넌트 작성**

`web/src/components/MarketOverviewPanel.tsx`:
```tsx
import { useCallback, useEffect, useState } from 'react'
import { getMarketOverview, type MarketItem, type MarketOverview } from '../api'

const POLL_MS = 30000
const UP = '#e5484d' // 상승 빨강(한국식)
const DOWN = '#3b82f6' // 하락 파랑

function sparkPath(values: number[], w = 96, h = 28): string {
  if (values.length < 2) return ''
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  return values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * w
      const y = h - ((v - min) / span) * h
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
}

function fmtNum(n: number): string {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(n)
}

function MarketCard({ item }: { item: MarketItem }) {
  const up = item.change >= 0
  const color = up ? UP : DOWN
  const sign = up ? '+' : ''
  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 8, padding: '10px 12px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
        <span style={{ fontWeight: 600 }}>{item.label}</span>
        {item.badge && (
          <span style={{ fontSize: 11, color: 'var(--text-dim)', border: '1px solid var(--border)', borderRadius: 4, padding: '0 5px' }}>
            {item.badge}
          </span>
        )}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <svg width={96} height={28} style={{ flexShrink: 0 }}>
          <path d={sparkPath(item.sparkline)} fill="none" stroke={color} strokeWidth={1.5} />
        </svg>
        <div>
          <div style={{ fontSize: 18, fontVariantNumeric: 'tabular-nums' }}>{fmtNum(item.value)}</div>
          <div style={{ fontSize: 13, color, fontVariantNumeric: 'tabular-nums' }}>
            {sign}
            {fmtNum(item.change)} ({sign}
            {item.change_pct.toFixed(2)}%)
          </div>
        </div>
      </div>
    </div>
  )
}

function statusDot(open: boolean) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
      <span style={{ width: 8, height: 8, borderRadius: '50%', background: open ? '#22c55e' : 'var(--text-dim)' }} />
      {open ? '열림' : '닫힘'}
    </span>
  )
}

export default function MarketOverviewPanel() {
  const [data, setData] = useState<MarketOverview | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setData(await getMarketOverview())
      setError(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '시장 개요 조회 실패')
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, POLL_MS)
    return () => clearInterval(id)
  }, [load])

  return (
    <div className="card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <h2 className="card-title" style={{ margin: 0 }}>시장 개요</h2>
        {data && (
          <div style={{ display: 'flex', gap: 16, fontSize: 13, color: 'var(--text-dim)' }}>
            <span>국내 장 {statusDot(data.markets.kr.open)}</span>
            <span>해외 장 {statusDot(data.markets.us.open)}</span>
          </div>
        )}
        <button onClick={load} style={{ marginLeft: 'auto' }}>새로고침</button>
      </div>

      {error ? (
        <p style={{ color: 'var(--fail)' }}>{error}</p>
      ) : data === null ? (
        <p style={{ color: 'var(--text-dim)' }}>불러오는 중…</p>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12, marginTop: 12 }}>
          {data.items.map((it) => (
            <MarketCard key={it.key} item={it} />
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: App.tsx 배치**

`web/src/App.tsx` import 블록에 추가:
```tsx
import MarketOverviewPanel from './components/MarketOverviewPanel'
```
`<main className="app-main">` 의 맨 위(에러 alert 아래, 첫 placeholder/loading 위)에 추가:
```tsx
        <main className="app-main">
          <MarketOverviewPanel />
          {error && <div className="alert alert-error">{error}</div>}
```

- [ ] **Step 4: 빌드 확인**

Run: `cd web && npm run build`
Expected: 빌드 성공(타입 에러 없음).

- [ ] **Step 5: 커밋**

```bash
git add web/src/api.ts web/src/components/MarketOverviewPanel.tsx web/src/App.tsx
git commit -m "feat(web): add market overview panel (indices cards, sparkline, market status)"
```

---

### Task 4: 보유 종목명 표시 (get_holdings)

**Files:**
- Modify: `ohmystock/core/broker/kis.py` (`get_holdings` 추가, `get_positions` 파생)
- Modify: `ohmystock/core/broker/toss.py` (`get_holdings` 추가, `get_positions` 파생)
- Modify: `server/app.py` (`/api/broker/account`가 `get_holdings` 사용)
- Modify: `web/src/api.ts`, `web/src/components/BrokerAccountPanel.tsx`
- Test: `tests/test_kis_broker.py`, `tests/test_toss_broker.py`, `tests/test_server.py`

**Interfaces:**
- Produces: `KISBroker.get_holdings() -> list[dict]`, `TossBroker.get_holdings() -> list[dict]` (각 `{"symbol","name","value"}`); `/api/broker/account` 의 `positions`가 `[{symbol,name,value}]`.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_kis_broker.py` 끝에 추가:
```python
def test_get_holdings_includes_name():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "output1": [
                {"pdno": "005930", "prdt_name": "삼성전자", "evlu_amt": "500000"},
                {"pdno": "000660", "prdt_name": "SK하이닉스", "evlu_amt": "0"},
            ],
            "output2": [{"tot_evlu_amt": "1", "dnca_tot_amt": "1"}]})

    broker = _make_broker(handler, access_token="tok",
                          token_expires_at=datetime(2030, 1, 1))
    assert broker.get_holdings() == [
        {"symbol": "005930", "name": "삼성전자", "value": 500000.0}]
    assert broker.get_positions() == {"005930": 500000.0}
```

`tests/test_toss_broker.py` 끝에 추가:
```python
def test_get_holdings_includes_name():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/holdings":
            return httpx.Response(200, json={"result": {
                "marketValue": {"amount": {"usd": 1795.0}},
                "items": [{"symbol": "AAPL", "name": "애플", "quantity": 10,
                           "currency": "USD", "marketValue": {"amount": 1795.0}}]}})
        raise AssertionError(f"예상치 못한 경로 {request.url.path}")

    broker = _make_broker(handler, access_token="tok",
                          token_expires_at=datetime(2030, 1, 1))
    assert broker.get_holdings() == [
        {"symbol": "AAPL", "name": "애플", "value": 1795.0}]
```

`tests/test_server.py` 의 기존 `_FakeBroker`를 아래로 **교체**하고 기존 `test_broker_account_ok` 의 positions 단언을 갱신:
```python
class _FakeBroker:
    paper = True

    def get_account(self):
        from ohmystock.core.broker.base import Account
        return Account(equity=10000000.0, cash=9000000.0)

    def get_holdings(self):
        return [{"symbol": "005930", "name": "삼성전자", "value": 354000.0}]
```
그리고 `test_broker_account_ok` 의 positions 단언을 교체:
```python
    assert body["positions"] == [
        {"symbol": "005930", "name": "삼성전자", "value": 354000.0}]
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_kis_broker.py tests/test_toss_broker.py tests/test_server.py -q`
Expected: FAIL (`get_holdings` 없음 / positions 형식 불일치).

- [ ] **Step 3: 구현**

`ohmystock/core/broker/kis.py` 의 `get_positions` 를 아래로 교체(바로 위에 `get_holdings` 추가):
```python
    def get_holdings(self) -> list[dict]:
        """보유 종목 [{symbol, name, value}]. 평가금액 0 이하 제외."""
        data = self._inquire_balance()
        out = []
        for row in data["output1"]:
            value = float(row.get("evlu_amt", 0))
            if value <= 0:
                continue
            out.append({"symbol": row["pdno"],
                        "name": row.get("prdt_name", ""), "value": value})
        return out

    def get_positions(self) -> dict[str, float]:
        return {h["symbol"]: h["value"] for h in self.get_holdings()}
```

`ohmystock/core/broker/toss.py` 의 `get_positions` 를 아래로 교체(바로 위에 `get_holdings` 추가):
```python
    def get_holdings(self) -> list[dict]:
        """보유 종목 [{symbol, name, value}]. quantity>0 + 통화 슬리브 일치만."""
        headers = self._acct_headers()
        holdings = self._result(self.client.get("/api/v1/holdings", headers=headers))
        cur = self.currency.upper()
        out = []
        for item in holdings.get("items", []):
            if float(item.get("quantity") or 0) <= 0:
                continue
            if str(item.get("currency", "")).upper() != cur:
                continue
            mv = item.get("marketValue", {})
            out.append({"symbol": item["symbol"], "name": item.get("name", ""),
                        "value": float(mv.get("amount") or 0.0)})
        return out

    def get_positions(self) -> dict[str, float]:
        return {h["symbol"]: h["value"] for h in self.get_holdings()}
```

`server/app.py` 의 `broker_account` 엔드포인트에서 positions 구성을 교체:
```python
            acct = b.get_account()
            positions = b.get_holdings()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        mode = "paper" if getattr(b, "paper", False) else "live"
        return {
            "broker": broker,
            "mode": mode,
            "equity": acct.equity,
            "cash": acct.cash,
            "positions": positions,
        }
```

`web/src/api.ts` 의 `BrokerAccount` 인터페이스 positions 타입 교체:
```typescript
export interface BrokerAccount {
  broker: string
  mode: string
  equity: number
  cash: number
  positions: { symbol: string; name: string; value: number }[]
}
```

`web/src/components/BrokerAccountPanel.tsx` 의 보유 테이블 헤더/행에 종목명 컬럼 추가:
```tsx
            <table className="orders-table">
              <thead>
                <tr>
                  <th>종목</th>
                  <th>종목명</th>
                  <th>평가금액</th>
                </tr>
              </thead>
              <tbody>
                {data.positions.map((p) => (
                  <tr key={p.symbol}>
                    <td>{p.symbol}</td>
                    <td>{p.name}</td>
                    <td style={{ fontVariantNumeric: 'tabular-nums' }}>{fmt.format(p.value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
```

- [ ] **Step 4: 통과 확인 + 빌드 + 전체 스위트**

Run: `uv run pytest tests/test_kis_broker.py tests/test_toss_broker.py tests/test_server.py -q`
Expected: PASS.
Run: `cd web && npm run build` → 성공.
Run: `uv run pytest -q` → 전 프로젝트 그린.

- [ ] **Step 5: 커밋**

```bash
git add ohmystock/core/broker/kis.py ohmystock/core/broker/toss.py server/app.py web/src/api.ts web/src/components/BrokerAccountPanel.tsx tests/
git commit -m "feat: show holding names in account panel (get_holdings, KIS prdt_name/TOSS name)"
```

---

### Task 5: USD 평가금액 원화 환산 참고

**Files:**
- Modify: `ohmystock/core/broker/toss.py` (`exchange_rate` 추가)
- Modify: `server/app.py` (`/api/broker/account` 에 `krw_rate`)
- Modify: `web/src/api.ts`, `web/src/components/BrokerAccountPanel.tsx`
- Test: `tests/test_toss_broker.py`, `tests/test_server.py`

**Interfaces:**
- Produces: `TossBroker.exchange_rate(base="USD", quote="KRW") -> float`; `/api/broker/account` 응답에 `krw_rate: number | null`.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_toss_broker.py` 끝에 추가:
```python
def test_exchange_rate():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/exchange-rate":
            assert request.url.params.get("baseCurrency") == "USD"
            assert request.url.params.get("quoteCurrency") == "KRW"
            return httpx.Response(200, json={"result": {"rate": "1385.50", "midRate": "1384.0"}})
        raise AssertionError(f"예상치 못한 경로 {request.url.path}")

    broker = _make_broker(handler, access_token="tok",
                          token_expires_at=datetime(2030, 1, 1))
    assert broker.exchange_rate("USD", "KRW") == 1385.5
```

`tests/test_server.py` 끝에 추가:
```python
def test_broker_account_toss_includes_krw_rate(tmp_path):
    from ohmystock.core.broker.base import Account

    class _TossFake:
        paper = False

        def get_account(self):
            return Account(equity=15028.0, cash=0.15)

        def get_holdings(self):
            return [{"symbol": "AAPL", "name": "애플", "value": 1795.0}]

        def exchange_rate(self, base="USD", quote="KRW"):
            return 1385.5

    client = _client_with_broker(tmp_path, lambda name: _TossFake())
    body = client.get("/api/broker/account?broker=toss").json()
    assert body["krw_rate"] == 1385.5


def test_broker_account_kis_krw_rate_null(tmp_path):
    body = _client_with_broker(tmp_path, lambda name: _FakeBroker()).get(
        "/api/broker/account?broker=kis").json()
    assert body["krw_rate"] is None
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_toss_broker.py::test_exchange_rate tests/test_server.py -k krw -q`
Expected: FAIL (`exchange_rate` 없음 / `krw_rate` 키 없음).

- [ ] **Step 3: 구현**

`ohmystock/core/broker/toss.py` 에 메서드 추가(예: `get_holdings` 아래):
```python
    def exchange_rate(self, base: str = "USD", quote: str = "KRW") -> float:
        """1 base = ? quote 환율(예: USD→KRW)."""
        headers = self._acct_headers()
        r = self._result(self.client.get(
            "/api/v1/exchange-rate",
            params={"baseCurrency": base, "quoteCurrency": quote},
            headers=headers))
        return float(r["rate"])
```

`server/app.py` 의 `broker_account` 엔드포인트에서 mode 계산 뒤, return 직전에 krw_rate 계산 후 응답에 포함:
```python
        mode = "paper" if getattr(b, "paper", False) else "live"
        krw_rate = None
        if broker == "toss":
            try:
                krw_rate = b.exchange_rate("USD", "KRW")
            except Exception:
                krw_rate = None
        return {
            "broker": broker,
            "mode": mode,
            "equity": acct.equity,
            "cash": acct.cash,
            "positions": positions,
            "krw_rate": krw_rate,
        }
```

`web/src/api.ts` 의 `BrokerAccount` 에 `krw_rate` 추가:
```typescript
export interface BrokerAccount {
  broker: string
  mode: string
  equity: number
  cash: number
  positions: { symbol: string; name: string; value: number }[]
  krw_rate: number | null
}
```

`web/src/components/BrokerAccountPanel.tsx`: `data` 렌더 영역에서 원화 환산 헬퍼 추가 + equity/cash 카드에 참고 표기. 컴포넌트 내부, `const fmt = formatter(broker)` 아래에 추가:
```tsx
  const krwFmt = new Intl.NumberFormat('ko-KR', { style: 'currency', currency: 'KRW', maximumFractionDigits: 0 })
  const toKrw = (usd: number): string | null =>
    data && data.krw_rate ? ` (≈${krwFmt.format(usd * data.krw_rate)})` : null
```
equity·cash 값 표시에 참고 추가(예: equity 카드):
```tsx
              <div style={{ fontSize: 22, fontVariantNumeric: 'tabular-nums' }}>
                {fmt.format(data.equity)}
                {data.krw_rate && (
                  <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>{toKrw(data.equity)}</span>
                )}
              </div>
```
cash 카드도 동일하게 `{data.krw_rate && <span ...>{toKrw(data.cash)}</span>}` 추가.

- [ ] **Step 4: 통과 확인 + 빌드 + 전체 스위트**

Run: `uv run pytest tests/test_toss_broker.py tests/test_server.py -q` → PASS.
Run: `cd web && npm run build` → 성공.
Run: `uv run pytest -q` → 그린.

- [ ] **Step 5: 커밋**

```bash
git add ohmystock/core/broker/toss.py server/app.py web/src/api.ts web/src/components/BrokerAccountPanel.tsx tests/
git commit -m "feat: show KRW reference for USD account amounts (TOSS exchange-rate)"
```

---

### Task 6: 캘린더 거래일/휴장 색 구분 강화 (CSS)

**Files:**
- Modify: `web/src/App.css` (`cal-cell-open`/`cal-cell-holiday`/범례 점)

**Interfaces:**
- Consumes: 기존 `CalendarPanel` 마크업(클래스 불변). CSS-only.

- [ ] **Step 1: 색 규칙 강화**

`web/src/App.css` 의 캘린더 셀 규칙을 아래로 교체(거래일=뚜렷한 활성, 휴장=명확히 흐림+적색 틸트):
```css
.cal-cell-holiday {
  background: color-mix(in srgb, var(--fail) 10%, var(--surface-2));
  color: var(--text-dim);
}

.cal-cell-open {
  background: color-mix(in srgb, var(--accent) 8%, transparent);
  color: var(--text);
  font-weight: 600;
}
```
그리고 범례 점을 셀과 일치시키기:
```css
.cal-legend-dot-open {
  background: color-mix(in srgb, var(--accent) 30%, var(--surface));
  border: 1px solid var(--accent);
}

.cal-legend-dot-holiday {
  background: color-mix(in srgb, var(--fail) 25%, var(--surface-2));
  border: 1px solid var(--fail);
}
```

- [ ] **Step 2: 빌드 확인**

Run: `cd web && npm run build`
Expected: 빌드 성공(CSS 변경, 타입 영향 없음).

- [ ] **Step 3: 커밋**

```bash
git add web/src/App.css
git commit -m "style(web): clearer trading-day vs holiday colors in calendar"
```

---

## 완료 후

- 백엔드+프론트 머지 후 실 서버로 확인: 시장 개요 카드(지수·등락·스파크라인)·장 상태·실 계좌 종목명/원화·캘린더 색.
- 적대적 점검은 읽기 전용·UI라 경량(시장 데이터 실패 처리·캐시 확인). v2 뉴스 레이어는 별도 spec/plan.
