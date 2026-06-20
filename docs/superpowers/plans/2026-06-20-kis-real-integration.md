# KIS 어댑터 실연동 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 인터페이스만 맞춰둔 `KISBroker`를 프로덕션급으로 재작성한다(모의/실전 스위치 · OAuth 자동 갱신 · 실 잔고/현재가 스키마 · notional→정수수량 · hashkey 옵션), 오프라인 검증 + 사용자용 실 스모크.

**Architecture:** `ohmystock/core/broker/kis.py`의 `KISBroker`를 단계적으로 재작성한다. `paper=True`(기본)면 모의 도메인+`V*` tr_id, `paper=False`면 실전+`T*`. 토큰은 만료시각을 캐시해 자동 갱신하고, 주문은 현재가(inquire-price)로 `floor(notional/현재가)` 정수 수량을 계산해 시장가로 제출하며 `rt_cd`로 성공을 판정한다. 모든 테스트는 `httpx.MockTransport`로 네트워크 없이 돈다. 실 모의투자 스모크는 사용자가 실행한다.

**Tech Stack:** Python 3.11, httpx, pytest, uv.

## Global Constraints

- 실행: `uv run pytest <path> -q` (VIRTUAL_ENV 3.9.11 경고 무해).
- `KISBroker`는 standalone(테스트 외 사용처 없음). `Account(equity, cash)`·`Order(symbol, side, notional)`는 `ohmystock/core/broker/base.py` 재사용.
- base URL: 모의 `https://openapivts.koreainvestment.com:29443` / 실전 `https://openapi.koreainvestment.com:9443`.
- 토큰: `POST /oauth2/tokenP` body `{grant_type:"client_credentials", appkey, appsecret}` → `access_token`, `access_token_token_expired`("%Y-%m-%d %H:%M:%S") 또는 `expires_in`(초).
- tr_id: 매수 `TTTC0802U`/`VTTC0802U`, 매도 `TTTC0801U`/`VTTC0801U`, 잔고 `TTTC8434R`/`VTTC8434R` (실전/모의). 현재가 `FHKST01010100`.
- 경로: 잔고 `/uapi/domestic-stock/v1/trading/inquire-balance`, 현재가 `/uapi/domestic-stock/v1/quotations/inquire-price`, 주문 `/uapi/domestic-stock/v1/trading/order-cash`, hashkey `/uapi/hashkey`.
- 주문 본문: `CANO, ACNT_PRDT_CD, PDNO, ORD_DVSN="01"(시장가), ORD_QTY=str(int), ORD_UNPR="0"`. 성공 `rt_cd=="0"`.
- 계좌번호 `"12345678-01"` → `CANO="12345678"`, `ACNT_PRDT_CD="01"`.
- env 폴백: `KIS_APP_KEY`/`KIS_APP_SECRET`/`KIS_ACCOUNT_NO`. 각 태스크 끝 커밋(atinjin).

---

### Task 1: 모드(paper/live) + 토큰 라이프사이클

**Files:**
- Modify: `ohmystock/core/broker/kis.py` (상수 블록 + `__init__` + `issue_token` 교체, `_ensure_token`/`_tr`/`_cano`/`_acnt_prdt_cd` 추가, `_auth_headers`에 hashkey 인자)
- Test: `tests/test_kis_broker.py` (token 테스트 교체 + mode/ensure 테스트 추가)

**Interfaces:**
- Produces: `KISBroker(app_key=None, app_secret=None, account_no=None, *, paper=True, base_url=None, client=None, access_token=None, token_expires_at=None, use_hashkey=False, now=None)`; `issue_token() -> str` (만료시각 저장); `_ensure_token() -> None`; `_tr(kind: "buy"|"sell"|"balance") -> str`; 속성 `paper`, `use_hashkey`, `token_expires_at`, `_cano`, `_acnt_prdt_cd`.
- Consumes: 다음 태스크들이 `_tr`, `_ensure_token`, `_cano`, `_acnt_prdt_cd`, `_auth_headers(tr_id, hashkey=None)`를 사용.

- [ ] **Step 1: 테스트 교체/추가**

`tests/test_kis_broker.py` 상단 import에 추가:
```python
from datetime import datetime, timedelta
```
기존 `test_issue_token_sets_and_returns_token`를 아래로 **교체**하고, 그 아래 새 테스트들을 추가:
```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_kis_broker.py -q`
Expected: FAIL (`token_expires_at`/`_ensure_token`/`_tr`/`_cano` 미존재).

- [ ] **Step 3: kis.py 상단 상수 + 생성자 + 토큰 교체**

`ohmystock/core/broker/kis.py`의 **맨 위부터 `__init__` 끝까지**(현재 import~생성자)와 `_auth_headers`/`issue_token`를 아래로 교체. **get_account / get_positions / _inquire_balance / submit_order 본문은 이번 태스크에서 건드리지 않는다**(Task 2·3에서 교체):
```python
"""한국투자증권(KIS) Open API 브로커 어댑터.

모의투자(paper) 우선. paper=True면 모의 도메인+V* tr_id, paper=False면 실전+T*.
httpx.Client 주입으로 httpx.MockTransport 오프라인 테스트가 가능하다. 환경변수
KIS_APP_KEY / KIS_APP_SECRET / KIS_ACCOUNT_NO 폴백을 지원한다.
"""

import math
import os
from datetime import datetime, timedelta

import httpx

from ohmystock.core.broker.base import Account, Order

_PAPER_URL = "https://openapivts.koreainvestment.com:29443"
_LIVE_URL = "https://openapi.koreainvestment.com:9443"

_TOKEN_PATH = "/oauth2/tokenP"
_HASHKEY_PATH = "/uapi/hashkey"
_BALANCE_PATH = "/uapi/domestic-stock/v1/trading/inquire-balance"
_PRICE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-price"
_ORDER_PATH = "/uapi/domestic-stock/v1/trading/order-cash"

_PRICE_TR_ID = "FHKST01010100"
_REFRESH_MARGIN = timedelta(seconds=60)

# 옛 상수 — Task 1에서 옛 _inquire_balance/submit_order가 임시로 참조한다.
# Task 2가 _BALANCE_TR_ID 사용을 없애고, Task 3가 _BUY_TR_ID/_SELL_TR_ID를 없앤다.
_BUY_TR_ID = "TTTC0802U"
_SELL_TR_ID = "TTTC0801U"
_BALANCE_TR_ID = "TTTC8434R"

# kind -> (모의 tr_id, 실전 tr_id)
_TR = {
    "buy": ("VTTC0802U", "TTTC0802U"),
    "sell": ("VTTC0801U", "TTTC0801U"),
    "balance": ("VTTC8434R", "TTTC8434R"),
}


class KISBroker:
    """한국투자증권 Open API 어댑터 (Broker 프로토콜)."""

    def __init__(
        self,
        app_key=None,
        app_secret=None,
        account_no=None,
        *,
        paper=True,
        base_url=None,
        client=None,
        access_token=None,
        token_expires_at=None,
        use_hashkey=False,
        now=None,
    ):
        self.app_key = app_key or os.environ.get("KIS_APP_KEY")
        self.app_secret = app_secret or os.environ.get("KIS_APP_SECRET")
        self.account_no = account_no or os.environ.get("KIS_ACCOUNT_NO")
        self.paper = paper
        self.use_hashkey = use_hashkey
        self.access_token = access_token
        self.token_expires_at = token_expires_at
        self._now = now or datetime.now
        if base_url is None:
            base_url = _PAPER_URL if paper else _LIVE_URL
        self.client = client or httpx.Client(base_url=base_url)

    def _tr(self, kind: str) -> str:
        paper_id, live_id = _TR[kind]
        return paper_id if self.paper else live_id

    @property
    def _cano(self) -> str:
        return (self.account_no or "").split("-")[0]

    @property
    def _acnt_prdt_cd(self) -> str:
        parts = (self.account_no or "").split("-")
        return parts[1] if len(parts) > 1 else "01"

    def _auth_headers(self, tr_id: str, hashkey: str | None = None) -> dict:
        headers = {
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key or "",
            "appsecret": self.app_secret or "",
            "tr_id": tr_id,
            "content-type": "application/json",
        }
        if hashkey:
            headers["hashkey"] = hashkey
        return headers

    def issue_token(self) -> str:
        """OAuth2 접근토큰 발급 + 만료시각 저장."""
        resp = self.client.post(
            _TOKEN_PATH,
            json={
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
            },
        )
        resp.raise_for_status()
        j = resp.json()
        self.access_token = j["access_token"]
        expired = j.get("access_token_token_expired")
        if expired:
            self.token_expires_at = datetime.strptime(expired, "%Y-%m-%d %H:%M:%S")
        else:
            self.token_expires_at = self._now() + timedelta(seconds=int(j.get("expires_in", 0)))
        return self.access_token

    def _ensure_token(self) -> None:
        if self.access_token is None:
            self.issue_token()
            return
        if self.token_expires_at is not None and \
                self._now() >= self.token_expires_at - _REFRESH_MARGIN:
            self.issue_token()
```
**중요:** 옛 `get_account` / `get_positions` / `_inquire_balance` / `submit_order` 본문과 옛 상수(`_BUY_TR_ID`/`_SELL_TR_ID`/`_BALANCE_TR_ID`)는 **그대로 둔다**(이번 태스크에서 건드리지 않음). 옛 메서드들은 이 옛 상수를 참조해 계속 동작하므로, 기존 잔고/포지션/주문 테스트(실전 tr_id `TTTC*` 가정)가 그대로 통과한다. 옛 `_auth_headers`만 위처럼 hashkey 인자 추가형으로 교체되며, 옛 호출부 `self._auth_headers(tr_id)`는 hashkey 기본값(None)으로 호환된다. _inquire_balance의 쿼리 파라미터·모의 tr_id는 Task 2, submit_order의 수량 변환·모의 tr_id는 Task 3에서 교체한다.

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_kis_broker.py -q`
Expected: PASS (기존 잔고/포지션/주문/env 테스트 + 신규 token/mode 테스트 모두 그린).

- [ ] **Step 5: 커밋**

```bash
git add ohmystock/core/broker/kis.py tests/test_kis_broker.py
git commit -m "feat(kis): add paper/live mode switch + OAuth token lifecycle"
```

---

### Task 2: 잔고 조회 (쿼리 파라미터 + 모의 tr_id)

**Files:**
- Modify: `ohmystock/core/broker/kis.py` (`_inquire_balance` 교체, `_ensure_token` 호출 추가)
- Test: `tests/test_kis_broker.py` (잔고 테스트에 tr_id·파라미터 단언 추가)

**Interfaces:**
- Consumes: Task 1의 `_ensure_token`, `_tr("balance")`, `_cano`, `_acnt_prdt_cd`, `_auth_headers`.
- Produces: `_inquire_balance()`가 쿼리 파라미터 포함 GET을 보내고 `output1`/`output2`를 반환(get_account/get_positions는 시그니처 유지).

- [ ] **Step 1: 잔고 테스트 강화**

`tests/test_kis_broker.py`의 기존 `test_get_account_parses_output2`를 아래로 **교체**(tr_id·CANO 파라미터 단언 추가):
```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_kis_broker.py::test_get_account_parses_output2_with_params -q`
Expected: FAIL (`captured["CANO"]`가 None — 옛 `_inquire_balance`는 파라미터 미전송).

- [ ] **Step 3: `_inquire_balance` 교체**

`ohmystock/core/broker/kis.py`의 `_inquire_balance` 메서드를 아래로 교체:
```python
    def _inquire_balance(self) -> dict:
        self._ensure_token()
        resp = self.client.get(
            _BALANCE_PATH,
            headers=self._auth_headers(self._tr("balance")),
            params={
                "CANO": self._cano,
                "ACNT_PRDT_CD": self._acnt_prdt_cd,
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "",
                "INQR_DVSN": "02",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "00",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            },
        )
        resp.raise_for_status()
        return resp.json()
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_kis_broker.py -q`
Expected: PASS (잔고/포지션 포함 전부 그린; `test_get_positions_excludes_zero_value`는 그대로 통과).

- [ ] **Step 5: 커밋**

```bash
git add ohmystock/core/broker/kis.py tests/test_kis_broker.py
git commit -m "feat(kis): inquire-balance with required query params + paper tr_id"
```

---

### Task 3: 현재가 + 주문 (notional→정수수량, rt_cd, hashkey 옵션)

**Files:**
- Modify: `ohmystock/core/broker/kis.py` (`_current_price`·`_hashkey` 추가, `submit_order` 전면 교체)
- Test: `tests/test_kis_broker.py` (옛 submit 테스트 2개 교체 + 신규 주문 테스트)

**Interfaces:**
- Consumes: Task 1·2의 `_ensure_token`, `_tr`, `_cano`, `_acnt_prdt_cd`, `_auth_headers(tr_id, hashkey)`.
- Produces: `_current_price(symbol) -> float` (inquire-price → `output.stck_prpr`, 0 이하면 예외); `_hashkey(body) -> str`; `submit_order(order)` (현재가로 `floor(notional/price)`, `qty<1` 스킵, ORD_DVSN="01", rt_cd 판정, use_hashkey 시 hashkey 헤더).

- [ ] **Step 1: 옛 submit 테스트 교체 + 신규 테스트**

`tests/test_kis_broker.py`의 기존 `test_submit_order_buy_uses_buy_tr_id`와 `test_submit_order_sell_uses_sell_tr_id` 두 개를 아래 묶음으로 **교체**:
```python
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
```
파일 상단 import에 `import json` 이 없으면 추가한다.

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_kis_broker.py -q`
Expected: FAIL (`_current_price`/`_hashkey` 미존재, 옛 submit_order는 inquire-price 미처리로 깨짐).

- [ ] **Step 3: `_current_price`·`_hashkey` 추가 + `submit_order` 교체**

`ohmystock/core/broker/kis.py`에서 `_inquire_balance` 아래(또는 클래스 말미)에 `_current_price`·`_hashkey`를 추가하고, 기존 `submit_order` 전체를 아래로 교체한다. 또한 이제 아무도 참조하지 않는 옛 상수 `_BUY_TR_ID`/`_SELL_TR_ID`/`_BALANCE_TR_ID` 정의를 삭제한다:
```python
    def _current_price(self, symbol: str) -> float:
        self._ensure_token()
        resp = self.client.get(
            _PRICE_PATH,
            headers=self._auth_headers(_PRICE_TR_ID),
            params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol},
        )
        resp.raise_for_status()
        price = float(resp.json()["output"]["stck_prpr"])
        if price <= 0:
            raise ValueError(f"KIS {symbol} 현재가 비정상({price}) — 주문 불가(정류 등)")
        return price

    def _hashkey(self, body: dict) -> str:
        resp = self.client.post(
            _HASHKEY_PATH,
            json=body,
            headers={
                "appkey": self.app_key or "",
                "appsecret": self.app_secret or "",
                "content-type": "application/json",
            },
        )
        resp.raise_for_status()
        return resp.json()["HASH"]

    def submit_order(self, order: Order) -> None:
        """시장가 현금 주문. notional을 현재가로 정수 수량 변환해 제출한다."""
        self._ensure_token()
        price = self._current_price(order.symbol)
        qty = math.floor(order.notional / price)
        if qty < 1:
            return  # 1주 미만(소액)은 스킵
        body = {
            "CANO": self._cano,
            "ACNT_PRDT_CD": self._acnt_prdt_cd,
            "PDNO": order.symbol,
            "ORD_DVSN": "01",       # 시장가
            "ORD_QTY": str(qty),
            "ORD_UNPR": "0",
        }
        hashkey = self._hashkey(body) if self.use_hashkey else None
        tr_id = self._tr("buy") if order.side == "buy" else self._tr("sell")
        resp = self.client.post(
            _ORDER_PATH, json=body, headers=self._auth_headers(tr_id, hashkey)
        )
        resp.raise_for_status()
        j = resp.json()
        if j.get("rt_cd") != "0":
            raise ValueError(f"KIS 주문 실패 [{j.get('rt_cd')}] {j.get('msg1')}")
```

- [ ] **Step 4: 통과 확인 + 전체 스위트**

Run: `uv run pytest tests/test_kis_broker.py -q`
Expected: PASS (전체 KIS 테스트 그린).
Run: `uv run pytest -q`
Expected: PASS (전 프로젝트 그린).

- [ ] **Step 5: 커밋**

```bash
git add ohmystock/core/broker/kis.py tests/test_kis_broker.py
git commit -m "feat(kis): submit_order with notional->qty, rt_cd check, optional hashkey"
```

---

### Task 4: 실 모의투자 스모크 스크립트 + README

**Files:**
- Create: `scripts/kis_smoke.py`
- Modify: `README.md` (KIS 섹션 추가)
- Test: `tests/test_kis_smoke_script.py`

**Interfaces:**
- Consumes: `KISBroker`, `Order`.
- Produces: `scripts/kis_smoke.py` with `build_parser() -> argparse.ArgumentParser` and `main(argv=None, broker=None) -> int`. `--help`는 키 없이 동작; 실주문은 `--order SYMBOL NOTIONAL` + `--i-understand-real-money` 둘 다 있어야 실행(기본은 모의투자라 실거래 아님이지만 동일 가드 적용).

- [ ] **Step 1: 실패 테스트**

`tests/test_kis_smoke_script.py`:
```python
import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "kis_smoke.py"


def _load():
    spec = importlib.util.spec_from_file_location("kis_smoke", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeBroker:
    def __init__(self):
        self.orders = []

    def issue_token(self):
        return "tok"

    def get_account(self):
        from ohmystock.core.broker.base import Account
        return Account(equity=1000000.0, cash=1000000.0)

    def get_positions(self):
        return {}

    def submit_order(self, order):
        self.orders.append(order)


def test_parser_defaults():
    args = _load().build_parser().parse_args([])
    assert args.order is None
    assert args.live is False


def test_main_no_order_zero_submits():
    fake = _FakeBroker()
    rc = _load().main([], broker=fake)
    assert rc == 0
    assert fake.orders == []


def test_main_order_without_flag_rejected():
    fake = _FakeBroker()
    rc = _load().main(["--order", "005930", "50000"], broker=fake)
    assert rc == 2
    assert fake.orders == []


def test_main_order_with_flag_submits():
    fake = _FakeBroker()
    rc = _load().main(["--order", "005930", "50000", "--i-understand-real-money"],
                      broker=fake)
    assert rc == 0
    assert len(fake.orders) == 1
    assert fake.orders[0].symbol == "005930"
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_kis_smoke_script.py -q`
Expected: FAIL (`scripts/kis_smoke.py` 없음).

- [ ] **Step 3: 스크립트 작성**

`scripts/kis_smoke.py`:
```python
"""KIS 모의투자 스모크 (사용자 실행 전용).

기본은 모의투자(paper). --live 를 줘야 실전 도메인을 쓴다.
실주문은 --order SYMBOL NOTIONAL 와 --i-understand-real-money 가 함께 있어야 실행한다.

준비:
  export KIS_APP_KEY=...  KIS_APP_SECRET=...  KIS_ACCOUNT_NO=12345678-01

사용:
  uv run python scripts/kis_smoke.py                 # 토큰+잔고+보유만(안전)
  uv run python scripts/kis_smoke.py --order 005930 50000 --i-understand-real-money
"""

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ohmystock.core.broker.base import Order
from ohmystock.core.broker.kis import KISBroker


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kis_smoke")
    p.add_argument("--live", action="store_true", help="실전 도메인 사용(기본: 모의투자)")
    p.add_argument("--order", nargs=2, metavar=("SYMBOL", "NOTIONAL"), default=None,
                   help="소량 주문. 예: --order 005930 50000")
    p.add_argument("--i-understand-real-money", action="store_true",
                   help="실주문 실행에 필수")
    return p


def main(argv=None, broker=None) -> int:
    args = build_parser().parse_args(argv)

    if args.order and not args.i_understand_real_money:
        print("거부: 실주문은 --i-understand-real-money 가 필요합니다.", file=sys.stderr)
        return 2

    if broker is None:
        broker = KISBroker(paper=not args.live)
    print(f"[1] 토큰 발급 … (paper={getattr(broker, 'paper', None)})")
    broker.issue_token()
    print("    OK")
    acct = broker.get_account()
    print(f"[2] account: equity={acct.equity} cash={acct.cash}")
    print(f"[3] positions: {broker.get_positions()}")

    if args.order:
        symbol, notional = args.order[0], float(args.order[1])
        print(f"[4] 주문 제출: BUY {symbol} ~{notional}")
        broker.submit_order(Order(symbol=symbol, side="buy", notional=notional))
        print("    제출됨")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 통과 확인 + --help**

Run: `uv run pytest tests/test_kis_smoke_script.py -q`
Expected: PASS (4 passed).
Run: `uv run python scripts/kis_smoke.py --help`
Expected: 도움말 출력, 종료코드 0(키 불필요).

- [ ] **Step 5: README 섹션 추가**

`README.md`의 적절한 위치(브로커/실거래 섹션)에 추가:
```markdown
### 한국투자증권(KIS) 어댑터

`ohmystock/core/broker/kis.py::KISBroker` 는 KIS Open API를 Broker 프로토콜로 구현한다.
`paper=True`(기본)면 모의투자 도메인+`V*` tr_id, `paper=False`면 실전이다. OAuth 토큰을
자동 갱신하고, 주문은 현재가로 `floor(notional/현재가)` 정수 수량을 계산해 시장가로 제출한다.

실 검증(모의투자 권장)은 사용자가 직접 실행한다:

```bash
export KIS_APP_KEY=...  KIS_APP_SECRET=...  KIS_ACCOUNT_NO=12345678-01
uv run python scripts/kis_smoke.py            # 토큰+잔고+보유(안전)
uv run python scripts/kis_smoke.py --order 005930 50000 --i-understand-real-money
```
```

- [ ] **Step 6: 전체 스위트 + 커밋**

Run: `uv run pytest -q`
Expected: PASS (전체 그린).

```bash
git add scripts/kis_smoke.py tests/test_kis_smoke_script.py README.md
git commit -m "feat(kis): add paper smoke script + README"
```

---

## 완료 후

- 적대적 안전 리뷰(실거래 가능 브로커 — 모드/수량/주문 정확성, 실주문 가드) 후 main 머지·푸시.
- ROADMAP의 "🔴 KIS 어댑터 실연동 검증" 항목 완료 표기(실 end-to-end 스모크는 사용자 몫으로 명시).
