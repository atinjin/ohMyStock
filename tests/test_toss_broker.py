import json
from datetime import datetime, timedelta

import httpx
import pytest

from ohmystock.core.broker.base import Account, Order
from ohmystock.core.broker.toss import TossBroker

_BASE = "https://openapi.tossinvest.com"


def _make_broker(handler, **kwargs):
    """MockTransport 기반 오프라인 TossBroker. 네트워크 미사용."""
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url=_BASE)
    kwargs.setdefault("client_id", "CID")
    kwargs.setdefault("client_secret", "CSEC")
    kwargs.setdefault("account_seq", "42")
    return TossBroker(client=client, **kwargs)


def test_issue_token_sets_token_and_expiry():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"access_token": "tok123",
                                         "token_type": "Bearer", "expires_in": 3600})

    fixed = datetime(2026, 6, 20, 9, 0, 0)
    broker = _make_broker(handler, now=lambda: fixed)
    token = broker.issue_token()

    assert token == "tok123"
    assert broker.access_token == "tok123"
    assert broker.token_expires_at == fixed + timedelta(seconds=3600)
    assert captured["method"] == "POST"
    assert captured["path"] == "/oauth2/token"
    assert "grant_type=client_credentials" in captured["body"]
    assert "client_id=CID" in captured["body"]


def test_issue_token_surfaces_error_body():
    # 토큰 발급 실패 시 상태코드 + 응답 본문(원인)을 에러 메시지로 노출
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={
            "error": "access_denied",
            "error_description": "IP address not allowed"})

    broker = _make_broker(handler)
    with pytest.raises(ValueError) as exc:
        broker.issue_token()
    msg = str(exc.value)
    assert "403" in msg
    assert "IP address not allowed" in msg


def test_env_credential_fallback(monkeypatch):
    monkeypatch.setenv("TOSS_CLIENT_ID", "env_id")
    monkeypatch.setenv("TOSS_CLIENT_SECRET", "env_secret")
    monkeypatch.setenv("TOSS_ACCOUNT_SEQ", "777")

    client = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={})), base_url=_BASE)
    broker = TossBroker(client=client)

    assert broker.client_id == "env_id"
    assert broker.client_secret == "env_secret"
    assert broker._account_seq == "777"


def test_ensure_token_refreshes_when_expired():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"access_token": "fresh", "expires_in": 3600})

    fixed = datetime(2026, 6, 20, 9, 0, 0)
    # 토큰은 있으나 만료시각이 과거 → 재발급되어야 함
    broker = _make_broker(handler, now=lambda: fixed,
                          access_token="stale",
                          token_expires_at=fixed - timedelta(seconds=1))
    broker._ensure_token()

    assert calls["n"] == 1
    assert broker.access_token == "fresh"


def test_ensure_token_keeps_valid_token():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("유효 토큰인데 재발급 호출됨")

    fixed = datetime(2026, 6, 20, 9, 0, 0)
    broker = _make_broker(handler, now=lambda: fixed,
                          access_token="good",
                          token_expires_at=fixed + timedelta(hours=1))
    broker._ensure_token()  # 호출돼도 네트워크 안 침

    assert broker.access_token == "good"


def test_result_unwraps_envelope_and_raises_without_result():
    broker = _make_broker(lambda r: httpx.Response(200, json={}))
    ok = httpx.Response(200, json={"result": {"x": 1}})
    assert broker._result(ok) == {"x": 1}
    with pytest.raises(ValueError):
        broker._result(httpx.Response(200, json={"no_result": True}))


def test_resolve_account_seq_picks_brokerage_and_caches():
    calls = {"accounts": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/accounts":
            calls["accounts"] += 1
            return httpx.Response(200, json={"result": [
                {"accountSeq": 100, "accountType": "PENSION_SAVINGS"},
                {"accountSeq": 200, "accountType": "BROKERAGE"},
            ]})
        raise AssertionError(f"예상치 못한 경로 {request.url.path}")

    broker = _make_broker(handler, account_seq=None, access_token="tok",
                          token_expires_at=datetime(2030, 1, 1))
    assert broker._resolve_account_seq() == 200
    assert broker._resolve_account_seq() == 200   # 캐시
    assert calls["accounts"] == 1


def test_get_account_combines_holdings_and_buying_power():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/holdings":
            assert request.headers.get("X-Tossinvest-Account") == "42"
            return httpx.Response(200, json={"result": {
                "marketValue": {"amount": {"krw": 0, "usd": 8000.0}},
                "items": [],
            }})
        if request.url.path == "/api/v1/buying-power":
            assert request.url.params.get("currency") == "USD"
            return httpx.Response(200, json={"result": {
                "currency": "USD", "cashBuyingPower": 2000.0}})
        raise AssertionError(f"예상치 못한 경로 {request.url.path}")

    broker = _make_broker(handler, access_token="tok",
                          token_expires_at=datetime(2030, 1, 1))
    account = broker.get_account()
    assert account == Account(equity=10000.0, cash=2000.0)


def test_get_positions_excludes_zero_quantity():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/holdings":
            return httpx.Response(200, json={"result": {
                "marketValue": {"amount": {"usd": 5000.0}},
                "items": [
                    {"symbol": "AAPL", "quantity": 10, "currency": "USD",
                     "marketValue": {"amount": 3000.0}},
                    {"symbol": "MSFT", "quantity": 0, "currency": "USD",
                     "marketValue": {"amount": 0.0}},
                ],
            }})
        raise AssertionError(f"예상치 못한 경로 {request.url.path}")

    broker = _make_broker(handler, access_token="tok",
                          token_expires_at=datetime(2030, 1, 1))
    assert broker.get_positions() == {"AAPL": 3000.0}


def test_submit_order_buy_floors_quantity():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/prices":
            assert request.url.params.get("symbols") == "AAPL"
            return httpx.Response(200, json={"result": [
                {"symbol": "AAPL", "lastPrice": 150.0}]})
        if request.url.path == "/api/v1/orders":
            captured["body"] = json.loads(request.content.decode())
            captured["account"] = request.headers.get("X-Tossinvest-Account")
            return httpx.Response(200, json={"result": {"orderId": "ord-1"}})
        raise AssertionError(f"예상치 못한 경로 {request.url.path}")

    broker = _make_broker(handler, access_token="tok",
                          token_expires_at=datetime(2030, 1, 1),
                          client_order_id_fn=lambda: "fixed-id")
    broker.submit_order(Order(symbol="AAPL", side="buy", notional=500.0))

    body = captured["body"]
    assert body["symbol"] == "AAPL"
    assert body["side"] == "BUY"
    assert body["orderType"] == "MARKET"
    assert body["quantity"] == 3          # floor(500/150)
    assert body["clientOrderId"] == "fixed-id"
    assert captured["account"] == "42"


def test_submit_order_sell_side():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/prices":
            return httpx.Response(200, json={"result": [
                {"symbol": "AAPL", "lastPrice": 100.0}]})
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"result": {"orderId": "ord-2"}})

    broker = _make_broker(handler, access_token="tok",
                          token_expires_at=datetime(2030, 1, 1))
    broker.submit_order(Order(symbol="AAPL", side="sell", notional=350.0))
    assert captured["body"]["side"] == "SELL"
    assert captured["body"]["quantity"] == 3


def test_submit_order_skips_below_one_share():
    seen = {"orders": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/prices":
            return httpx.Response(200, json={"result": [
                {"symbol": "AAPL", "lastPrice": 1000.0}]})
        if request.url.path == "/api/v1/orders":
            seen["orders"] += 1
            return httpx.Response(200, json={"result": {"orderId": "x"}})
        raise AssertionError("unexpected")

    broker = _make_broker(handler, access_token="tok",
                          token_expires_at=datetime(2030, 1, 1))
    broker.submit_order(Order(symbol="AAPL", side="buy", notional=500.0))  # <1주
    assert seen["orders"] == 0   # 주문 POST 없음


def test_submit_order_raises_without_order_id():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/prices":
            return httpx.Response(200, json={"result": [
                {"symbol": "AAPL", "lastPrice": 100.0}]})
        return httpx.Response(200, json={"result": {}})  # orderId 없음

    broker = _make_broker(handler, access_token="tok",
                          token_expires_at=datetime(2030, 1, 1))
    with pytest.raises(ValueError):
        broker.submit_order(Order(symbol="AAPL", side="buy", notional=500.0))


def test_submit_order_raises_on_zero_price_no_post():
    # 정류/장전 등 현재가 0 → 나눗셈 크래시 대신 명확한 예외, 주문 POST 없음
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/prices":
            return httpx.Response(200, json={"result": [
                {"symbol": "AAPL", "lastPrice": 0.0}]})
        if request.url.path == "/api/v1/orders":
            raise AssertionError("0가인데 실주문이 나감")
        raise AssertionError(f"예상치 못한 경로 {request.url.path}")

    broker = _make_broker(handler, access_token="tok",
                          token_expires_at=datetime(2030, 1, 1))
    with pytest.raises(ValueError):
        broker.submit_order(Order(symbol="AAPL", side="buy", notional=500.0))


def test_submit_order_raises_on_missing_symbol_no_post():
    # 요청 종목이 시세에 없으면 잘못된 가격으로 주문 내지 않고 예외
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/prices":
            return httpx.Response(200, json={"result": [
                {"symbol": "MSFT", "lastPrice": 100.0}]})  # 다른 종목만
        if request.url.path == "/api/v1/orders":
            raise AssertionError("시세 없는데 실주문이 나감")
        raise AssertionError(f"예상치 못한 경로 {request.url.path}")

    broker = _make_broker(handler, access_token="tok",
                          token_expires_at=datetime(2030, 1, 1))
    with pytest.raises(ValueError):
        broker.submit_order(Order(symbol="AAPL", side="buy", notional=500.0))


def _mixed_currency_holdings_handler(request):
    if request.url.path == "/api/v1/holdings":
        return httpx.Response(200, json={"result": {
            "marketValue": {"amount": {"usd": 4795.0, "krw": 1402000.0}},
            "items": [
                {"symbol": "AAPL", "quantity": 10, "currency": "USD",
                 "marketValue": {"amount": 1795.0}},
                {"symbol": "TSLA", "quantity": 1, "currency": "USD",
                 "marketValue": {"amount": 3000.0}},
                {"symbol": "005930", "quantity": 4, "currency": "KRW",
                 "marketValue": {"amount": 1402000.0}},
            ],
        }})
    raise AssertionError(f"예상치 못한 경로 {request.url.path}")


def test_get_positions_filters_to_usd_by_default():
    # 다통화 계좌: 기본 usd → US 종목만(원화 종목 제외), 합이 USD equity 슬리브와 일치
    broker = _make_broker(_mixed_currency_holdings_handler, access_token="tok",
                          token_expires_at=datetime(2030, 1, 1))
    assert broker.get_positions() == {"AAPL": 1795.0, "TSLA": 3000.0}


def test_get_positions_krw_instance_returns_kr_only():
    broker = _make_broker(_mixed_currency_holdings_handler, currency="krw",
                          access_token="tok", token_expires_at=datetime(2030, 1, 1))
    assert broker.get_positions() == {"005930": 1402000.0}


def test_get_holdings_includes_name():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/holdings":
            return httpx.Response(200, json={"result": {
                "marketValue": {"amount": {"usd": 1795.0}},
                "items": [{"symbol": "AAPL", "name": "애플", "quantity": 10,
                           "currency": "USD", "marketValue": {"amount": 1795.0}}]}})
        raise AssertionError(f"예상치 못한 경로 {request.url.path}")

    broker = _make_broker(handler, access_token="tok",
                          token_expires_at=datetime(2030, 1, 1))
    assert broker.get_holdings() == [
        {"symbol": "AAPL", "name": "애플", "value": 1795.0}]


def test_exchange_rate():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/exchange-rate":
            assert request.url.params.get("baseCurrency") == "USD"
            assert request.url.params.get("quoteCurrency") == "KRW"
            return httpx.Response(200, json={"result": {"rate": "1385.50", "midRate": "1384.0"}})
        raise AssertionError(f"예상치 못한 경로 {request.url.path}")

    broker = _make_broker(handler, access_token="tok",
                          token_expires_at=datetime(2030, 1, 1))
    assert broker.exchange_rate("USD", "KRW") == 1385.5
