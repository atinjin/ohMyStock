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


def _client_with_broker(tmp_path, broker_factory):
    adapter = YFinanceAdapter(cache=ParquetCache(tmp_path), downloader=_fake_dl)
    return TestClient(create_app(adapter=adapter, broker_factory=broker_factory))


class _FakeBroker:
    paper = True

    def get_account(self):
        from ohmystock.core.broker.base import Account
        return Account(equity=10000000.0, cash=9000000.0)

    def get_holdings(self):
        return [{"symbol": "005930", "name": "삼성전자", "value": 354000.0}]


def test_broker_account_ok(tmp_path):
    made = {"n": 0}

    def factory(name):
        made["n"] += 1
        return _FakeBroker()

    client = _client_with_broker(tmp_path, factory)
    resp = client.get("/api/broker/account?broker=kis")
    assert resp.status_code == 200
    body = resp.json()
    assert body["broker"] == "kis"
    assert body["mode"] == "paper"
    assert body["equity"] == 10000000.0
    assert body["cash"] == 9000000.0
    assert body["positions"] == [
        {"symbol": "005930", "name": "삼성전자", "value": 354000.0}]
    # 캐시: 같은 브로커 재조회 시 factory 는 1회만
    client.get("/api/broker/account?broker=kis")
    assert made["n"] == 1


def test_broker_account_invalid_broker(tmp_path):
    client = _client_with_broker(tmp_path, lambda name: _FakeBroker())
    resp = client.get("/api/broker/account?broker=ibkr")
    assert resp.status_code == 400


def test_broker_account_error_returns_502(tmp_path):
    class _BoomBroker:
        paper = False

        def get_account(self):
            raise RuntimeError("키 없음")

        def get_holdings(self):
            return []

    client = _client_with_broker(tmp_path, lambda name: _BoomBroker())
    resp = client.get("/api/broker/account?broker=toss")
    assert resp.status_code == 502
    assert "키 없음" in resp.json()["detail"]


def test_broker_account_toss_includes_krw_rate(tmp_path):
    from ohmystock.core.broker.base import Account

    class _TossFake:
        paper = False

        def get_account(self):
            return Account(equity=15028.0, cash=0.15)

        def get_holdings(self):
            return [{"symbol": "AAPL", "name": "애플", "value": 1795.0}]

        def exchange_rate(self, base="USD", quote="KRW"):
            return 1385.5

    client = _client_with_broker(tmp_path, lambda name: _TossFake())
    body = client.get("/api/broker/account?broker=toss").json()
    assert body["krw_rate"] == 1385.5


def test_broker_account_kis_krw_rate_null(tmp_path):
    body = _client_with_broker(tmp_path, lambda name: _FakeBroker()).get(
        "/api/broker/account?broker=kis").json()
    assert body["krw_rate"] is None


def test_market_overview_endpoint_and_cache(tmp_path):
    import pandas as pd
    calls = {"n": 0}

    def provider(symbol):
        calls["n"] += 1
        closes = [100.0] * 40 + [110.0, 121.0]
        idx = pd.date_range("2025-01-01", periods=len(closes), freq="B")
        return pd.DataFrame({"open": closes, "high": closes, "low": closes,
                             "close": closes, "volume": [1] * len(closes)}, index=idx)

    adapter = YFinanceAdapter(cache=ParquetCache(tmp_path), downloader=_fake_dl)
    client = TestClient(create_app(adapter=adapter, market_provider=provider))
    resp = client.get("/api/market/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["markets"]["us"]["open"], bool)
    assert isinstance(body["markets"]["kr"]["open"], bool)
    assert len(body["items"]) == 7
    after_first = calls["n"]
    assert after_first == 7            # 심볼 7개 1회씩
    client.get("/api/market/overview")  # TTL 내 → 캐시
    assert calls["n"] == after_first    # provider 재호출 없음
