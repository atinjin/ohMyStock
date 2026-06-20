from datetime import datetime, timedelta

import httpx
import pytest

from ohmystock.core.broker.base import Account, Order
from ohmystock.core.broker.kis import KISBroker


def _make_broker(handler, paper=True, **kwargs):
    """MockTransport 기반 오프라인 KISBroker를 만든다. 네트워크 미사용."""
    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://openapi.koreainvestment.com:9443",
    )
    return KISBroker(
        app_key="AK",
        app_secret="AS",
        account_no="12345678-01",
        paper=paper,
        client=client,
        **kwargs,
    )


def test_issue_token_sets_token_and_expiry():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/oauth2/tokenP"
        return httpx.Response(200, json={
            "access_token": "tok123",
            "access_token_token_expired": "2026-06-21 09:00:00"})

    broker = _make_broker(handler)
    token = broker.issue_token()
    assert token == "tok123"
    assert broker.access_token == "tok123"
    assert broker.token_expires_at == datetime(2026, 6, 21, 9, 0, 0)


def test_issue_token_expiry_from_expires_in():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})

    fixed = datetime(2026, 6, 20, 9, 0, 0)
    broker = _make_broker(handler, now=lambda: fixed)
    broker.issue_token()
    assert broker.token_expires_at == fixed + timedelta(seconds=3600)


def test_ensure_token_refreshes_when_expired():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"access_token": "fresh", "expires_in": 3600})

    fixed = datetime(2026, 6, 20, 9, 0, 0)
    broker = _make_broker(handler, now=lambda: fixed, access_token="stale",
                          token_expires_at=fixed - timedelta(seconds=1))
    broker._ensure_token()
    assert calls["n"] == 1
    assert broker.access_token == "fresh"


def test_ensure_token_keeps_valid():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("유효 토큰인데 재발급 호출됨")

    fixed = datetime(2026, 6, 20, 9, 0, 0)
    broker = _make_broker(handler, now=lambda: fixed, access_token="good",
                          token_expires_at=fixed + timedelta(hours=1))
    broker._ensure_token()
    assert broker.access_token == "good"


def test_mode_selects_tr_and_base_url():
    h = lambda r: httpx.Response(200, json={})
    paper = _make_broker(h)
    live = _make_broker(h, paper=False)
    assert paper._tr("buy") == "VTTC0802U"
    assert paper._tr("sell") == "VTTC0801U"
    assert paper._tr("balance") == "VTTC8434R"
    assert live._tr("buy") == "TTTC0802U"
    assert live._tr("balance") == "TTTC8434R"
    # 주입 client 없을 때 base_url 기본값
    p2 = KISBroker(app_key="k", app_secret="s", account_no="1-01")
    assert "openapivts" in str(p2.client.base_url)
    l2 = KISBroker(app_key="k", app_secret="s", account_no="1-01", paper=False)
    assert "openapivts" not in str(l2.client.base_url)


def test_account_no_split():
    broker = _make_broker(lambda r: httpx.Response(200, json={}))
    assert broker._cano == "12345678"
    assert broker._acnt_prdt_cd == "01"


def test_get_account_parses_output2_with_params():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/uapi/domestic-stock/v1/trading/inquire-balance"
        captured["tr_id"] = request.headers.get("tr_id")
        captured["CANO"] = request.url.params.get("CANO")
        captured["INQR_DVSN"] = request.url.params.get("INQR_DVSN")
        return httpx.Response(200, json={
            "output1": [],
            "output2": [{"tot_evlu_amt": "1000000", "dnca_tot_amt": "250000"}]})

    broker = _make_broker(handler, access_token="tok",
                          token_expires_at=datetime(2030, 1, 1))
    account = broker.get_account()
    assert account == Account(equity=1000000.0, cash=250000.0)
    assert captured["tr_id"] == "VTTC8434R"     # paper 기본
    assert captured["CANO"] == "12345678"
    assert captured["INQR_DVSN"] == "02"


def test_get_positions_excludes_zero_value():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "output1": [
                    {"pdno": "005930", "evlu_amt": "500000"},
                    {"pdno": "000660", "evlu_amt": "0"},
                ],
                "output2": [{"tot_evlu_amt": "1", "dnca_tot_amt": "1"}],
            },
        )

    broker = _make_broker(handler, access_token="tok")
    positions = broker.get_positions()

    assert positions == {"005930": 500000.0}


def test_submit_order_buy_uses_buy_tr_id():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["tr_id"] = request.headers.get("tr_id")
        return httpx.Response(200, json={"rt_cd": "0"})

    broker = _make_broker(handler, access_token="tok")
    broker.submit_order(Order(symbol="005930", side="buy", notional=100000.0))

    assert captured["method"] == "POST"
    assert captured["path"] == "/uapi/domestic-stock/v1/trading/order-cash"
    assert captured["tr_id"] == "TTTC0802U"


def test_submit_order_sell_uses_sell_tr_id():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["tr_id"] = request.headers.get("tr_id")
        return httpx.Response(200, json={"rt_cd": "0"})

    broker = _make_broker(handler, access_token="tok")
    broker.submit_order(Order(symbol="005930", side="sell", notional=100000.0))

    assert captured["tr_id"] == "TTTC0801U"


def test_env_key_fallback(monkeypatch):
    monkeypatch.setenv("KIS_APP_KEY", "env_key")
    monkeypatch.setenv("KIS_APP_SECRET", "env_secret")
    monkeypatch.setenv("KIS_ACCOUNT_NO", "99999999-01")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    broker = KISBroker(client=client)

    assert broker.app_key == "env_key"
    assert broker.app_secret == "env_secret"
    assert broker.account_no == "99999999-01"
