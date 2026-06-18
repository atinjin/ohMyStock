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
    assert slept == [5.0, 10.0]
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
    assert len(slept) == 2
