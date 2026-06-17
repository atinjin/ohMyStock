# 스케줄러 진입점 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 매 거래일 장 마감 후 페이퍼 계좌를 최신 거래일까지 자동 전진시키는 멱등 CLI 진입점(`python -m ohmystock.scheduler run-once`)을 만든다.

**Architecture:** `ohmystock/scheduler.py` 단일 모듈 — `compute_target_date`(마감 완료된 최신 거래일) + `run_once`(due 판정 후 `PaperService.run(to=)`로 따라잡기) + CLI. 기존 `MarketCalendar`·`PaperService`를 호출만 한다. `now`·캘린더·서비스를 주입받아 결정적 테스트.

**Tech Stack:** Python 3.11, stdlib argparse/zoneinfo, 기존 코어(exchange_calendars 래퍼, PaperService).

## Global Constraints

- 테스트 `uv run pytest <path> -q`. "VIRTUAL_ENV 3.9.11 ... ignored" 경고는 무해.
- 모든 테스트 오프라인(FakeAdapter·임시 SQLite·주입 now). 시계 모킹 없음.
- 시장 타임존 = `ZoneInfo("America/New_York")`. `now`는 ET tz-aware로 전달.

---

## 참고 — 재사용 인터페이스 (이미 구현됨)

- `ohmystock/core/calendar/exchange.py::us_market_calendar() -> ExchangeMarketCalendar`
  - `.is_trading_day(d: date) -> bool`
  - `.previous_trading_day(d: date) -> date` (엄격히 이전)
  - `.session_times(d: date) -> tuple[datetime, datetime] | None` (개장, 마감) tz-aware ET, 비거래일 None
- `ohmystock/paper/service.py::PaperService(store, adapter, config)`
  - `.init_account(strategy, params, symbols, capital, start, end)`
  - `.run(steps=None, to=None) -> list[dict]` (커서를 앞으로만 전진; 데이터 끝/`to` 도달 시 멈춤)
  - `.get_state() -> dict` — 미생성이면 `{"exists": False}`, 아니면 `exists`/`cursor_date`/`equity`/... 포함
- `ohmystock/paper/sqlite_store.py::SqlitePaperStore(db_path)`
- `ohmystock/core/data/yfinance_adapter.py::YFinanceAdapter(cache=...)`, `ohmystock/core/data/cache.py::ParquetCache(dir)`, `ohmystock/config.py::Config`

---

## Task 1: compute_target_date + run_once

**Files:**
- Create: `ohmystock/scheduler.py`
- Test: `tests/test_scheduler.py`

**Interfaces:**
- Produces: `compute_target_date(calendar, now: datetime) -> date | None`; `run_once(service, calendar, now: datetime) -> dict` (키: `ran: bool`, `reason: str`, 그리고 전진 시 `target`/`steps`/`cursor`/`equity`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scheduler.py
from datetime import date, datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from ohmystock.config import Config
from ohmystock.core.calendar.exchange import us_market_calendar
from ohmystock.paper.service import PaperService
from ohmystock.paper.sqlite_store import SqlitePaperStore
from ohmystock.scheduler import compute_target_date, run_once

ET = ZoneInfo("America/New_York")


class FakeAdapter:
    def get_daily_bars(self, symbols, start, end):
        idx = pd.bdate_range("2024-06-03", periods=20)  # 마지막 = 2024-06-28(금)
        out = {}
        for i, s in enumerate(symbols):
            closes = np.linspace(10 + i, 30 + i, 20)
            out[s] = pd.DataFrame(
                {"open": closes, "high": closes, "low": closes,
                 "close": closes, "volume": [1e6] * 20}, index=idx)
        return out


def _service(tmp_path):
    return PaperService(SqlitePaperStore(tmp_path / "p.db"), FakeAdapter(), Config())


def _inited(tmp_path):
    svc = _service(tmp_path)
    svc.init_account("MACrossover", {"short": 3, "long": 10}, ["AAPL"],
                     1_000_000, "2024-06-03", "2024-06-28")
    return svc


# ---- compute_target_date ----

def test_target_after_close():
    cal = us_market_calendar()
    # 2024-07-02(화) 마감 16:00 ET, 17:00 -> 당일
    assert compute_target_date(cal, datetime(2024, 7, 2, 17, 0, tzinfo=ET)) == date(2024, 7, 2)


def test_target_before_close():
    cal = us_market_calendar()
    # 2024-07-02 12:00 (마감 전) -> 직전거래일 2024-07-01
    assert compute_target_date(cal, datetime(2024, 7, 2, 12, 0, tzinfo=ET)) == date(2024, 7, 1)


def test_target_half_day_after_close():
    cal = us_market_calendar()
    # 2024-07-03 반장일 마감 13:00, 14:00 -> 당일
    assert compute_target_date(cal, datetime(2024, 7, 3, 14, 0, tzinfo=ET)) == date(2024, 7, 3)


def test_target_weekend():
    cal = us_market_calendar()
    assert compute_target_date(cal, datetime(2024, 7, 6, 10, 0, tzinfo=ET)) == date(2024, 7, 5)


def test_target_holiday():
    cal = us_market_calendar()
    # 2024-07-04 휴일 -> 2024-07-03
    assert compute_target_date(cal, datetime(2024, 7, 4, 10, 0, tzinfo=ET)) == date(2024, 7, 3)


# ---- run_once ----

def test_run_once_advances_to_latest(tmp_path):
    svc = _inited(tmp_path)
    cal = us_market_calendar()
    now = datetime(2024, 6, 28, 17, 0, tzinfo=ET)  # 마감 후, target=2024-06-28 = 데이터 끝
    res = run_once(svc, cal, now)
    assert res["ran"] is True
    assert res["steps"] > 0
    last = pd.bdate_range("2024-06-03", periods=20)[-1].strftime("%Y-%m-%d")
    assert svc.get_state()["cursor_date"] == last  # 최신까지 전진


def test_run_once_idempotent(tmp_path):
    svc = _inited(tmp_path)
    cal = us_market_calendar()
    now = datetime(2024, 6, 28, 17, 0, tzinfo=ET)
    run_once(svc, cal, now)            # 1회차: 전진
    res2 = run_once(svc, cal, now)     # 2회차: 커서가 이미 target 이상
    assert res2["ran"] is False
    assert res2["reason"] == "최신"


def test_run_once_no_account(tmp_path):
    svc = _service(tmp_path)           # init 안 함
    cal = us_market_calendar()
    res = run_once(svc, cal, datetime(2024, 6, 28, 17, 0, tzinfo=ET))
    assert res["ran"] is False
    assert res["reason"] == "계좌 없음"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scheduler.py -q`
Expected: FAIL (ImportError: cannot import name 'compute_target_date' / ModuleNotFoundError)

- [ ] **Step 3: Write `ohmystock/scheduler.py`**

```python
"""거래일 스케줄러 진입점 (cron 래퍼).

매 거래일 장 마감 후 페이퍼 계좌를 최신 거래일까지 전진시킨다. 멱등.
외부 cron / /schedule(cloud agent)이 `python -m ohmystock.scheduler run-once`를
주기적으로 호출하면, 지금이 돌릴 때인지 스스로 판정한다.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")


def compute_target_date(calendar, now: datetime) -> date | None:
    """now(ET tz-aware) 기준, 마감이 완료된 가장 최근 거래일."""
    today = now.date()
    if calendar.is_trading_day(today):
        times = calendar.session_times(today)
        if times is not None:
            _open, close = times
            if now >= close:
                return today
        return calendar.previous_trading_day(today)
    return calendar.previous_trading_day(today)


def run_once(service, calendar, now: datetime) -> dict:
    """due면 페이퍼 계좌를 최신 거래일까지 전진. 멱등(커서는 앞으로만 이동)."""
    state = service.get_state()
    if not state.get("exists"):
        return {"ran": False, "reason": "계좌 없음"}

    target = compute_target_date(calendar, now)
    if target is None:
        return {"ran": False, "reason": "거래일 없음"}

    target_iso = target.isoformat()
    cursor = state.get("cursor_date")
    if cursor is not None and cursor >= target_iso:
        return {"ran": False, "reason": "최신", "cursor": cursor, "target": target_iso}

    results = service.run(to=target_iso)
    new_state = service.get_state()
    return {
        "ran": len(results) > 0,
        "reason": "전진" if results else "데이터 없음",
        "target": target_iso,
        "steps": len(results),
        "cursor": new_state.get("cursor_date"),
        "equity": new_state.get("equity"),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_scheduler.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add ohmystock/scheduler.py tests/test_scheduler.py
git commit -m "feat: add scheduler core (compute_target_date + idempotent run_once)"
```

---

## Task 2: CLI (run-once)

**Files:**
- Modify: `ohmystock/scheduler.py`
- Test: `tests/test_scheduler_cli.py`

**Interfaces:**
- Consumes: `run_once` (Task 1).
- Produces: `run_cli(argv=None, *, service=None, calendar=None, now=None) -> dict`; `main() -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scheduler_cli.py
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from ohmystock.config import Config
from ohmystock.core.calendar.exchange import us_market_calendar
from ohmystock.paper.service import PaperService
from ohmystock.paper.sqlite_store import SqlitePaperStore
from ohmystock.scheduler import run_cli

ET = ZoneInfo("America/New_York")


class FakeAdapter:
    def get_daily_bars(self, symbols, start, end):
        idx = pd.bdate_range("2024-06-03", periods=20)
        out = {}
        for i, s in enumerate(symbols):
            closes = np.linspace(10 + i, 30 + i, 20)
            out[s] = pd.DataFrame(
                {"open": closes, "high": closes, "low": closes,
                 "close": closes, "volume": [1e6] * 20}, index=idx)
        return out


def test_run_cli_run_once(tmp_path, capsys):
    svc = PaperService(SqlitePaperStore(tmp_path / "p.db"), FakeAdapter(), Config())
    svc.init_account("MACrossover", {"short": 3, "long": 10}, ["AAPL"],
                     1_000_000, "2024-06-03", "2024-06-28")
    res = run_cli(["run-once"], service=svc, calendar=us_market_calendar(),
                  now=datetime(2024, 6, 28, 17, 0, tzinfo=ET))
    assert res["ran"] is True
    assert "ran" in capsys.readouterr().out  # 결과 한 줄 출력
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scheduler_cli.py -q`
Expected: FAIL (ImportError: cannot import name 'run_cli')

- [ ] **Step 3: Append CLI to `ohmystock/scheduler.py`**

Add these imports at the top (below the existing `from datetime ...` / `from zoneinfo ...`):
```python
import argparse

from ohmystock.config import Config
from ohmystock.core.calendar.exchange import us_market_calendar
from ohmystock.core.data.cache import ParquetCache
from ohmystock.core.data.yfinance_adapter import YFinanceAdapter
from ohmystock.paper.service import PaperService
from ohmystock.paper.sqlite_store import SqlitePaperStore

DEFAULT_DB = "state/paper.db"
```

Append at the end of the file (after `run_once`):
```python
def run_cli(argv=None, *, service=None, calendar=None, now=None) -> dict:
    parser = argparse.ArgumentParser(prog="ohmystock.scheduler")
    parser.add_argument("--db", default=DEFAULT_DB)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run-once")
    args = parser.parse_args(argv)

    if service is None:
        service = PaperService(
            SqlitePaperStore(args.db),
            YFinanceAdapter(cache=ParquetCache(".cache")),
            Config(),
        )
    if calendar is None:
        calendar = us_market_calendar()
    if now is None:
        now = datetime.now(_ET)

    result = run_once(service, calendar, now)
    print(result)
    return result


def main() -> None:
    run_cli()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_scheduler_cli.py -q`
Then full suite: `uv run pytest -q`
Expected: PASS (전체).

- [ ] **Step 5: Commit**

```bash
git add ohmystock/scheduler.py tests/test_scheduler_cli.py
git commit -m "feat: add scheduler run-once CLI (python -m ohmystock.scheduler)"
```

---

## Task 3: 스모크 + 머지

- [ ] **Step 1: 전체 테스트**

Run: `uv run pytest -q`
Expected: 전체 PASS (기존 + scheduler).

- [ ] **Step 2: 실데이터 CLI 스모크 (네트워크)**

```bash
uv run python -m ohmystock.paper --db state/sched.db init --strategy Momentum --symbols AAPL,MSFT,GOOGL --capital 5000000 --start 2024-01-01 --end 2024-12-31
uv run python -m ohmystock.scheduler --db state/sched.db run-once
uv run python -m ohmystock.scheduler --db state/sched.db run-once   # 2회차 멱등 확인
rm -f state/sched.db
```
Expected: 1회차 `{'ran': True, ...}`(최신 거래일까지 전진), 2회차 `{'ran': False, 'reason': '최신' 또는 '데이터 없음'}`.

- [ ] **Step 3: 머지**

```bash
git checkout main && git merge --no-ff <feature-branch>
uv run pytest -q
git push origin main
```

---

## Self-Review

**Spec 커버리지:**
- §2 모듈 구조(compute_target_date/run_once/run_cli/main) → Task 1,2 ✓
- §3 due 판정(마감 후→당일 / 마감 전·휴장→직전거래일) → Task 1 compute_target_date + 5개 테스트 ✓
- §4 오케스트레이션(계좌없음·최신·전진·멱등) → Task 1 run_once + 3개 테스트 ✓
- §5 CLI(run-once, 주입 가능) → Task 2 ✓
- §6 에러(계좌 없음→ran False) → Task 1 test_run_once_no_account ✓
- §7 테스트(결정적·오프라인) → 각 Task ✓
- §8 비범위(APScheduler·실계좌·알림) — 미포함(정상) ✓

**플레이스홀더:** 완전한 코드(검증된 PaperService/MarketCalendar 시그니처).

**타입 일관성:**
- `compute_target_date(calendar, now) -> date|None`, `run_once(service, calendar, now) -> dict` — Task 1 정의 ↔ Task 2 run_cli 호출 일치 ✓
- `run_once` 반환 키(ran/reason/target/steps/cursor/equity) — Task 1 ↔ 테스트 일치 ✓
- FakeAdapter 마지막 거래일 2024-06-28 = `pd.bdate_range("2024-06-03", periods=20)[-1]` (테스트가 동적으로 계산) ✓

**검증된 사실:** 2024-07-02 마감 16:00·2024-07-03 반장일 13:00·2024-07-04 휴일·2024-07-06 토요일 → 직전거래일 규약. `cursor >= target_iso`는 ISO 날짜 문자열의 사전식=시간순 비교라 정확.
