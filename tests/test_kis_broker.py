import httpx
import pytest

from ohmystock.core.broker.base import Account, Order
from ohmystock.core.broker.kis import KISBroker


def _make_broker(handler, **kwargs):
    """MockTransport 기반 오프라인 KISBroker를 만든다. 네트워크 미사용."""
    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://openapi.koreainvestment.com:9443",
    )
    return KISBroker(
        app_key="AK",
        app_secret="AS",
        account_no="12345678-01",
        client=client,
        **kwargs,
    )


def test_issue_token_sets_and_returns_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/oauth2/tokenP"
        return httpx.Response(200, json={"access_token": "tok123"})

    broker = _make_broker(handler)
    token = broker.issue_token()

    assert token == "tok123"
    assert broker.access_token == "tok123"


def test_get_account_parses_output2():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/uapi/domestic-stock/v1/trading/inquire-balance"
        return httpx.Response(
            200,
            json={
                "output1": [],
                "output2": [{"tot_evlu_amt": "1000000", "dnca_tot_amt": "250000"}],
            },
        )

    broker = _make_broker(handler, access_token="tok")
    account = broker.get_account()

    assert account == Account(equity=1000000.0, cash=250000.0)


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
