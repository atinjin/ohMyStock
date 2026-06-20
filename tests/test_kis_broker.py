import json
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


def _price_and_order_handler(captured, price=10000.0, rt_cd="0"):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/uapi/domestic-stock/v1/quotations/inquire-price":
            assert request.headers.get("tr_id") == "FHKST01010100"
            return httpx.Response(200, json={"output": {"stck_prpr": str(price)}})
        if request.url.path == "/uapi/domestic-stock/v1/trading/order-cash":
            captured["tr_id"] = request.headers.get("tr_id")
            captured["body"] = json.loads(request.content.decode())
            captured["hashkey"] = request.headers.get("hashkey")
            return httpx.Response(200, json={"rt_cd": rt_cd, "msg1": "메시지"})
        raise AssertionError(f"예상치 못한 경로 {request.url.path}")
    return handler


def test_submit_order_buy_floors_quantity_paper_tr_id():
    captured = {}
    broker = _make_broker(_price_and_order_handler(captured, price=10000.0),
                          access_token="tok", token_expires_at=datetime(2030, 1, 1))
    broker.submit_order(Order(symbol="005930", side="buy", notional=35000.0))
    assert captured["tr_id"] == "VTTC0802U"          # paper 기본
    assert captured["body"]["PDNO"] == "005930"
    assert captured["body"]["ORD_DVSN"] == "01"      # 시장가
    assert captured["body"]["ORD_QTY"] == "3"        # floor(35000/10000)
    assert captured["body"]["ORD_UNPR"] == "0"
    assert captured["hashkey"] is None               # 기본 off


def test_submit_order_sell_uses_live_tr_id_when_not_paper():
    captured = {}
    broker = _make_broker(_price_and_order_handler(captured, price=10000.0),
                          paper=False, access_token="tok",
                          token_expires_at=datetime(2030, 1, 1))
    broker.submit_order(Order(symbol="005930", side="sell", notional=20000.0))
    assert captured["tr_id"] == "TTTC0801U"
    assert captured["body"]["ORD_QTY"] == "2"


def test_submit_order_skips_below_one_share():
    seen = {"orders": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/uapi/domestic-stock/v1/quotations/inquire-price":
            return httpx.Response(200, json={"output": {"stck_prpr": "100000"}})
        if request.url.path == "/uapi/domestic-stock/v1/trading/order-cash":
            seen["orders"] += 1
            return httpx.Response(200, json={"rt_cd": "0"})
        raise AssertionError("unexpected")

    broker = _make_broker(handler, access_token="tok",
                          token_expires_at=datetime(2030, 1, 1))
    broker.submit_order(Order(symbol="005930", side="buy", notional=50000.0))  # <1주
    assert seen["orders"] == 0


def test_submit_order_raises_on_rt_cd_failure():
    captured = {}
    broker = _make_broker(_price_and_order_handler(captured, rt_cd="1"),
                          access_token="tok", token_expires_at=datetime(2030, 1, 1))
    with pytest.raises(ValueError):
        broker.submit_order(Order(symbol="005930", side="buy", notional=35000.0))


def test_submit_order_raises_on_zero_price_no_order():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/uapi/domestic-stock/v1/quotations/inquire-price":
            return httpx.Response(200, json={"output": {"stck_prpr": "0"}})
        if request.url.path == "/uapi/domestic-stock/v1/trading/order-cash":
            raise AssertionError("0가인데 주문이 나감")
        raise AssertionError("unexpected")

    broker = _make_broker(handler, access_token="tok",
                          token_expires_at=datetime(2030, 1, 1))
    with pytest.raises(ValueError):
        broker.submit_order(Order(symbol="005930", side="buy", notional=35000.0))


def test_submit_order_with_hashkey():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/uapi/hashkey":
            return httpx.Response(200, json={"HASH": "HASHED"})
        if request.url.path == "/uapi/domestic-stock/v1/quotations/inquire-price":
            return httpx.Response(200, json={"output": {"stck_prpr": "10000"}})
        if request.url.path == "/uapi/domestic-stock/v1/trading/order-cash":
            captured["hashkey"] = request.headers.get("hashkey")
            return httpx.Response(200, json={"rt_cd": "0"})
        raise AssertionError("unexpected")

    broker = _make_broker(handler, access_token="tok",
                          token_expires_at=datetime(2030, 1, 1), use_hashkey=True)
    broker.submit_order(Order(symbol="005930", side="buy", notional=35000.0))
    assert captured["hashkey"] == "HASHED"


def test_submit_order_paper_sell_and_live_buy_tr_ids():
    # submit_order 경로로 paper 매도(V*)·실전 매수(T*) tr_id 분기까지 검증(비대칭 갭 차단)
    cap_p = {}
    paper = _make_broker(_price_and_order_handler(cap_p, price=10000.0),
                         access_token="tok", token_expires_at=datetime(2030, 1, 1))
    paper.submit_order(Order(symbol="005930", side="sell", notional=20000.0))
    assert cap_p["tr_id"] == "VTTC0801U"   # 모의 매도

    cap_l = {}
    live = _make_broker(_price_and_order_handler(cap_l, price=10000.0),
                        paper=False, access_token="tok",
                        token_expires_at=datetime(2030, 1, 1))
    live.submit_order(Order(symbol="005930", side="buy", notional=30000.0))
    assert cap_l["tr_id"] == "TTTC0802U"   # 실전 매수


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


def test_inquire_balance_retries_on_rate_limit():
    # KIS 초당 거래 제한(EGW00201)은 실행 전 거부 → 짧게 대기 후 재시도
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, json={
                "rt_cd": "1", "msg_cd": "EGW00201",
                "msg1": "초당 거래건수를 초과하였습니다."})
        return httpx.Response(200, json={
            "output1": [],
            "output2": [{"tot_evlu_amt": "1000000", "dnca_tot_amt": "500000"}]})

    slept = []
    broker = _make_broker(handler, access_token="tok",
                          token_expires_at=datetime(2030, 1, 1),
                          sleep=lambda s: slept.append(s))
    assert broker.get_account() == Account(equity=1000000.0, cash=500000.0)
    assert calls["n"] == 2          # 1차 거부 후 재시도
    assert slept == [0.5]           # 재시도 전 대기


def test_send_does_not_retry_non_rate_limit_500():
    # EGW00201 이 아닌 500 은 재시도 없이 즉시 실패
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, json={
            "rt_cd": "1", "msg_cd": "EGW99999", "msg1": "기타 오류"})

    broker = _make_broker(handler, access_token="tok",
                          token_expires_at=datetime(2030, 1, 1),
                          sleep=lambda s: None)
    with pytest.raises(httpx.HTTPStatusError):
        broker.get_account()
    assert calls["n"] == 1          # 재시도 없음
