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
