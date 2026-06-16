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
        conn.executescript(_SCHEMA)
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
