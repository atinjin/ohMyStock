# 거래일·장시간 캘린더 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 미래 날짜까지 정확한 미국 거래일·세션시각(반장일·DST 포함)을 제공하는 `MarketCalendar`(exchange_calendars 래퍼)와, 이를 조회하는 `/api/calendar` + 대시보드 월별 달력 패널을 만든다.

**Architecture:** `ohmystock/core/calendar/`에 `MarketCalendar` Protocol + `ExchangeMarketCalendar`(거래소코드 래퍼) + `us_market_calendar()`. 캘린더는 "현재 시각"을 내부에 두지 않아 결정적. 그 위에 얇은 `GET /api/calendar` 조회 API와 React 달력 패널.

**Tech Stack:** Python 3.11, `exchange_calendars` 4.x, pandas, FastAPI, React/Vite.

---

## File Structure

| 파일 | 책임 |
|------|------|
| `ohmystock/core/calendar/__init__.py` | 패키지 |
| `ohmystock/core/calendar/base.py` | `MarketCalendar` Protocol |
| `ohmystock/core/calendar/exchange.py` | `ExchangeMarketCalendar` + `us_market_calendar()` |
| `server/app.py` | `GET /api/calendar` + lazy `app.state.calendar` (수정) |
| `web/src/api.ts` | `getCalendar` + 타입 (수정) |
| `web/src/components/CalendarPanel.tsx` | 월별 달력 그리드 |
| `web/src/App.tsx`, `web/src/App.css` | 패널 마운트·스타일 (수정) |

`exchange_calendars` 검증된 API(v4.13.2): `get_calendar(code)`, `cal.tz`(="America/New_York"), `cal.is_session(ts)`, `cal.next_session(ts)`/`cal.previous_session(ts)`(**비session 입력 시 NotSessionError**), `cal.date_to_session(ts, direction="next"/"previous")`(임의 날짜 OK, **해당 방향의 첫 session, 같은 날 포함**), `cal.session_open(ts)`/`cal.session_close(ts)`(**UTC tz-aware**), `cal.is_open_on_minute(ts_tz_aware)`, `cal.first_session`/`cal.last_session`(tz-naive).

---

## Task 0: 의존성 + 패키지

**Files:** Modify `pyproject.toml`, `uv.lock`; Create `ohmystock/core/calendar/__init__.py`

- [ ] **Step 1: 의존성 추가 (이미 추가됐다면 확인만)**

Run:
```bash
cd /Users/atinjin/repository/OhMyStock
uv add exchange-calendars
mkdir -p ohmystock/core/calendar
touch ohmystock/core/calendar/__init__.py
uv run python -c "import exchange_calendars; print(exchange_calendars.__version__)"
```
Expected: 버전 출력(4.x).

- [ ] **Step 2: Commit**

```bash
git add pyproject.toml uv.lock ohmystock/core/calendar/__init__.py
git commit -m "chore: add exchange_calendars dep and calendar package"
```

---

## Task 1: MarketCalendar 인터페이스 + ExchangeMarketCalendar

**Files:** Create `ohmystock/core/calendar/base.py`, `ohmystock/core/calendar/exchange.py`; Test `tests/test_market_calendar.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_market_calendar.py
from datetime import date, datetime
from zoneinfo import ZoneInfo
from ohmystock.core.calendar.exchange import us_market_calendar

ET = ZoneInfo("America/New_York")


def test_is_trading_day():
    cal = us_market_calendar()
    assert cal.is_trading_day(date(2024, 7, 3)) is True    # 수요일 거래일
    assert cal.is_trading_day(date(2024, 7, 4)) is False   # 독립기념일(휴장)
    assert cal.is_trading_day(date(2024, 7, 6)) is False   # 토요일


def test_next_previous_trading_day_strict_and_skip():
    cal = us_market_calendar()
    # 금 7/5 -> 다음 거래일 월 7/8 (주말 건너뜀, 같은 날 미포함)
    assert cal.next_trading_day(date(2024, 7, 5)) == date(2024, 7, 8)
    # 수 7/3 -> 7/4 휴일 + 주말 건너뛰어 월 7/8
    assert cal.next_trading_day(date(2024, 7, 3)) == date(2024, 7, 8)
    # 비거래일(토 7/6)에서 다음 거래일 = 월 7/8
    assert cal.next_trading_day(date(2024, 7, 6)) == date(2024, 7, 8)
    # 월 7/8 직전 거래일 = 금 7/5
    assert cal.previous_trading_day(date(2024, 7, 8)) == date(2024, 7, 5)
    # 비거래일(토 7/6) 직전 거래일 = 금 7/5
    assert cal.previous_trading_day(date(2024, 7, 6)) == date(2024, 7, 5)


def test_session_times_full_half_and_none():
    cal = us_market_calendar()
    full = cal.session_times(date(2024, 7, 2))   # 정규일
    assert full is not None
    o, c = full
    assert (o.hour, o.minute) == (9, 30)
    assert (c.hour, c.minute) == (16, 0)

    half = cal.session_times(date(2024, 7, 3))   # 독립기념일 전날 = 반장일
    assert half is not None
    _, hc = half
    assert (hc.hour, hc.minute) == (13, 0)

    assert cal.session_times(date(2024, 7, 4)) is None   # 휴장일


def test_is_open():
    cal = us_market_calendar()
    assert cal.is_open(datetime(2024, 7, 3, 10, 0, tzinfo=ET)) is True    # 장중(반장일 9:30~13:00)
    assert cal.is_open(datetime(2024, 7, 3, 15, 0, tzinfo=ET)) is False   # 반장일 마감 13:00 이후
    assert cal.is_open(datetime(2024, 7, 4, 10, 0, tzinfo=ET)) is False   # 휴일
    assert cal.is_open(datetime(2024, 7, 6, 10, 0, tzinfo=ET)) is False   # 토요일
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_market_calendar.py -q`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write `ohmystock/core/calendar/base.py`**

```python
from datetime import date, datetime
from typing import Protocol


class MarketCalendar(Protocol):
    """거래일·세션시각 판정. 내부에 '현재 시각'을 두지 않아 결정적."""

    def is_trading_day(self, d: date) -> bool: ...
    def next_trading_day(self, d: date) -> date: ...        # d 다음 거래일(엄격히 이후)
    def previous_trading_day(self, d: date) -> date: ...     # d 직전 거래일(엄격히 이전)
    def session_times(self, d: date) -> tuple[datetime, datetime] | None: ...
    #   그 날 (개장, 마감) tz-aware 현지시각. 비거래일이면 None. 반장일 반영.
    def is_open(self, dt: datetime) -> bool: ...             # tz-aware 시각에 장이 열렸나
```

- [ ] **Step 4: Write `ohmystock/core/calendar/exchange.py`**

```python
from datetime import date, datetime

import pandas as pd
import exchange_calendars as xcals

_REGULAR_CLOSE_HOUR = 16  # XNYS 정규 마감(현지시각)


class ExchangeMarketCalendar:
    """exchange_calendars 래퍼. MarketCalendar 인터페이스 구현."""

    def __init__(self, code: str = "XNYS"):
        self._cal = xcals.get_calendar(code)
        self._tz = self._cal.tz

    def _in_bounds(self, ts: pd.Timestamp) -> bool:
        return self._cal.first_session <= ts <= self._cal.last_session

    def is_trading_day(self, d: date) -> bool:
        ts = pd.Timestamp(d)
        if not self._in_bounds(ts):
            return False
        return bool(self._cal.is_session(ts))

    def next_trading_day(self, d: date) -> date:
        ts = pd.Timestamp(d)
        # 거래일이면 다음 세션(엄격히 이후), 비거래일이면 그 이후 첫 세션(엄격히 이후)
        if self._cal.is_session(ts):
            return self._cal.next_session(ts).date()
        return self._cal.date_to_session(ts, direction="next").date()

    def previous_trading_day(self, d: date) -> date:
        ts = pd.Timestamp(d)
        if self._cal.is_session(ts):
            return self._cal.previous_session(ts).date()
        return self._cal.date_to_session(ts, direction="previous").date()

    def session_times(self, d: date) -> tuple[datetime, datetime] | None:
        ts = pd.Timestamp(d)
        if not self._in_bounds(ts) or not self._cal.is_session(ts):
            return None
        open_local = self._cal.session_open(ts).tz_convert(self._tz)
        close_local = self._cal.session_close(ts).tz_convert(self._tz)
        return (open_local.to_pydatetime(), close_local.to_pydatetime())

    def is_open(self, dt: datetime) -> bool:
        ts = pd.Timestamp(dt)
        if ts.tz is None:
            raise ValueError("tz-aware datetime이 필요합니다")
        d = ts.tz_convert(self._tz).date()
        if not (self._cal.first_session.date() <= d <= self._cal.last_session.date()):
            return False
        try:
            return bool(self._cal.is_open_on_minute(ts.floor("min")))
        except Exception:
            return False


def us_market_calendar() -> ExchangeMarketCalendar:
    """미국(NYSE/XNYS) 캘린더."""
    return ExchangeMarketCalendar("XNYS")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_market_calendar.py -q`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add ohmystock/core/calendar/base.py ohmystock/core/calendar/exchange.py tests/test_market_calendar.py
git commit -m "feat: add MarketCalendar interface + ExchangeMarketCalendar (XNYS, half-days, tz-aware)"
```

---

## Task 2: /api/calendar 엔드포인트

**Files:** Modify `server/app.py`; Test `tests/test_calendar_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_calendar_api.py
from fastapi.testclient import TestClient
from server.app import create_app


class FakeAdapter:
    def get_daily_bars(self, symbols, start, end):
        return {}


def _client():
    return TestClient(create_app(adapter=FakeAdapter()))


def test_calendar_month():
    c = _client()
    r = c.get("/api/calendar?year=2024&month=7")
    assert r.status_code == 200
    data = r.json()
    assert data["year"] == 2024 and data["month"] == 7
    days = {d["date"]: d for d in data["days"]}
    assert len(days) == 31
    assert days["2024-07-04"]["is_trading_day"] is False
    assert days["2024-07-03"]["is_trading_day"] is True
    assert days["2024-07-03"]["close"] == "13:00"
    assert days["2024-07-03"]["is_half_day"] is True
    assert days["2024-07-02"]["close"] == "16:00"
    assert days["2024-07-02"]["is_half_day"] is False


def test_calendar_bad_month():
    assert _client().get("/api/calendar?year=2024&month=13").status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_calendar_api.py -q`
Expected: FAIL (404 — endpoint not yet defined)

- [ ] **Step 3: Modify `server/app.py`**

Add imports near the top (with the other imports):
```python
import calendar as _pycal
from ohmystock.core.calendar.exchange import us_market_calendar
```

In `create_app`, right after `app.state.paper_db = paper_db`, add:
```python
    app.state.calendar = None  # lazy: /api/calendar 첫 요청 때 생성
```

Add this endpoint inside `create_app`, before `return app`:
```python
    def _market_calendar():
        if app.state.calendar is None:
            app.state.calendar = us_market_calendar()
        return app.state.calendar

    @app.get("/api/calendar")
    def market_calendar(year: int, month: int):
        if month < 1 or month > 12:
            raise HTTPException(status_code=400, detail="month은 1~12 이어야 합니다")
        cal = _market_calendar()
        n_days = _pycal.monthrange(year, month)[1]
        days = []
        for day in range(1, n_days + 1):
            d = date(year, month, day)
            times = cal.session_times(d)
            if times is None:
                days.append({
                    "date": d.isoformat(), "is_trading_day": False,
                    "open": None, "close": None, "is_half_day": False,
                })
            else:
                open_dt, close_dt = times
                days.append({
                    "date": d.isoformat(), "is_trading_day": True,
                    "open": open_dt.strftime("%H:%M"),
                    "close": close_dt.strftime("%H:%M"),
                    "is_half_day": close_dt.hour < 16,
                })
        return {"year": year, "month": month, "days": days}
```
(`date` and `HTTPException` are already imported in server/app.py.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_calendar_api.py -q`
Then full suite: `uv run pytest -q`
Expected: PASS (all). Existing endpoints unaffected (calendar is lazily built only when /api/calendar is hit).

- [ ] **Step 5: Commit**

```bash
git add server/app.py tests/test_calendar_api.py
git commit -m "feat: add GET /api/calendar (month grid of trading days + session hours)"
```

---

## Task 3: 대시보드 월별 달력 패널

**Files:** Modify `web/src/api.ts`, `web/src/App.tsx`, `web/src/App.css`; Create `web/src/components/CalendarPanel.tsx`

API 계약 (Task 2):
- `GET /api/calendar?year=YYYY&month=MM` → `{year, month, days:[{date:"YYYY-MM-DD", is_trading_day:boolean, open:"HH:MM"|null, close:"HH:MM"|null, is_half_day:boolean}]}` (month 1~12; 잘못된 month → 400)

- [ ] **Step 1: api.ts — 타입 + 클라이언트**

Add:
```ts
export interface CalendarDay {
  date: string
  is_trading_day: boolean
  open: string | null
  close: string | null
  is_half_day: boolean
}
export interface CalendarMonth {
  year: number
  month: number
  days: CalendarDay[]
}
export async function getCalendar(year: number, month: number): Promise<CalendarMonth> {
  const r = await fetch(`/api/calendar?year=${year}&month=${month}`)
  if (!r.ok) throw new Error((await r.json()).detail ?? '캘린더 조회 실패')
  return r.json()
}
```

- [ ] **Step 2: Create `web/src/components/CalendarPanel.tsx`**

A `.card` component (no props needed) that:
- Holds `year`/`month` state (default = current month from `new Date()`), `data: CalendarMonth | null`, `error: string | null`.
- On mount and whenever year/month change (useEffect), calls `getCalendar(year, month)` → setData (try/catch → setError).
- Header: "거래 캘린더" + ◀ / ▶ buttons that decrement/increment month (rolling over year), and a `YYYY년 MM월` label.
- A 7-column grid (요일 헤더 일~토). Compute leading blanks from the weekday of day 1 (`new Date(year, month-1, 1).getDay()`), then one cell per day from `data.days`.
- Each day cell shows the day number; class by status:
  - non-trading → muted/holiday style (`.cal-cell-holiday`)
  - trading full day → normal (`.cal-cell-open`)
  - half day → trading style + a small "조기마감 {close}" badge (`.cal-cell-half`)
  - today (matches `new Date()` y/m/d) → highlight ring (`.cal-cell-today`)
- A small legend row: 거래일 / 휴장 / 반장일 / 오늘.
- Show `error` (dim red) if set.
- Keep TS strict-clean (no `any`; type the day lookup). Match the dark theme.

- [ ] **Step 3: Wire into `App.tsx`**

- Import `CalendarPanel` and render `<CalendarPanel />` in the main panel area (e.g. near the PaperPanel). It is self-contained (own data fetching), render it always.

- [ ] **Step 4: `App.css` — calendar styles**

Add styles (reuse theme vars): `.calendar-grid` (7-col grid), `.cal-weekday` (dim header), `.cal-cell` (square-ish, border, padding), `.cal-cell-holiday` (muted bg `--surface-2`, dim text), `.cal-cell-open` (normal), `.cal-cell-half` (accent-tinted + small badge), `.cal-cell-today` (border `--accent`), `.cal-badge` (tiny early-close label), `.cal-nav` (header with ◀▶ + label flex row), `.cal-legend` (small flex row of colored dots + labels). Keep it tidy and responsive.

- [ ] **Step 5: Build**

Run: `cd web && npm run build`
Expected: TypeScript + build pass, no errors.

- [ ] **Step 6: Commit**

```bash
git add web/src
git commit -m "feat(web): add market calendar panel (month grid, trading/holiday/half-day, today)"
```

---

## Task 4: 스모크 + 머지

- [ ] **Step 1: 전체 테스트**

Run: `uv run pytest -q`
Expected: 전체 PASS (기존 + market_calendar + calendar_api).

- [ ] **Step 2: 실서버 스모크**

Run:
```bash
uv run uvicorn server.app:app --port 8011 --log-level warning &
sleep 4
curl -s "http://localhost:8011/api/calendar?year=2024&month=11" | python3 -c "import sys,json;d=json.load(sys.stdin);hd=[x for x in d['days'] if x['is_half_day']];print('half-days:',[(x['date'],x['close']) for x in hd])"
kill %1
```
Expected: 2024-11-29(추수감사절 다음날)이 반장일 13:00 로 출력.

- [ ] **Step 3: 웹 빌드 확인**

Run: `cd web && npm run build`
Expected: 통과.

- [ ] **Step 4: 머지**

```bash
git checkout main && git merge --no-ff <feature-branch>
uv run pytest -q
git push origin main
```

---

## Self-Review

**Spec 커버리지:**
- §2 모듈 구조 → Task 0,1 ✓
- §3 MarketCalendar 인터페이스(is_trading_day/next/previous/session_times/is_open) → Task 1 base.py + exchange.py ✓
- §4 exchange_calendars 래퍼(XNYS, tz 변환, 반장일) → Task 1 exchange.py ✓
- §5 에러(비거래일 None, 범위밖 처리) → Task 1(_in_bounds, session_times None) ✓
- §6 테스트(거래일/반장일/next·prev/is_open, 오프라인) → Task 1 test ✓
- §7 웹 조회: API → Task 2 ; 대시보드 패널 → Task 3 ✓
- §8 비범위(스케줄러·실주문·XKRX) — 미포함(정상) ✓

**플레이스홀더:** Task 0~2는 완전한 코드(검증된 exchange_calendars 메서드명). Task 3은 컴포넌트 요구사항 명시 + 빌드 게이트.

**타입 일관성:**
- `MarketCalendar` 메서드(is_trading_day/next_trading_day/previous_trading_day/session_times/is_open) — base Protocol ↔ exchange 구현 일치 ✓
- `us_market_calendar()` — Task 1 정의 ↔ Task 2 server import 일치 ✓
- API 응답 `{year,month,days:[{date,is_trading_day,open,close,is_half_day}]}` — Task 2 ↔ Task 3 api.ts 타입 일치 ✓

**검증된 사실(probe):** 2024-07-03 반장일(13:00 ET), 2024-07-02 정규(16:00), next_trading_day(7/5)=7/8, exchange_calendars 범위 ~2027. `next_session`은 비session 입력 시 예외라 `is_session` 분기 + `date_to_session` 사용.
