# 스케줄러 재시도·백오프 + 실행 로그 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 스케줄러 실행을 지수 백오프로 재시도하고 각 결과를 SQLite(`scheduler_runs`)에 기록해 CLI·API·대시보드로 조회한다.

**Architecture:** 새 `SqliteSchedulerStore`(paper.db 공유) + `scheduler.py`에 `run_scheduled`(기존 멱등 `run_once`를 재시도+기록으로 감쌈). CLI `history`/`last-run`, `GET /api/scheduler/runs`, 대시보드 패널.

**Tech Stack:** Python 3.11 stdlib sqlite3/time, FastAPI, React/Vite.

## Global Constraints

- 테스트 `uv run pytest <path> -q`. "VIRTUAL_ENV 3.9.11 ... ignored" 경고 무해.
- 모든 테스트 오프라인·결정적(`now`/`sleep`/`store` 주입, FakeAdapter, 임시 DB).
- 재시도: 예외 시 최대 `max_attempts=3`, 지수 백오프 `base_delay=5.0`·`factor=2.0`(→5,10초 대기). "계좌 없음" 등 dict 결과는 재시도 안 함.

---

## 참고 — 재사용 (구현됨)

- `ohmystock/scheduler.py::run_once(service, calendar, now) -> dict` (멱등 단일 시도; 키 `ran`/`reason`, 전진 시 `target`/`steps`/`cursor`/`equity`). `run_cli(argv=None, *, service=None, calendar=None, now=None) -> dict` (현재 run-once만). 모듈 상단에 `_ET = ZoneInfo("America/New_York")`, `DEFAULT_DB = "state/paper.db"`, 및 `Config`/`ParquetCache`/`YFinanceAdapter`/`PaperService`/`SqlitePaperStore` import 존재.
- `ohmystock/paper/sqlite_store.py::SqlitePaperStore`, `ohmystock/paper/service.py::PaperService`.
- `server/app.py::create_app(adapter=None, paper_db="state/paper.db")` — `app.state.paper_db` 보유. `HTTPException` import됨. lazy 패턴(`app.state.calendar` 등) 존재.

---

## Task 1: SqliteSchedulerStore

**Files:** Create `ohmystock/scheduler_store.py`; Test `tests/test_scheduler_store.py`

**Interfaces:**
- Produces: `SqliteSchedulerStore(db_path)` with `record_run(*, ts, status, reason, target, steps, equity, attempts, error) -> None`, `recent_runs(limit=20) -> list[dict]`, `last_run() -> dict|None`, `last_success() -> dict|None`. 각 dict 키 = 컬럼명(id/ts/status/reason/target/steps/equity/attempts/error).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scheduler_store.py
from ohmystock.scheduler_store import SqliteSchedulerStore


def _rec(store, **kw):
    base = dict(ts="2024-01-01T17:00:00-05:00", status="ok", reason="전진",
                target="2024-01-01", steps=1, equity=1000.0, attempts=1, error=None)
    base.update(kw)
    store.record_run(**base)


def test_empty(tmp_path):
    s = SqliteSchedulerStore(tmp_path / "p.db")
    assert s.recent_runs() == []
    assert s.last_run() is None
    assert s.last_success() is None


def test_record_and_query(tmp_path):
    s = SqliteSchedulerStore(tmp_path / "p.db")
    _rec(s, status="ok", target="2024-01-02")
    _rec(s, status="failed", reason="boom", error="boom", steps=0, equity=None, attempts=3)
    runs = s.recent_runs()
    assert len(runs) == 2
    assert runs[0]["status"] == "failed"   # id DESC (최근 먼저)
    assert runs[1]["status"] == "ok"
    assert s.last_run()["status"] == "failed"
    assert s.last_success()["target"] == "2024-01-02"


def test_limit(tmp_path):
    s = SqliteSchedulerStore(tmp_path / "p.db")
    for _ in range(5):
        _rec(s)
    assert len(s.recent_runs(limit=3)) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scheduler_store.py -q`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write `ohmystock/scheduler_store.py`**

```python
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Protocol

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scheduler_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT, status TEXT, reason TEXT, target TEXT,
  steps INTEGER, equity REAL, attempts INTEGER, error TEXT
);
"""


class SchedulerStore(Protocol):
    def record_run(self, *, ts: str, status: str, reason: str,
                   target: str | None, steps: int, equity: float | None,
                   attempts: int, error: str | None) -> None: ...
    def recent_runs(self, limit: int = 20) -> list[dict]: ...
    def last_run(self) -> dict | None: ...
    def last_success(self) -> dict | None: ...


class SqliteSchedulerStore:
    """스케줄러 실행 로그(SQLite). paper.db와 같은 파일을 공유하되 테이블이 다름."""

    def __init__(self, db_path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        return conn

    def record_run(self, *, ts: str, status: str, reason: str,
                   target: str | None, steps: int, equity: float | None,
                   attempts: int, error: str | None) -> None:
        with closing(self._conn()) as conn, conn:
            conn.execute(
                "INSERT INTO scheduler_runs "
                "(ts, status, reason, target, steps, equity, attempts, error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (ts, status, reason, target, steps, equity, attempts, error),
            )

    def recent_runs(self, limit: int = 20) -> list[dict]:
        with closing(self._conn()) as conn:
            rows = conn.execute(
                "SELECT * FROM scheduler_runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def last_run(self) -> dict | None:
        with closing(self._conn()) as conn:
            row = conn.execute(
                "SELECT * FROM scheduler_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row is not None else None

    def last_success(self) -> dict | None:
        with closing(self._conn()) as conn:
            row = conn.execute(
                "SELECT * FROM scheduler_runs WHERE status = 'ok' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row is not None else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_scheduler_store.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add ohmystock/scheduler_store.py tests/test_scheduler_store.py
git commit -m "feat: add SqliteSchedulerStore (scheduler_runs log)"
```

---

## Task 2: run_scheduled (재시도·백오프 + 기록)

**Files:** Modify `ohmystock/scheduler.py`; Test `tests/test_run_scheduled.py`

**Interfaces:**
- Consumes: `run_once` (모듈 내), `SchedulerStore.record_run` (Task 1).
- Produces: `run_scheduled(service, calendar, store, now, *, max_attempts=3, base_delay=5.0, factor=2.0, sleep=time.sleep) -> dict` (run_once 결과 + `status`("ok"/"skipped")·`attempts`). 전부 실패 시 원 예외 raise(직전 `failed` 기록).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_scheduled.py
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import ohmystock.scheduler as sched

ET = ZoneInfo("America/New_York")
NOW = datetime(2024, 6, 28, 17, 0, tzinfo=ET)


class FakeStore:
    def __init__(self):
        self.records = []

    def record_run(self, **kw):
        self.records.append(kw)


def test_success_records_ok(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr(sched, "run_once", lambda s, c, n: {
        "ran": True, "reason": "전진", "target": "2024-06-28", "steps": 5, "equity": 1100.0})
    res = sched.run_scheduled(None, None, store, NOW)
    assert res["status"] == "ok"
    assert res["attempts"] == 1
    assert len(store.records) == 1
    assert store.records[0]["status"] == "ok"
    assert store.records[0]["steps"] == 5
    assert store.records[0]["ts"] == NOW.isoformat()


def test_skipped_records_skipped(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr(sched, "run_once", lambda s, c, n: {"ran": False, "reason": "계좌 없음"})
    res = sched.run_scheduled(None, None, store, NOW)
    assert res["status"] == "skipped"
    assert store.records[0]["status"] == "skipped"
    assert store.records[0]["target"] is None
    assert store.records[0]["steps"] == 0


def test_retry_then_success(monkeypatch):
    store = FakeStore()
    n = {"i": 0}

    def flaky(s, c, now):
        n["i"] += 1
        if n["i"] < 3:
            raise RuntimeError("transient")
        return {"ran": True, "reason": "전진", "target": "2024-06-28", "steps": 2, "equity": 1.0}

    monkeypatch.setattr(sched, "run_once", flaky)
    slept = []
    res = sched.run_scheduled(None, None, store, NOW, sleep=slept.append)
    assert res["status"] == "ok"
    assert res["attempts"] == 3
    assert slept == [5.0, 10.0]   # base 5 * factor 2^0, 2^1
    assert store.records[0]["attempts"] == 3


def test_all_fail_records_failed_and_raises(monkeypatch):
    store = FakeStore()

    def always_fail(s, c, now):
        raise RuntimeError("down")

    monkeypatch.setattr(sched, "run_once", always_fail)
    slept = []
    with pytest.raises(RuntimeError):
        sched.run_scheduled(None, None, store, NOW, sleep=slept.append)
    assert len(store.records) == 1
    assert store.records[0]["status"] == "failed"
    assert store.records[0]["attempts"] == 3
    assert len(slept) == 2        # max_attempts - 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_run_scheduled.py -q`
Expected: FAIL (AttributeError: module ... has no attribute 'run_scheduled')

- [ ] **Step 3: Modify `ohmystock/scheduler.py`**

Add `import time` near the top (with the other stdlib imports, e.g. right after `import argparse`). Append `run_scheduled` AFTER `run_once` and BEFORE `run_cli`:

```python
def run_scheduled(service, calendar, store, now, *,
                  max_attempts: int = 3, base_delay: float = 5.0,
                  factor: float = 2.0, sleep=time.sleep) -> dict:
    """run_once를 지수 백오프로 재시도하고 결과를 store에 기록. 멱등."""
    attempt = 0
    last_error = None
    result = None
    while attempt < max_attempts:
        attempt += 1
        try:
            result = run_once(service, calendar, now)
            last_error = None
            break
        except Exception as exc:          # 일시적 실패 -> 백오프 후 재시도
            last_error = exc
            if attempt < max_attempts:
                sleep(base_delay * (factor ** (attempt - 1)))

    ts = now.isoformat()
    if last_error is not None:
        store.record_run(ts=ts, status="failed", reason=str(last_error)[:200],
                         target=None, steps=0, equity=None,
                         attempts=attempt, error=repr(last_error))
        raise last_error
    status = "ok" if result["ran"] else "skipped"
    store.record_run(ts=ts, status=status, reason=result["reason"],
                     target=result.get("target"), steps=result.get("steps", 0),
                     equity=result.get("equity"), attempts=attempt, error=None)
    return {**result, "status": status, "attempts": attempt}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_run_scheduled.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add ohmystock/scheduler.py tests/test_run_scheduled.py
git commit -m "feat: add run_scheduled (retry/backoff + run-log recording)"
```

---

## Task 3: CLI (run-once 기록 + history + last-run)

**Files:** Modify `ohmystock/scheduler.py`; Modify `tests/test_scheduler_cli.py`

**Interfaces:**
- Consumes: `run_scheduled` (Task 2), `SqliteSchedulerStore` (Task 1).
- Produces: `run_cli(argv=None, *, service=None, calendar=None, store=None, now=None, sleep=time.sleep)` — `run-once`는 `run_scheduled`로 실행·기록; `history [--limit N]`·`last-run` 추가.

- [ ] **Step 1: Update the failing test**

Replace the body of `tests/test_scheduler_cli.py` ENTIRELY with:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from ohmystock.config import Config
from ohmystock.core.calendar.exchange import us_market_calendar
from ohmystock.paper.service import PaperService
from ohmystock.paper.sqlite_store import SqlitePaperStore
from ohmystock.scheduler import run_cli
from ohmystock.scheduler_store import SqliteSchedulerStore

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


def _svc(tmp_path):
    svc = PaperService(SqlitePaperStore(tmp_path / "p.db"), FakeAdapter(), Config())
    svc.init_account("MACrossover", {"short": 3, "long": 10}, ["AAPL"],
                     1_000_000, "2024-06-03", "2024-06-28")
    return svc


def test_run_once_records(tmp_path, capsys):
    store = SqliteSchedulerStore(tmp_path / "p.db")
    res = run_cli(["run-once"], service=_svc(tmp_path), calendar=us_market_calendar(),
                  store=store, now=datetime(2024, 6, 28, 17, 0, tzinfo=ET))
    assert res["status"] == "ok"
    assert "ran" in capsys.readouterr().out
    assert store.last_run()["status"] == "ok"   # 실행이 기록됨


def test_history_and_last_run(tmp_path, capsys):
    store = SqliteSchedulerStore(tmp_path / "p.db")
    run_cli(["run-once"], service=_svc(tmp_path), calendar=us_market_calendar(),
            store=store, now=datetime(2024, 6, 28, 17, 0, tzinfo=ET))
    hist = run_cli(["history", "--limit", "5"], store=store)
    assert isinstance(hist, list) and len(hist) == 1
    last = run_cli(["last-run"], store=store)
    assert last["last_run"]["status"] == "ok"
    assert last["last_success"]["status"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scheduler_cli.py -q`
Expected: FAIL (run_cli has no `store` kwarg / no `history` subcommand)

- [ ] **Step 3: Modify `ohmystock/scheduler.py`**

Add to imports (with the other `from ohmystock...` imports): `from ohmystock.scheduler_store import SqliteSchedulerStore`.

Replace the ENTIRE existing `run_cli` function with:

```python
def run_cli(argv=None, *, service=None, calendar=None, store=None, now=None, sleep=time.sleep):
    parser = argparse.ArgumentParser(prog="ohmystock.scheduler")
    parser.add_argument("--db", default=DEFAULT_DB)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run-once")
    p_hist = sub.add_parser("history")
    p_hist.add_argument("--limit", type=int, default=20)
    sub.add_parser("last-run")
    args = parser.parse_args(argv)

    if store is None:
        store = SqliteSchedulerStore(args.db)

    if args.cmd == "run-once":
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
        result = run_scheduled(service, calendar, store, now, sleep=sleep)
        print(result)
        return result

    if args.cmd == "history":
        runs = store.recent_runs(args.limit)
        for run in runs:
            print(run)
        return runs

    # last-run
    out = {"last_run": store.last_run(), "last_success": store.last_success()}
    print(out)
    return out
```

(Keep `main()` and the `if __name__ == "__main__"` block unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_scheduler_cli.py -q`
Then full suite: `uv run pytest -q`
Expected: PASS (전체).

- [ ] **Step 5: Commit**

```bash
git add ohmystock/scheduler.py tests/test_scheduler_cli.py
git commit -m "feat: scheduler CLI records runs + history/last-run subcommands"
```

---

## Task 4: API (/api/scheduler/runs)

**Files:** Modify `server/app.py`; Test `tests/test_scheduler_api.py`

**Interfaces:**
- Consumes: `SqliteSchedulerStore.recent_runs` (Task 1).
- Produces: `GET /api/scheduler/runs?limit=20` → `{"runs": [...]}` (limit 1~200 클램프).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scheduler_api.py
from fastapi.testclient import TestClient
from server.app import create_app
from ohmystock.scheduler_store import SqliteSchedulerStore


class FakeAdapter:
    def get_daily_bars(self, symbols, start, end):
        return {}


def test_runs_empty(tmp_path):
    c = TestClient(create_app(adapter=FakeAdapter(), paper_db=str(tmp_path / "p.db")))
    r = c.get("/api/scheduler/runs")
    assert r.status_code == 200
    assert r.json() == {"runs": []}


def test_runs_after_record(tmp_path):
    db = str(tmp_path / "p.db")
    SqliteSchedulerStore(db).record_run(
        ts="2024-01-01T00:00:00", status="ok", reason="전진",
        target="2024-01-01", steps=1, equity=1.0, attempts=1, error=None)
    c = TestClient(create_app(adapter=FakeAdapter(), paper_db=db))
    r = c.get("/api/scheduler/runs?limit=5")
    assert r.status_code == 200
    runs = r.json()["runs"]
    assert len(runs) == 1 and runs[0]["status"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scheduler_api.py -q`
Expected: FAIL (404).

- [ ] **Step 3: Modify `server/app.py`**

Add import near the top: `from ohmystock.scheduler_store import SqliteSchedulerStore`.

Add this endpoint inside `create_app`, before `return app`:
```python
    @app.get("/api/scheduler/runs")
    def scheduler_runs(limit: int = 20):
        limit = max(1, min(limit, 200))
        store = SqliteSchedulerStore(app.state.paper_db)
        return {"runs": store.recent_runs(limit)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_scheduler_api.py -q`
Then full suite: `uv run pytest -q`
Expected: PASS (전체).

- [ ] **Step 5: Commit**

```bash
git add server/app.py tests/test_scheduler_api.py
git commit -m "feat: add GET /api/scheduler/runs (recent run log)"
```

---

## Task 5: 대시보드 실행 내역 패널

**Files:** Modify `web/src/api.ts`, `web/src/App.tsx`, `web/src/App.css`; Create `web/src/components/SchedulerRunsPanel.tsx`

API 계약: `GET /api/scheduler/runs?limit=N` → `{runs:[{id,ts,status,reason,target,steps,equity,attempts,error}]}`. `status` ∈ "ok"|"skipped"|"failed".

- [ ] **Step 1: api.ts — 타입 + 클라이언트**

```ts
export interface SchedulerRun {
  id: number
  ts: string
  status: string
  reason: string
  target: string | null
  steps: number
  equity: number | null
  attempts: number
  error: string | null
}
export async function getSchedulerRuns(limit = 20): Promise<SchedulerRun[]> {
  const r = await fetch(`/api/scheduler/runs?limit=${limit}`)
  if (!r.ok) throw new Error((await r.json()).detail ?? '실행 내역 조회 실패')
  return (await r.json()).runs
}
```

- [ ] **Step 2: Create `web/src/components/SchedulerRunsPanel.tsx`**

A `.card` component (no props):
- State: `runs: SchedulerRun[] | null`, `error: string | null`. useEffect on mount → `getSchedulerRuns(20)` → setRuns (try/catch → setError).
- Title "스케줄러 실행 내역".
- If `runs === null && !error`: "불러오는 중…". If `runs` empty: "실행 기록 없음".
- Else a `.orders-table` with columns 시각 / 상태 / target / steps / 시도 / 사유. The 상태 cell uses a colored span: status==="ok" → `.run-ok`(green), "failed" → `.run-failed`(red), else `.run-skipped`(dim). The 사유 cell shows `error ?? reason`. Truncate ts to `ts.replace('T',' ').slice(0,16)`.
- Show `error` (dim red) if set. TS strict-clean (no `any`).

- [ ] **Step 3: Wire into `App.tsx`**

Import `SchedulerRunsPanel`, render `<SchedulerRunsPanel />` in the main panel area (near CalendarPanel / PaperPanel). Self-contained; render always.

- [ ] **Step 4: App.css — status styles**

Add (reuse theme vars): `.run-ok { color: var(--pass); font-weight:600; }`, `.run-failed { color: var(--fail); font-weight:600; }`, `.run-skipped { color: var(--text-dim); }`. Reuse `.orders-table` for the table.

- [ ] **Step 5: Build**

Run: `cd web && npm run build`
Expected: TypeScript + build pass, no errors.

- [ ] **Step 6: Commit**

```bash
git add web/src
git commit -m "feat(web): add scheduler run-history panel"
```

---

## Task 6: 스모크 + 머지

- [ ] **Step 1: 전체 테스트**

Run: `uv run pytest -q`
Expected: 전체 PASS.

- [ ] **Step 2: 실데이터 스모크 (네트워크)**

```bash
rm -f .cache/AAPL.parquet .cache/MSFT.parquet
uv run python -m ohmystock.paper --db state/sl.db init --strategy Momentum --symbols AAPL,MSFT --capital 5000000 --start 2024-01-01 --end 2024-12-31
uv run python -m ohmystock.scheduler --db state/sl.db run-once
uv run python -m ohmystock.scheduler --db state/sl.db history --limit 5
uv run python -m ohmystock.scheduler --db state/sl.db last-run
rm -f state/sl.db
```
Expected: run-once `{'status':'ok'/'skipped', ...}`; history가 그 실행 1줄 출력; last-run에 last_run/last_success.

- [ ] **Step 3: 웹 빌드**

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
- §2 SqliteSchedulerStore(record/recent/last-run/last-success) → Task 1 ✓
- §3 run_scheduled(재시도·백오프·status 매핑·기록·재발생) → Task 2 ✓
- §4 CLI(run-once 기록·history·last-run, 주입) → Task 3 ✓
- §5 API(/api/scheduler/runs, 클램프) → Task 4 ✓
- §6 대시보드 패널 → Task 5 ✓
- §7 에러(재시도 대상=예외, 스킵 제외, 전부실패 재발생) → Task 2 + test_all_fail ✓
- §8 테스트(store/run_scheduled/CLI/API/프론트) → 각 Task ✓

**플레이스홀더:** 완전한 코드. 검증된 시그니처(run_once/PaperService/create_app).

**타입 일관성:**
- `record_run(*, ts,status,reason,target,steps,equity,attempts,error)` — Task 1 정의 ↔ Task 2 호출 ↔ Task 2 FakeStore ↔ Task 4 test 일치 ✓
- `run_scheduled(service,calendar,store,now,*,...) -> dict(+status,attempts)` — Task 2 ↔ Task 3 run_cli 일치 ✓
- `recent_runs(limit) -> list[dict]` — Task 1 ↔ Task 3 history ↔ Task 4 API ↔ Task 5 프론트 일치 ✓
- 백오프 수열 `base_delay*factor^(attempt-1)` = 5,10 (2회) — Task 2 test_retry_then_success로 고정 ✓

**검증된 사실:** run_once는 멱등(커서 전진만)이라 재시도 안전. `run_once`를 monkeypatch해 run_scheduled 단위 격리. CLI `run-once`는 이제 store가 필요 → 기존 test_scheduler_cli를 store 주입으로 교체(state/ 부작용 방지).
