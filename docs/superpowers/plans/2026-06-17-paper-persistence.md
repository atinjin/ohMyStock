# 페이퍼 트레이딩 상태 영속화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 모의 계좌를 정해진 캘린더를 따라 하루씩 전진시키며 보유·현금·자산곡선·거래를 SQLite에 영속하고, CLI와 대시보드로 운용·조회한다.

**Architecture:** `ohmystock/paper/` 새 패키지. `PaperStore` 인터페이스(SQLite 구현) + `engine.step`(기존 `rebalance`/`PaperBroker`/`RiskGuard` 재사용) + `PaperService`(묶음). CLI(`python -m ohmystock.paper`)와 `/api/paper/*` + 대시보드 패널. 완전 결정적·오프라인 테스트.

**Tech Stack:** Python 3.11, stdlib `sqlite3`, pandas, FastAPI, React/Vite.

---

## File Structure

| 파일 | 책임 |
|------|------|
| `ohmystock/paper/__init__.py` | 패키지 |
| `ohmystock/paper/account.py` | `PaperAccount` DTO |
| `ohmystock/paper/store.py` | `PaperStore` Protocol |
| `ohmystock/paper/sqlite_store.py` | `SqlitePaperStore` |
| `ohmystock/paper/engine.py` | `close_panel`/`next_trading_day`/`step` |
| `ohmystock/paper/service.py` | `PaperService` (init/step/run/get_state/get_history) |
| `ohmystock/paper/__main__.py` | CLI |
| `server/app.py` | `/api/paper/*` 엔드포인트 (수정) |
| `web/src/api.ts` | paper API 클라이언트 (수정) |
| `web/src/components/PaperPanel.tsx` | 페이퍼 계좌 패널 |
| `web/src/App.tsx`, `web/src/App.css` | 패널 마운트·스타일 (수정) |

재사용: `core/broker/paper.py::PaperBroker(cash)`(`.cash`,`.shares`,`set_prices`,`get_account`,`get_positions`,`submit_order`), `core/broker/risk.py::RiskGuard(config, peak_equity)`(`update`/`drawdown`/`in_breach`), `core/broker/rebalance.py::rebalance(strategy,bars,broker,risk,config)`(제출 주문 list[Order] 반환), `report.py::build_strategy(name,params)`, `core/broker/base.py::Order(symbol,side,notional)`.

---

## Task 0: 패키지 + gitignore

**Files:** Create `ohmystock/paper/__init__.py`; Modify `.gitignore`

- [ ] **Step 1: 패키지 디렉토리**

Run:
```bash
cd /Users/atinjin/repository/OhMyStock
mkdir -p ohmystock/paper
touch ohmystock/paper/__init__.py
grep -q "^state/" .gitignore || printf 'state/\n' >> .gitignore
```

- [ ] **Step 2: Commit**

```bash
git add ohmystock/paper/__init__.py .gitignore
git commit -m "chore: add paper package and gitignore state/"
```

---

## Task 1: PaperAccount + PaperStore 인터페이스

**Files:** Create `ohmystock/paper/account.py`, `ohmystock/paper/store.py`; Test `tests/test_paper_account.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_paper_account.py
from ohmystock.paper.account import PaperAccount

def test_paper_account_fields():
    a = PaperAccount(
        strategy="Momentum", params={"top_k": 3}, symbols=["AAPL", "MSFT"],
        initial_capital=1_000_000, start_date="2024-01-01", end_date="2024-06-30",
        cursor_date=None, cash=1_000_000, peak_equity=1_000_000)
    assert a.symbols == ["AAPL", "MSFT"]
    assert a.cursor_date is None
    assert a.cash == 1_000_000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_paper_account.py -q`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write minimal implementation**

```python
# ohmystock/paper/account.py
from dataclasses import dataclass


@dataclass
class PaperAccount:
    """페이퍼 계좌 설정 + 현재 상태."""
    strategy: str
    params: dict
    symbols: list[str]
    initial_capital: float
    start_date: str
    end_date: str
    cursor_date: str | None
    cash: float
    peak_equity: float
```

```python
# ohmystock/paper/store.py
from typing import Protocol
from ohmystock.paper.account import PaperAccount


class PaperStore(Protocol):
    """페이퍼 계좌 영속 저장소. SQLite 등으로 구현."""
    def initialize(self, account: PaperAccount) -> None: ...
    def load_account(self) -> PaperAccount | None: ...
    def save_account(self, account: PaperAccount) -> None: ...
    def load_positions(self) -> dict[str, float]: ...
    def save_positions(self, shares: dict[str, float]) -> None: ...
    def append_snapshot(self, date: str, equity: float, cash: float) -> None: ...
    def append_trades(self, date: str, orders: list[dict]) -> None: ...
    def snapshots(self) -> list[dict]: ...
    def trades(self) -> list[dict]: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_paper_account.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add ohmystock/paper/account.py ohmystock/paper/store.py tests/test_paper_account.py
git commit -m "feat: add PaperAccount DTO and PaperStore protocol"
```

---

## Task 2: SqlitePaperStore

**Files:** Create `ohmystock/paper/sqlite_store.py`; Test `tests/test_paper_sqlite_store.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_paper_sqlite_store.py
from ohmystock.paper.account import PaperAccount
from ohmystock.paper.sqlite_store import SqlitePaperStore


def _account():
    return PaperAccount(
        strategy="Momentum", params={"top_k": 2}, symbols=["AAPL", "MSFT"],
        initial_capital=1_000_000, start_date="2024-01-01", end_date="2024-06-30",
        cursor_date=None, cash=1_000_000, peak_equity=1_000_000)


def test_initialize_and_load(tmp_path):
    store = SqlitePaperStore(tmp_path / "p.db")
    assert store.load_account() is None
    store.initialize(_account())
    a = store.load_account()
    assert a is not None
    assert a.strategy == "Momentum"
    assert a.params == {"top_k": 2}
    assert a.symbols == ["AAPL", "MSFT"]
    assert a.cash == 1_000_000


def test_save_account_and_positions(tmp_path):
    store = SqlitePaperStore(tmp_path / "p.db")
    store.initialize(_account())
    a = store.load_account()
    a.cursor_date = "2024-01-03"
    a.cash = 500_000
    a.peak_equity = 1_100_000
    store.save_account(a)
    store.save_positions({"AAPL": 10.0, "MSFT": 0.0})
    a2 = store.load_account()
    assert a2.cursor_date == "2024-01-03"
    assert a2.cash == 500_000
    assert store.load_positions() == {"AAPL": 10.0}  # 0 주는 저장 안 함


def test_snapshots_and_trades(tmp_path):
    store = SqlitePaperStore(tmp_path / "p.db")
    store.initialize(_account())
    store.append_snapshot("2024-01-02", 1_000_000, 1_000_000)
    store.append_snapshot("2024-01-03", 1_010_000, 400_000)
    store.append_trades("2024-01-03", [
        {"symbol": "AAPL", "side": "buy", "notional": 600_000, "price": 100.0, "shares": 6000.0},
    ])
    snaps = store.snapshots()
    assert [s["date"] for s in snaps] == ["2024-01-02", "2024-01-03"]
    assert snaps[-1]["equity"] == 1_010_000
    trades = store.trades()
    assert len(trades) == 1
    assert trades[0]["side"] == "buy"
    assert trades[0]["symbol"] == "AAPL"


def test_initialize_resets(tmp_path):
    store = SqlitePaperStore(tmp_path / "p.db")
    store.initialize(_account())
    store.append_snapshot("2024-01-02", 1, 1)
    store.initialize(_account())  # reset
    assert store.snapshots() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_paper_sqlite_store.py -q`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write minimal implementation**

```python
# ohmystock/paper/sqlite_store.py
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from ohmystock.paper.account import PaperAccount

_SCHEMA = """
CREATE TABLE IF NOT EXISTS account (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  strategy TEXT, params TEXT, symbols TEXT,
  initial_capital REAL, start_date TEXT, end_date TEXT,
  cursor_date TEXT, cash REAL, peak_equity REAL,
  created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS positions (symbol TEXT PRIMARY KEY, shares REAL);
CREATE TABLE IF NOT EXISTS snapshots (date TEXT PRIMARY KEY, equity REAL, cash REAL);
CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT, symbol TEXT, side TEXT, notional REAL, price REAL, shares REAL
);
"""


class SqlitePaperStore:
    """SQLite 기반 PaperStore 구현 (단일 계좌)."""

    def __init__(self, db_path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self, account: PaperAccount) -> None:
        with closing(self._conn()) as conn, conn:
            conn.executescript(_SCHEMA)
            conn.execute("DELETE FROM account")
            conn.execute("DELETE FROM positions")
            conn.execute("DELETE FROM snapshots")
            conn.execute("DELETE FROM trades")
            conn.execute(
                "INSERT INTO account (id, strategy, params, symbols, initial_capital, "
                "start_date, end_date, cursor_date, cash, peak_equity, created_at, updated_at) "
                "VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
                (account.strategy, json.dumps(account.params), json.dumps(account.symbols),
                 account.initial_capital, account.start_date, account.end_date,
                 account.cursor_date, account.cash, account.peak_equity),
            )

    def load_account(self) -> PaperAccount | None:
        with closing(self._conn()) as conn:
            row = conn.execute("SELECT * FROM account WHERE id = 1").fetchone()
        if row is None:
            return None
        return PaperAccount(
            strategy=row["strategy"], params=json.loads(row["params"]),
            symbols=json.loads(row["symbols"]), initial_capital=row["initial_capital"],
            start_date=row["start_date"], end_date=row["end_date"],
            cursor_date=row["cursor_date"], cash=row["cash"], peak_equity=row["peak_equity"],
        )

    def save_account(self, account: PaperAccount) -> None:
        with closing(self._conn()) as conn, conn:
            conn.execute(
                "UPDATE account SET cursor_date=?, cash=?, peak_equity=?, "
                "updated_at=datetime('now') WHERE id=1",
                (account.cursor_date, account.cash, account.peak_equity),
            )

    def load_positions(self) -> dict[str, float]:
        with closing(self._conn()) as conn:
            rows = conn.execute("SELECT symbol, shares FROM positions").fetchall()
        return {r["symbol"]: r["shares"] for r in rows}

    def save_positions(self, shares: dict[str, float]) -> None:
        with closing(self._conn()) as conn, conn:
            conn.execute("DELETE FROM positions")
            conn.executemany(
                "INSERT INTO positions (symbol, shares) VALUES (?, ?)",
                [(s, q) for s, q in shares.items() if q > 0],
            )

    def append_snapshot(self, date: str, equity: float, cash: float) -> None:
        with closing(self._conn()) as conn, conn:
            conn.execute(
                "INSERT OR REPLACE INTO snapshots (date, equity, cash) VALUES (?, ?, ?)",
                (date, equity, cash),
            )

    def append_trades(self, date: str, orders: list[dict]) -> None:
        with closing(self._conn()) as conn, conn:
            conn.executemany(
                "INSERT INTO trades (date, symbol, side, notional, price, shares) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [(date, o["symbol"], o["side"], o["notional"], o["price"], o["shares"])
                 for o in orders],
            )

    def snapshots(self) -> list[dict]:
        with closing(self._conn()) as conn:
            rows = conn.execute(
                "SELECT date, equity, cash FROM snapshots ORDER BY date").fetchall()
        return [dict(r) for r in rows]

    def trades(self) -> list[dict]:
        with closing(self._conn()) as conn:
            rows = conn.execute(
                "SELECT date, symbol, side, notional, price, shares "
                "FROM trades ORDER BY id").fetchall()
        return [dict(r) for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_paper_sqlite_store.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add ohmystock/paper/sqlite_store.py tests/test_paper_sqlite_store.py
git commit -m "feat: add SqlitePaperStore (account/positions/snapshots/trades)"
```

---

## Task 3: 스텝 엔진

**Files:** Create `ohmystock/paper/engine.py`; Test `tests/test_paper_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_paper_engine.py
import numpy as np
import pandas as pd
from ohmystock.config import Config
from ohmystock.paper.account import PaperAccount
from ohmystock.paper.sqlite_store import SqlitePaperStore
from ohmystock.paper import engine


def _bars(symbols, n=40):
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    out = {}
    for i, s in enumerate(symbols):
        closes = np.linspace(10 + i, 30 + i, n)  # 꾸준한 상승추세
        out[s] = pd.DataFrame(
            {"open": closes, "high": closes, "low": closes,
             "close": closes, "volume": [1e6] * n}, index=idx)
    return out


def _fresh(tmp_path, symbols=("AAPL",)):
    acct = PaperAccount(
        strategy="MACrossover", params={"short": 3, "long": 10},
        symbols=list(symbols), initial_capital=1_000_000,
        start_date="2024-01-01", end_date="2024-03-31",
        cursor_date=None, cash=1_000_000, peak_equity=1_000_000)
    store = SqlitePaperStore(tmp_path / "p.db")
    store.initialize(acct)
    return acct, store


def test_step_advances_cursor_and_records(tmp_path):
    acct, store = _fresh(tmp_path)
    bars = _bars(["AAPL"], 40)
    res = engine.step(acct, store, bars, Config())
    assert res is not None
    assert res["date"] == "2024-01-01"  # 첫 거래일
    loaded = store.load_account()
    assert loaded.cursor_date == "2024-01-01"
    assert len(store.snapshots()) == 1


def test_step_returns_none_when_complete(tmp_path):
    acct, store = _fresh(tmp_path)
    bars = _bars(["AAPL"], 40)
    last = bars["AAPL"].index[-1].strftime("%Y-%m-%d")
    acct.cursor_date = last
    store.save_account(acct)
    assert engine.step(acct, store, bars, Config()) is None


def test_repeated_steps_build_equity_and_trades(tmp_path):
    acct, store = _fresh(tmp_path)
    bars = _bars(["AAPL"], 40)
    # 끝까지 스텝
    for _ in range(60):
        a = store.load_account()
        if engine.step(a, store, bars, Config()) is None:
            break
    snaps = store.snapshots()
    assert len(snaps) >= 30          # 거래일 수만큼 스냅샷
    assert store.load_account().cursor_date == bars["AAPL"].index[-1].strftime("%Y-%m-%d")
    # 상승추세 -> MA교차가 매수 -> 거래 발생 & 자산 증가
    assert len(store.trades()) >= 1
    assert snaps[-1]["equity"] > 1_000_000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_paper_engine.py -q`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write minimal implementation**

```python
# ohmystock/paper/engine.py
import pandas as pd

from ohmystock.core.broker.paper import PaperBroker
from ohmystock.core.broker.risk import RiskGuard
from ohmystock.core.broker.rebalance import rebalance
from ohmystock.report import build_strategy


def close_panel(bars: dict, start: str, end: str) -> pd.DataFrame:
    """종가 패널: 거래일 합집합 인덱스로 정렬·ffill, [start,end]로 한정."""
    closes = pd.DataFrame({sym: df["close"] for sym, df in bars.items()})
    closes = closes.sort_index().ffill()
    mask = (closes.index >= pd.Timestamp(start)) & (closes.index <= pd.Timestamp(end))
    return closes[mask]


def next_trading_day(index: pd.DatetimeIndex, cursor_date):
    """cursor 다음 거래일. cursor None이면 첫 날, 더 없으면 None."""
    if len(index) == 0:
        return None
    if cursor_date is None:
        return index[0]
    after = index[index > pd.Timestamp(cursor_date)]
    return None if len(after) == 0 else after[0]


def step(account, store, bars: dict, config):
    """커서를 다음 거래일로 전진해 리밸런싱·기록. 결과 dict 또는 완료 시 None."""
    panel = close_panel(bars, account.start_date, account.end_date)
    d = next_trading_day(panel.index, account.cursor_date)
    if d is None:
        return None

    sliced = {sym: df[df.index <= d] for sym, df in bars.items()}
    broker = PaperBroker(cash=account.cash)
    broker.shares = dict(store.load_positions())
    prices = {
        sym: float(panel.loc[d, sym])
        for sym in panel.columns
        if pd.notna(panel.loc[d, sym])
    }
    broker.set_prices(prices)

    strategy = build_strategy(account.strategy, account.params)
    risk = RiskGuard(config, peak_equity=account.peak_equity)
    orders = rebalance(strategy, sliced, broker, risk, config)

    acct = broker.get_account()
    equity = acct.equity
    date_str = d.strftime("%Y-%m-%d")
    order_rows = [
        {
            "symbol": o.symbol, "side": o.side, "notional": round(o.notional, 2),
            "price": prices.get(o.symbol, 0.0),
            "shares": (o.notional / prices[o.symbol]) if o.symbol in prices else 0.0,
        }
        for o in orders
    ]

    account.cursor_date = date_str
    account.cash = acct.cash
    account.peak_equity = max(account.peak_equity, equity)
    store.save_positions(broker.shares)
    store.append_snapshot(date_str, equity, acct.cash)
    store.append_trades(date_str, order_rows)
    store.save_account(account)

    return {
        "date": date_str, "equity": equity, "cash": acct.cash,
        "orders": order_rows,
        "in_breach": bool(risk.in_breach(equity)),
        "drawdown": float(risk.drawdown(equity)),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_paper_engine.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add ohmystock/paper/engine.py tests/test_paper_engine.py
git commit -m "feat: add paper step engine (calendar cursor, rebalance, record)"
```

---

## Task 4: PaperService

**Files:** Create `ohmystock/paper/service.py`; Test `tests/test_paper_service.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_paper_service.py
import numpy as np
import pandas as pd
import pytest
from datetime import date
from ohmystock.config import Config
from ohmystock.paper.sqlite_store import SqlitePaperStore
from ohmystock.paper.service import PaperService


class FakeAdapter:
    def __init__(self, n=40):
        self.n = n

    def get_daily_bars(self, symbols, start, end):
        idx = pd.date_range("2024-01-01", periods=self.n, freq="B")
        out = {}
        for i, s in enumerate(symbols):
            closes = np.linspace(10 + i, 30 + i, self.n)
            out[s] = pd.DataFrame(
                {"open": closes, "high": closes, "low": closes,
                 "close": closes, "volume": [1e6] * self.n}, index=idx)
        return out


def _service(tmp_path):
    store = SqlitePaperStore(tmp_path / "p.db")
    return PaperService(store, FakeAdapter(40), Config())


def test_state_when_uninitialized(tmp_path):
    svc = _service(tmp_path)
    assert svc.get_state() == {"exists": False}


def test_init_then_step(tmp_path):
    svc = _service(tmp_path)
    svc.init_account("MACrossover", {"short": 3, "long": 10}, ["AAPL"],
                     1_000_000, "2024-01-01", "2024-03-31")
    res = svc.step()
    assert res is not None
    state = svc.get_state()
    assert state["exists"] is True
    assert state["cursor_date"] == "2024-01-01"


def test_run_to_end(tmp_path):
    svc = _service(tmp_path)
    svc.init_account("MACrossover", {"short": 3, "long": 10}, ["AAPL"],
                     1_000_000, "2024-01-01", "2024-03-31")
    results = svc.run()
    assert len(results) >= 30
    hist = svc.get_history()
    assert len(hist["snapshots"]) == len(results)
    assert svc.get_state()["equity"] > 1_000_000


def test_step_without_account_raises(tmp_path):
    svc = _service(tmp_path)
    with pytest.raises(ValueError):
        svc.step()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_paper_service.py -q`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write minimal implementation**

```python
# ohmystock/paper/service.py
from datetime import date

from ohmystock.config import Config
from ohmystock.paper.account import PaperAccount
from ohmystock.paper import engine


class PaperService:
    """페이퍼 계좌 운용 묶음: store + 데이터 어댑터 + 엔진."""

    def __init__(self, store, adapter, config=None):
        self.store = store
        self.adapter = adapter
        self.config = config or Config()

    def init_account(self, strategy, params, symbols, capital, start, end) -> PaperAccount:
        account = PaperAccount(
            strategy=strategy, params=dict(params or {}), symbols=list(symbols),
            initial_capital=capital, start_date=start, end_date=end,
            cursor_date=None, cash=capital, peak_equity=capital)
        self.store.initialize(account)
        return account

    def _bars(self, account: PaperAccount) -> dict:
        return self.adapter.get_daily_bars(
            account.symbols,
            date.fromisoformat(account.start_date),
            date.fromisoformat(account.end_date))

    def step(self):
        account = self.store.load_account()
        if account is None:
            raise ValueError("페이퍼 계좌가 없습니다. 먼저 init 하세요.")
        return engine.step(account, self.store, self._bars(account), self.config)

    def run(self, steps=None, to=None) -> list[dict]:
        results: list[dict] = []
        while True:
            account = self.store.load_account()
            if account is None:
                raise ValueError("페이퍼 계좌가 없습니다. 먼저 init 하세요.")
            res = engine.step(account, self.store, self._bars(account), self.config)
            if res is None:
                break
            results.append(res)
            if steps is not None and len(results) >= steps:
                break
            if to is not None and res["date"] >= to:
                break
        return results

    def get_state(self) -> dict:
        account = self.store.load_account()
        if account is None:
            return {"exists": False}
        positions = self.store.load_positions()
        snaps = self.store.snapshots()
        equity = snaps[-1]["equity"] if snaps else account.cash
        drawdown = (
            0.0 if account.peak_equity <= 0
            else max(0.0, (account.peak_equity - equity) / account.peak_equity)
        )
        return {
            "exists": True,
            "config": {
                "strategy": account.strategy, "params": account.params,
                "symbols": account.symbols, "initial_capital": account.initial_capital,
                "start": account.start_date, "end": account.end_date,
            },
            "cursor_date": account.cursor_date,
            "cash": account.cash, "equity": equity, "peak_equity": account.peak_equity,
            "positions": [{"symbol": s, "shares": q} for s, q in positions.items()],
            "in_breach": bool(drawdown > self.config.mdd_limit),
            "drawdown": float(drawdown),
        }

    def get_history(self) -> dict:
        return {"snapshots": self.store.snapshots(), "trades": self.store.trades()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_paper_service.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add ohmystock/paper/service.py tests/test_paper_service.py
git commit -m "feat: add PaperService (init/step/run/get_state/get_history)"
```

---

## Task 5: CLI

**Files:** Create `ohmystock/paper/__main__.py`; Test `tests/test_paper_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_paper_cli.py
import numpy as np
import pandas as pd
from ohmystock.paper.__main__ import build_parser, run_cli


class FakeAdapter:
    def get_daily_bars(self, symbols, start, end):
        idx = pd.date_range("2024-01-01", periods=40, freq="B")
        out = {}
        for i, s in enumerate(symbols):
            closes = np.linspace(10 + i, 30 + i, 40)
            out[s] = pd.DataFrame(
                {"open": closes, "high": closes, "low": closes,
                 "close": closes, "volume": [1e6] * 40}, index=idx)
        return out


def test_cli_init_step_status(tmp_path, capsys):
    db = str(tmp_path / "p.db")
    adapter = FakeAdapter()
    run_cli(["--db", db, "init", "--strategy", "MACrossover",
             "--symbols", "AAPL", "--capital", "1000000",
             "--start", "2024-01-01", "--end", "2024-03-31"], adapter=adapter)
    run_cli(["--db", db, "step"], adapter=adapter)
    run_cli(["--db", db, "status"], adapter=adapter)
    out = capsys.readouterr().out
    assert "초기화" in out
    assert "2024-01-01" in out  # status가 커서 출력
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_paper_cli.py -q`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write minimal implementation**

```python
# ohmystock/paper/__main__.py
import argparse

from ohmystock.config import Config
from ohmystock.core.data.cache import ParquetCache
from ohmystock.core.data.yfinance_adapter import YFinanceAdapter
from ohmystock.paper.service import PaperService
from ohmystock.paper.sqlite_store import SqlitePaperStore

DEFAULT_DB = "state/paper.db"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ohmystock.paper")
    p.add_argument("--db", default=DEFAULT_DB)
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init")
    pi.add_argument("--strategy", required=True)
    pi.add_argument("--symbols", required=True, help="쉼표 구분")
    pi.add_argument("--capital", type=float, default=5_000_000)
    pi.add_argument("--start", required=True)
    pi.add_argument("--end", required=True)

    sub.add_parser("step")
    pr = sub.add_parser("run")
    pr.add_argument("--steps", type=int, default=None)
    pr.add_argument("--to", default=None)
    sub.add_parser("status")
    return p


def run_cli(argv=None, adapter=None) -> None:
    args = build_parser().parse_args(argv)
    if adapter is None:
        adapter = YFinanceAdapter(cache=ParquetCache(".cache"))
    svc = PaperService(SqlitePaperStore(args.db), adapter, Config())

    if args.cmd == "init":
        svc.init_account(args.strategy, {}, args.symbols.split(","),
                         args.capital, args.start, args.end)
        print("초기화 완료")
    elif args.cmd == "step":
        res = svc.step()
        print("완료(더 진행할 거래일 없음)" if res is None else res)
    elif args.cmd == "run":
        results = svc.run(steps=args.steps, to=args.to)
        print(f"{len(results)} 스텝 진행")
    elif args.cmd == "status":
        print(svc.get_state())


def main() -> None:
    run_cli()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_paper_cli.py -q`
Expected: PASS (1 passed)

Note: import path `ohmystock.paper.__main__` works because the test imports the module directly; `python -m ohmystock.paper` calls `main()`.

- [ ] **Step 5: Commit**

```bash
git add ohmystock/paper/__main__.py tests/test_paper_cli.py
git commit -m "feat: add paper CLI (init/step/run/status)"
```

---

## Task 6: API 엔드포인트

**Files:** Modify `server/app.py`; Test `tests/test_paper_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_paper_api.py
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from server.app import create_app


class FakeAdapter:
    def get_daily_bars(self, symbols, start, end):
        idx = pd.date_range("2024-01-01", periods=40, freq="B")
        out = {}
        for i, s in enumerate(symbols):
            closes = np.linspace(10 + i, 30 + i, 40)
            out[s] = pd.DataFrame(
                {"open": closes, "high": closes, "low": closes,
                 "close": closes, "volume": [1e6] * 40}, index=idx)
        return out


def _client(tmp_path):
    return TestClient(create_app(adapter=FakeAdapter(),
                                 paper_db=str(tmp_path / "p.db")))


def test_paper_state_uninitialized(tmp_path):
    resp = _client(tmp_path).get("/api/paper/state")
    assert resp.status_code == 200
    assert resp.json() == {"exists": False}


def test_paper_init_step_history(tmp_path):
    c = _client(tmp_path)
    body = {"strategy": "MACrossover", "params": {"short": 3, "long": 10},
            "symbols": ["AAPL"], "start": "2024-01-01", "end": "2024-03-31",
            "capital": 1_000_000}
    r = c.post("/api/paper/init", json=body)
    assert r.status_code == 200
    assert r.json()["exists"] is True

    s = c.post("/api/paper/step")
    assert s.status_code == 200
    assert s.json()["date"] == "2024-01-01"

    run = c.post("/api/paper/run", json={})
    assert run.status_code == 200
    assert isinstance(run.json()["results"], list)

    hist = c.get("/api/paper/history")
    assert hist.status_code == 200
    assert len(hist.json()["snapshots"]) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_paper_api.py -q`
Expected: FAIL (TypeError: create_app() got unexpected keyword 'paper_db')

- [ ] **Step 3: Modify `server/app.py`**

Add imports near the top (after existing imports):

```python
from pydantic import BaseModel
from ohmystock.paper.service import PaperService
from ohmystock.paper.sqlite_store import SqlitePaperStore
```

Add a request model next to `BacktestRequest`:

```python
class RunRequest(BaseModel):
    steps: int | None = None
    to: str | None = None
```

Change the `create_app` signature and store the db path on app.state:

```python
def create_app(adapter=None, paper_db="state/paper.db") -> FastAPI:
    if adapter is None:
        adapter = YFinanceAdapter(cache=ParquetCache(".cache"))

    app = FastAPI(title="OhMyStock API")
    app.state.adapter = adapter
    app.state.paper_db = paper_db
```

Add these endpoints inside `create_app` (before `return app`):

```python
    def _paper_service() -> PaperService:
        return PaperService(SqlitePaperStore(app.state.paper_db), app.state.adapter, Config())

    @app.post("/api/paper/init")
    def paper_init(req: BacktestRequest):
        try:
            date.fromisoformat(req.start)
            date.fromisoformat(req.end)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        svc = _paper_service()
        svc.init_account(req.strategy, req.params, req.symbols, req.capital,
                         req.start, req.end)
        return svc.get_state()

    @app.post("/api/paper/step")
    def paper_step():
        try:
            res = _paper_service().step()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return res if res is not None else {"done": True}

    @app.post("/api/paper/run")
    def paper_run(req: RunRequest):
        try:
            results = _paper_service().run(steps=req.steps, to=req.to)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"results": results}

    @app.get("/api/paper/state")
    def paper_state():
        return _paper_service().get_state()

    @app.get("/api/paper/history")
    def paper_history():
        return _paper_service().get_history()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_paper_api.py -q`
Then full suite: `uv run pytest -q`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add server/app.py tests/test_paper_api.py
git commit -m "feat: add /api/paper endpoints (init/step/run/state/history)"
```

---

## Task 7: 대시보드 페이퍼 계좌 패널

**Files:** Modify `web/src/api.ts`, `web/src/App.tsx`, `web/src/App.css`; Create `web/src/components/PaperPanel.tsx`

API 계약 (Task 6):
- `GET /api/paper/state` → `{exists:false}` 또는 `{exists:true, config, cursor_date, cash, equity, peak_equity, positions:[{symbol,shares}], in_breach, drawdown}`
- `POST /api/paper/init` body `{strategy, params, symbols, start, end, capital}` → state
- `POST /api/paper/step` → step 결과 `{date, equity, cash, orders, in_breach, drawdown}` 또는 `{done:true}`
- `POST /api/paper/run` body `{steps?, to?}` → `{results:[...]}`
- `GET /api/paper/history` → `{snapshots:[{date,equity,cash}], trades:[{date,symbol,side,notional,price,shares}]}`

- [ ] **Step 1: api.ts — 타입 + 클라이언트 함수 추가**

Add interfaces and functions (mirror existing `runBacktest` fetch/error handling, reuse the existing error parser):

```ts
export interface PaperPosition { symbol: string; shares: number }
export interface PaperState {
  exists: boolean
  config?: { strategy: string; params: Record<string, ParamValue>; symbols: string[]; initial_capital: number; start: string; end: string }
  cursor_date?: string | null
  cash?: number
  equity?: number
  peak_equity?: number
  positions?: PaperPosition[]
  in_breach?: boolean
  drawdown?: number
}
export interface PaperHistory {
  snapshots: { date: string; equity: number; cash: number }[]
  trades: { date: string; symbol: string; side: string; notional: number; price: number; shares: number }[]
}

export function getPaperState(): Promise<PaperState> {
  return fetch('/api/paper/state').then((r) => r.json())
}
export function getPaperHistory(): Promise<PaperHistory> {
  return fetch('/api/paper/history').then((r) => r.json())
}
export async function initPaper(req: BacktestRequest): Promise<PaperState> {
  const r = await fetch('/api/paper/init', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(req),
  })
  if (!r.ok) throw new Error((await r.json()).detail ?? '초기화 실패')
  return r.json()
}
export async function stepPaper(): Promise<{ done?: boolean; date?: string }> {
  const r = await fetch('/api/paper/step', { method: 'POST' })
  if (!r.ok) throw new Error((await r.json()).detail ?? '스텝 실패')
  return r.json()
}
export async function runPaper(body: { steps?: number; to?: string }): Promise<{ results: unknown[] }> {
  const r = await fetch('/api/paper/run', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error((await r.json()).detail ?? '실행 실패')
  return r.json()
}
```

- [ ] **Step 2: Create `web/src/components/PaperPanel.tsx`**

A card component that:
- Props: `{ request: BacktestRequest | null }` (the current form-built request, used for 초기화).
- On mount and after each action, calls `getPaperState()` + `getPaperHistory()` and stores them in state.
- If `state.exists` is false: show "페이퍼 계좌 없음" + a "현재 설정으로 초기화" button (disabled if `request` is null) that calls `initPaper(request)` then refreshes.
- If exists: show
  - config summary (전략/종목/기간/커서 날짜)
  - 자본 cards: 현재 자산(equity), 현금(cash), 고점(peak_equity) — format with the existing `withCommas` and append `원` (reuse `web/src/format.ts`).
  - a risk badge (in_breach ? "MDD 한도 위반" red : "정상" green) showing drawdown %.
  - the equity curve via the existing `EquityChart` — map `history.snapshots` to `{date, value: equity}` (EquityChart expects `EquityPoint[]` with `date`/`value`).
  - a positions table (종목 / 보유수량 shares to 4 decimals).
  - a trades table (날짜 / 종목 / 구분 buy=green·sell=red / 금액 notional with commas) — show the most recent ~20, newest first.
  - buttons: "한 스텝", "끝까지 빠르게"(calls `runPaper({})`), "초기화"(re-init from `request`). Disable while an action is in flight.
- Keep TS strict-clean (no `any` in public props; internal `unknown` ok). Reuse existing CSS classes where possible (`.card`, `.metric-card`, `.orders-table`, `.live-badge*`, `.score-item-*`); add minimal new CSS only if needed.

- [ ] **Step 3: Wire into `App.tsx`**

- Build the current request from the form. The simplest approach: lift the last-submitted `BacktestRequest` into App state (App already receives requests via `handleRun`/`handlePreview` from `BacktestForm`). Store `const [lastRequest, setLastRequest] = useState<BacktestRequest | null>(null)` and set it inside `handleRun` and `handlePreview`.
- Render `<PaperPanel request={lastRequest} />` in the main panel (e.g. below the live preview / scorecard, or as its own section). It manages its own data fetching.

- [ ] **Step 4: Add CSS if needed (`web/src/App.css`)**

Reuse existing classes; add only small additions (e.g. a `.paper-actions` flex row for the buttons, a `.paper-config` dim summary line) using existing theme variables (`--surface-2`, `--border`, `--text-dim`, `--accent`).

- [ ] **Step 5: Build to verify**

Run: `cd web && npm run build`
Expected: TypeScript + build pass, no errors.

- [ ] **Step 6: Commit**

```bash
git add web/src
git commit -m "feat(web): add paper account panel (state, equity curve, step/run/init)"
```

---

## Task 8: 실데이터 스모크 + 머지

- [ ] **Step 1: 전체 테스트**

Run: `uv run pytest -q`
Expected: 전체 PASS (기존 + 신규 paper 테스트)

- [ ] **Step 2: 실데이터 CLI 스모크 (네트워크)**

Run:
```bash
uv run python -m ohmystock.paper --db state/smoke.db init --strategy Momentum --symbols AAPL,MSFT,GOOGL,AMZN,META --capital 5000000 --start 2020-01-01 --end 2024-01-01
uv run python -m ohmystock.paper --db state/smoke.db run
uv run python -m ohmystock.paper --db state/smoke.db status
```
Expected: 초기화 → "N 스텝 진행" → status에 cursor=마지막 거래일, equity 출력. `rm -f state/smoke.db` 로 정리.

- [ ] **Step 3: 웹 스모크 (선택, 수동)**

`make start` 후 대시보드에서 백테스트 1회 실행(폼 설정 확정) → 페이퍼 패널에서 "초기화" → "끝까지 빠르게" → 자산곡선·보유·거래 표시 확인.

- [ ] **Step 4: Commit (정리/잔여) + 머지**

```bash
git checkout main && git merge --no-ff <feature-branch>
uv run pytest -q
git push origin main
```

---

## Self-Review

**Spec 커버리지:**
- §2 모듈 구조 → Task 0~7 ✓
- §3 데이터 모델(account/positions/snapshots/trades) → Task 2 ✓
- §4 PaperStore 인터페이스 → Task 1, 2 ✓
- §5 스텝 엔진(커서·ffill 패널·lookahead·멱등성·트랜잭션 저장) → Task 3 ✓
- §6 CLI(init/step/run/status) → Task 5 ; API(/api/paper/*) → Task 6 ; 대시보드 패널 → Task 7 ✓
- §7 에러 처리(미생성→exists:false / step·run 에러 / 커서 끝→None·done) → Task 4, 6 ✓
- §8 테스트(store/engine/service/api 오프라인 + 프론트 빌드) → 각 Task ✓

**비범위 확인:** 멀티계좌·실계좌 cron·슬리피지 정밀화·인증 — 미포함(정상).

**플레이스홀더:** Task 1~6은 완전한 코드. Task 7(프론트)은 컴포넌트 요구사항을 명시하고 빌드 게이트로 검증(기존 프론트 작업과 동일 방식).

**타입 일관성:**
- `PaperAccount`(strategy/params/symbols/initial_capital/start_date/end_date/cursor_date/cash/peak_equity) — Task 1 정의, Task 2~6에서 동일 사용 ✓
- `PaperStore` 메서드 시그니처 — Task 1 Protocol ↔ Task 2 구현 일치 ✓
- `engine.step(account, store, bars, config) -> dict|None` — Task 3 정의 ↔ Task 4 service 호출 일치 ✓
- order_rows 키(symbol/side/notional/price/shares) — engine 생성 ↔ store.append_trades 소비 일치 ✓
- API 응답 형태 — Task 6 ↔ Task 7 api.ts 타입 일치 ✓

**의도된 단순화:** `get_state`의 equity는 마지막 스냅샷 값(네트워크 없이 즉시 조회), positions는 shares만(평가금액 생략). 체결은 d 종가 기준(슬리피지/수수료 미적용).
