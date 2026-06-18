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
    assert runs[0]["status"] == "failed"
    assert runs[1]["status"] == "ok"
    assert s.last_run()["status"] == "failed"
    assert s.last_success()["target"] == "2024-01-02"


def test_limit(tmp_path):
    s = SqliteSchedulerStore(tmp_path / "p.db")
    for _ in range(5):
        _rec(s)
    assert len(s.recent_runs(limit=3)) == 3
