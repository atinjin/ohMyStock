# TOSS Invest Broker Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 토스증권 Open API를 `Broker` 프로토콜(`TossBroker`)로 구현하고 오프라인으로 검증한다(실 스모크는 사용자 실행).

**Architecture:** `ohmystock/core/broker/toss.py`에 `TossBroker`를 추가한다. AlpacaBroker/KISBroker와 동형(주입 httpx.Client + env 폴백 + raise_for_status). OAuth client_credentials 토큰을 자동 갱신하고, 응답 공통 envelope `{result}`를 파싱하며, 주문은 현재가로 `floor(notional/lastPrice)` 정수 수량을 계산해 MARKET으로 제출한다. 모든 테스트는 `httpx.MockTransport`로 네트워크 없이 돈다.

**Tech Stack:** Python 3.11, httpx, pytest, uv.

## Global Constraints

- 실행: `uv run pytest <path> -q` (VIRTUAL_ENV 3.9.11 경고는 무해).
- TOSS는 **샌드박스 없음 — 모든 주문 실거래.** 에이전트는 실주문을 내지 않는다(오프라인 테스트만).
- base URL `https://openapi.tossinvest.com`. 토큰 `POST /oauth2/token`(form-urlencoded, `grant_type=client_credentials`+`client_id`+`client_secret`) → `access_token`/`expires_in`(envelope 아님).
- 공통 헤더 `Authorization: Bearer {token}`; 계좌·자산·주문 호출엔 추가로 `X-Tossinvest-Account: {accountSeq}`.
- OAuth 외 응답은 `{ "result": … }` envelope.
- `Account`/`Order`는 `ohmystock/core/broker/base.py` 재사용: `Account(equity: float, cash: float)`, `Order(symbol: str, side: "buy"|"sell", notional: float)`.
- 통화 기본 `usd`(US 바스켓). side 매핑 `buy→BUY`, `sell→SELL`. orderType `MARKET`. 1주 미만 수량은 스킵.
- env 폴백: `TOSS_CLIENT_ID`/`TOSS_CLIENT_SECRET`/`TOSS_ACCOUNT_SEQ`.
- 각 태스크 끝에서 커밋. 커밋은 atinjin 작성.

---

### Task 1: TossBroker — OAuth 토큰 + 자격증명 폴백 + envelope 헬퍼

**Files:**
- Create: `ohmystock/core/broker/toss.py`
- Test: `tests/test_toss_broker.py`

**Interfaces:**
- Consumes: `ohmystock.core.broker.base.Account, Order`.
- Produces: `TossBroker(client_id=None, client_secret=None, account_seq=None, *, currency="usd", base_url="https://openapi.tossinvest.com", client=None, access_token=None, token_expires_at=None, now=None, client_order_id_fn=None)`; `issue_token() -> str` (access_token 저장 + `token_expires_at` 설정); `_ensure_token() -> None`; `_result(resp) -> Any` (envelope 파싱). 속성 `client_id`/`client_secret`/`access_token`/`token_expires_at`/`currency`/`client`.

- [ ] **Step 1: Write the failing tests**

`tests/test_toss_broker.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_toss_broker.py -q`
Expected: FAIL (`ModuleNotFoundError: ohmystock.core.broker.toss`).

- [ ] **Step 3: Write minimal implementation**

`ohmystock/core/broker/toss.py`:
```python
"""토스증권(TOSS Invest) Open API 브로커 어댑터.

샌드박스(모의투자)가 없어 모든 주문이 실거래다. httpx.Client 를 주입하면
httpx.MockTransport 로 완전히 오프라인 테스트할 수 있다. 환경변수
TOSS_CLIENT_ID / TOSS_CLIENT_SECRET / TOSS_ACCOUNT_SEQ 폴백을 지원한다.
"""

import math
import os
import uuid
from datetime import datetime, timedelta

import httpx

from ohmystock.core.broker.base import Account, Order

_BASE_URL = "https://openapi.tossinvest.com"
_TOKEN_PATH = "/oauth2/token"
_REFRESH_MARGIN = timedelta(seconds=60)


class TossBroker:
    """토스증권 Open API 어댑터 (Broker 프로토콜)."""

    def __init__(
        self,
        client_id=None,
        client_secret=None,
        account_seq=None,
        *,
        currency="usd",
        base_url=_BASE_URL,
        client=None,
        access_token=None,
        token_expires_at=None,
        now=None,
        client_order_id_fn=None,
    ):
        self.client_id = client_id or os.environ.get("TOSS_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("TOSS_CLIENT_SECRET")
        self._account_seq = account_seq or os.environ.get("TOSS_ACCOUNT_SEQ")
        self.currency = currency.lower()
        self.access_token = access_token
        self.token_expires_at = token_expires_at
        self.client = client or httpx.Client(base_url=base_url)
        self._now = now or datetime.now
        self._client_order_id_fn = client_order_id_fn or (lambda: uuid.uuid4().hex)

    # --- 토큰 ---------------------------------------------------------------
    def issue_token(self) -> str:
        """OAuth2 client_credentials 토큰 발급 + 만료시각 저장."""
        resp = self.client.post(
            _TOKEN_PATH,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        resp.raise_for_status()
        j = resp.json()  # OAuth 응답은 envelope 아님
        self.access_token = j["access_token"]
        expires_in = int(j.get("expires_in", 0))
        self.token_expires_at = self._now() + timedelta(seconds=expires_in)
        return self.access_token

    def _ensure_token(self) -> None:
        if self.access_token is None:
            self.issue_token()
            return
        if self.token_expires_at is not None and \
                self._now() >= self.token_expires_at - _REFRESH_MARGIN:
            self.issue_token()

    # --- 공통 ---------------------------------------------------------------
    def _result(self, resp: httpx.Response):
        resp.raise_for_status()
        j = resp.json()
        if "result" not in j:
            raise ValueError(f"TOSS 응답에 result 없음: {j}")
        return j["result"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_toss_broker.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add ohmystock/core/broker/toss.py tests/test_toss_broker.py
git commit -m "feat(toss): add TossBroker OAuth token lifecycle + envelope helper"
```

---

### Task 2: 계좌 해석 + get_account + get_positions

**Files:**
- Modify: `ohmystock/core/broker/toss.py` (메서드 추가)
- Test: `tests/test_toss_broker.py` (테스트 추가)

**Interfaces:**
- Consumes: Task 1의 `TossBroker`, `_ensure_token`, `_result`, `self.access_token`, `self.currency`, `self._account_seq`.
- Produces: `_resolve_account_seq() -> str` (account_seq 미지정 시 `GET /api/v1/accounts`의 첫 BROKERAGE seq, 캐시); `_acct_headers() -> dict`; `get_account() -> Account`; `get_positions() -> dict[str, float]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_toss_broker.py` 끝에 추가:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_toss_broker.py -q`
Expected: FAIL (`AttributeError: 'TossBroker' object has no attribute '_resolve_account_seq'`).

- [ ] **Step 3: Write minimal implementation**

`ohmystock/core/broker/toss.py`의 `_result` 메서드 아래에 추가:
```python
    # --- 계좌 ---------------------------------------------------------------
    def _resolve_account_seq(self):
        if self._account_seq:
            return self._account_seq
        self._ensure_token()
        resp = self.client.get(
            "/api/v1/accounts",
            headers={"Authorization": f"Bearer {self.access_token}"},
        )
        accounts = self._result(resp)
        for acc in accounts:
            if acc.get("accountType") == "BROKERAGE":
                self._account_seq = acc["accountSeq"]
                return self._account_seq
        if accounts:
            self._account_seq = accounts[0]["accountSeq"]
            return self._account_seq
        raise ValueError("TOSS 계좌를 찾을 수 없습니다 (accounts 비어있음)")

    def _acct_headers(self) -> dict:
        self._ensure_token()
        return {
            "Authorization": f"Bearer {self.access_token}",
            "X-Tossinvest-Account": str(self._resolve_account_seq()),
        }

    def get_account(self) -> Account:
        headers = self._acct_headers()
        holdings = self._result(self.client.get("/api/v1/holdings", headers=headers))
        amount = holdings.get("marketValue", {}).get("amount", {})
        positions_value = float(amount.get(self.currency) or 0.0)
        bp = self._result(self.client.get(
            "/api/v1/buying-power",
            params={"currency": self.currency.upper()},
            headers=headers,
        ))
        cash = float(bp.get("cashBuyingPower") or 0.0)
        return Account(equity=positions_value + cash, cash=cash)

    def get_positions(self) -> dict[str, float]:
        headers = self._acct_headers()
        holdings = self._result(self.client.get("/api/v1/holdings", headers=headers))
        out = {}
        for item in holdings.get("items", []):
            if float(item.get("quantity") or 0) <= 0:
                continue
            mv = item.get("marketValue", {})
            out[item["symbol"]] = float(mv.get("amount") or 0.0)
        return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_toss_broker.py -q`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add ohmystock/core/broker/toss.py tests/test_toss_broker.py
git commit -m "feat(toss): add account resolution + get_account/get_positions"
```

---

### Task 3: submit_order (현재가 → floor 수량 → MARKET 주문)

**Files:**
- Modify: `ohmystock/core/broker/toss.py` (메서드 추가)
- Test: `tests/test_toss_broker.py` (테스트 추가)

**Interfaces:**
- Consumes: Task 1·2의 `_ensure_token`, `_resolve_account_seq`, `_result`, `self.access_token`, `self._client_order_id_fn`.
- Produces: `_last_price(symbol: str) -> float` (`GET /api/v1/prices?symbols=SYM` → `lastPrice`); `submit_order(order: Order) -> None` (floor 수량, side BUY/SELL, MARKET, clientOrderId; `qty<1` 스킵; `result.orderId` 없으면 예외).

- [ ] **Step 1: Write the failing tests**

`tests/test_toss_broker.py` 끝에 추가:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_toss_broker.py -q`
Expected: FAIL (`AttributeError: ... 'submit_order'` 또는 `_last_price`).

- [ ] **Step 3: Write minimal implementation**

`ohmystock/core/broker/toss.py`의 `get_positions` 아래에 추가:
```python
    # --- 시세 / 주문 --------------------------------------------------------
    def _last_price(self, symbol: str) -> float:
        resp = self.client.get(
            "/api/v1/prices",
            params={"symbols": symbol},
            headers={"Authorization": f"Bearer {self.access_token}"},
        )
        for row in self._result(resp):
            if row.get("symbol") == symbol:
                return float(row["lastPrice"])
        raise ValueError(f"TOSS 시세 없음: {symbol}")

    def submit_order(self, order: Order) -> None:
        self._ensure_token()
        seq = self._resolve_account_seq()
        price = self._last_price(order.symbol)
        qty = math.floor(order.notional / price)
        if qty < 1:
            return  # 1주 미만(소액)은 스킵
        body = {
            "symbol": order.symbol,
            "side": "BUY" if order.side == "buy" else "SELL",
            "orderType": "MARKET",
            "quantity": qty,
            "timeInForce": "DAY",
            "clientOrderId": self._client_order_id_fn(),
        }
        resp = self.client.post(
            "/api/v1/orders",
            json=body,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "X-Tossinvest-Account": str(seq),
            },
        )
        result = self._result(resp)
        if not result.get("orderId"):
            raise ValueError(f"TOSS 주문 실패: {result}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_toss_broker.py -q`
Expected: PASS (12 passed).

- [ ] **Step 5: Run full suite**

Run: `uv run pytest -q`
Expected: PASS (모든 기존 테스트 + 신규 12개 그린).

- [ ] **Step 6: Commit**

```bash
git add ohmystock/core/broker/toss.py tests/test_toss_broker.py
git commit -m "feat(toss): add submit_order (price->floor qty, MARKET, clientOrderId)"
```

---

### Task 4: 실 스모크 스크립트 + README + import 가드 테스트

**Files:**
- Create: `scripts/toss_smoke.py`
- Modify: `README.md` (TOSS 섹션 추가)
- Test: `tests/test_toss_smoke_script.py`

**Interfaces:**
- Consumes: `TossBroker`, `Order`.
- Produces: `scripts/toss_smoke.py` with `build_parser() -> argparse.ArgumentParser` and `main(argv=None) -> int`. `--help`는 키 없이 동작; 주문은 `--order SYMBOL NOTIONAL` 명시 + `--i-understand-real-money` 플래그가 있어야만 실행.

- [ ] **Step 1: Write the failing test**

`tests/test_toss_smoke_script.py`:
```python
import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "toss_smoke.py"


def _load():
    spec = importlib.util.spec_from_file_location("toss_smoke", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_parser_defaults_no_order():
    mod = _load()
    args = mod.build_parser().parse_args([])
    assert args.order is None
    assert args.i_understand_real_money is False


def test_parser_accepts_order():
    mod = _load()
    args = mod.build_parser().parse_args(
        ["--order", "AAPL", "500", "--i-understand-real-money"])
    assert args.order == ["AAPL", "500"]
    assert args.i_understand_real_money is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_toss_smoke_script.py -q`
Expected: FAIL (`scripts/toss_smoke.py` 없음 → import 에러).

- [ ] **Step 3: Write the script**

`scripts/toss_smoke.py`:
```python
"""TOSS Invest 실계좌 스모크 (사용자 실행 전용).

경고: 토스증권 Open API는 모의투자(샌드박스)가 없어 모든 주문이 실제 체결된다.
주문은 --order SYMBOL NOTIONAL 와 --i-understand-real-money 를 함께 줄 때만 실행한다.

준비:
  export TOSS_CLIENT_ID=...   TOSS_CLIENT_SECRET=...
  (선택) export TOSS_ACCOUNT_SEQ=...

사용:
  uv run python scripts/toss_smoke.py                 # 토큰+계좌+보유만 확인(안전)
  uv run python scripts/toss_smoke.py --order AAPL 50 --i-understand-real-money
"""

import argparse
import sys

from ohmystock.core.broker.base import Order
from ohmystock.core.broker.toss import TossBroker


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="toss_smoke")
    p.add_argument("--currency", default="usd")
    p.add_argument("--order", nargs=2, metavar=("SYMBOL", "NOTIONAL"), default=None,
                   help="소량 실주문 (실거래!). 예: --order AAPL 50")
    p.add_argument("--i-understand-real-money", action="store_true",
                   help="실제 돈이 나가는 것을 이해함 — 주문 실행에 필수")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    broker = TossBroker(currency=args.currency)
    print("[1] 토큰 발급 …")
    broker.issue_token()
    print("    OK")
    print(f"[2] accountSeq = {broker._resolve_account_seq()}")
    acct = broker.get_account()
    print(f"[3] account: equity={acct.equity} cash={acct.cash}")
    print(f"[4] positions: {broker.get_positions()}")

    if args.order:
        if not args.i_understand_real_money:
            print("거부: 실주문은 --i-understand-real-money 가 필요합니다 (실거래).",
                  file=sys.stderr)
            return 2
        symbol, notional = args.order[0], float(args.order[1])
        print(f"[5] 실주문 제출: BUY {symbol} ~{notional} (실거래!)")
        broker.submit_order(Order(symbol=symbol, side="buy", notional=notional))
        print("    제출됨")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_toss_smoke_script.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Verify --help works without keys**

Run: `uv run python scripts/toss_smoke.py --help`
Expected: argparse 도움말 출력, 종료코드 0 (네트워크/키 불필요).

- [ ] **Step 6: Add README section**

`README.md`에 적절한 위치(예: 브로커/실계좌 섹션)에 추가:
```markdown
### 토스증권(TOSS Invest) 어댑터

`ohmystock/core/broker/toss.py::TossBroker` 는 토스증권 Open API(`https://openapi.tossinvest.com`)를
Broker 프로토콜로 구현한다. OAuth client_credentials 토큰을 자동 갱신하고,
주문은 현재가로 `floor(notional/lastPrice)` 정수 수량을 계산해 시장가로 제출한다.

**주의: TOSS는 모의투자(샌드박스)가 없어 모든 주문이 실제 체결된다.** 에이전트/자동화는
실주문을 내지 않으며, 실계좌 검증은 사용자가 직접 실행한다:

```bash
export TOSS_CLIENT_ID=...  TOSS_CLIENT_SECRET=...
uv run python scripts/toss_smoke.py            # 토큰+계좌+보유 확인(안전)
uv run python scripts/toss_smoke.py --order AAPL 50 --i-understand-real-money  # 소량 실주문
```
```

- [ ] **Step 7: Run full suite**

Run: `uv run pytest -q`
Expected: PASS (전체 그린).

- [ ] **Step 8: Commit**

```bash
git add scripts/toss_smoke.py tests/test_toss_smoke_script.py README.md
git commit -m "feat(toss): add user-run real smoke script + README"
```

---

## 완료 후

- 적대적 안전 리뷰(실거래 브로커 — 실주문이 명시적 의도 없이 새어나갈 경로 점검) 후 main 머지·푸시.
- ROADMAP에 TOSS 어댑터 항목 추가/완료 표기.
