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
