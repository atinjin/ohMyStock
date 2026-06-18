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
