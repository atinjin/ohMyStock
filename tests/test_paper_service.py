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
