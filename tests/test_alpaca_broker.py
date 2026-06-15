import httpx
import pytest

from ohmystock.core.broker.alpaca import AlpacaBroker
from ohmystock.core.broker.base import Account, Order

BASE_URL = "https://paper-api.alpaca.markets"


def _broker(handler):
    """MockTransport 기반 AlpacaBroker. 네트워크 없음."""
    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url=BASE_URL
    )
    return AlpacaBroker(api_key="k", secret_key="s", client=client)


def test_get_account_parses_equity_and_cash():
    def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/v2/account"
        return httpx.Response(200, json={"equity": "10000.50", "cash": "2500.25"})

    broker = _broker(handler)
    acct = broker.get_account()
    assert acct == Account(equity=10000.50, cash=2500.25)
    assert isinstance(acct.equity, float)
    assert isinstance(acct.cash, float)


def test_get_positions_maps_symbol_to_market_value():
    def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/v2/positions"
        return httpx.Response(
            200,
            json=[
                {"symbol": "AAPL", "market_value": "3000"},
                {"symbol": "MSFT", "market_value": "1500"},
            ],
        )

    broker = _broker(handler)
    positions = broker.get_positions()
    assert positions == {"AAPL": 3000.0, "MSFT": 1500.0}


def test_submit_order_posts_correct_market_order():
    captured = {}

    def handler(request):
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = __import__("json").loads(request.content)
        return httpx.Response(200, json={"id": "x"})

    broker = _broker(handler)
    broker.submit_order(Order(symbol="AAPL", side="buy", notional=123.456))

    assert captured["method"] == "POST"
    assert captured["path"] == "/v2/orders"
    body = captured["body"]
    assert body["symbol"] == "AAPL"
    assert body["side"] == "buy"
    assert body["notional"] == 123.46  # rounded to 2 decimals
    assert body["type"] == "market"
    assert body["time_in_force"] == "day"


def test_submit_order_raises_on_error_status():
    def handler(request):
        return httpx.Response(422, json={"message": "rejected"})

    broker = _broker(handler)
    with pytest.raises(httpx.HTTPStatusError):
        broker.submit_order(Order(symbol="AAPL", side="buy", notional=100.0))


def test_env_key_fallback_constructs_without_passed_keys(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "env-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "env-secret")

    def handler(request):
        return httpx.Response(200, json={"equity": "1.0", "cash": "1.0"})

    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url=BASE_URL
    )
    # 키를 넘기지 않아도 환경변수에서 읽어 생성 성공
    broker = AlpacaBroker(client=client)
    assert broker.api_key == "env-key"
    assert broker.secret_key == "env-secret"
    # 주입된 클라이언트로 네트워크 없이 동작 확인
    assert broker.get_account() == Account(equity=1.0, cash=1.0)
