import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from ohmystock.core.data.cache import ParquetCache
from ohmystock.core.data.yfinance_adapter import YFinanceAdapter
from server.app import create_app


def _fake_dl(symbol, start, end):
    n = 120
    closes = list(np.linspace(10, 18, n))
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes,
         "close": closes, "volume": [1000] * n}, index=idx)


def _client(tmp_path):
    adapter = YFinanceAdapter(cache=ParquetCache(tmp_path), downloader=_fake_dl)
    return TestClient(create_app(adapter=adapter))


def test_health(tmp_path):
    resp = _client(tmp_path).get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_strategies(tmp_path):
    resp = _client(tmp_path).get("/api/strategies")
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()["strategies"]]
    assert "MACrossover" in names
    assert "Momentum" in names


def test_backtest_ok(tmp_path):
    body = {
        "strategy": "MACrossover",
        "params": {"short": 5, "long": 20},
        "symbols": ["AAPL", "MSFT"],
        "start": "2024-01-01",
        "end": "2024-06-30",
    }
    resp = _client(tmp_path).post("/api/backtest", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["metrics"]) == 6
    assert len(data["validations"]) == 12  # 11 + 과최적화
    assert len(data["equity_curve"]) > 0


def test_backtest_unknown_strategy(tmp_path):
    body = {
        "strategy": "DoesNotExist",
        "symbols": ["AAPL"],
        "start": "2024-01-01",
        "end": "2024-06-30",
    }
    resp = _client(tmp_path).post("/api/backtest", json=body)
    assert resp.status_code == 400


def test_live_preview_ok(tmp_path):
    body = {
        "strategy": "Momentum",
        "params": {"lookback": 20, "top_k": 2},
        "symbols": ["AAPL", "MSFT", "GOOGL"],
        "start": "2024-01-01",
        "end": "2024-06-30",
    }
    resp = _client(tmp_path).post("/api/live/preview", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["strategy"] == "Momentum"
    assert "orders" in data
    assert "risk" in data
    assert "account_before" in data
