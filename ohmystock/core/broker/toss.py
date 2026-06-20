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
        if resp.status_code >= 400:
            raise ValueError(f"TOSS API 오류 HTTP {resp.status_code}: {resp.text}")
        j = resp.json()
        if "result" not in j:
            raise ValueError(f"TOSS 응답에 result 없음: {j}")
        return j["result"]

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
        cur = self.currency.upper()
        for item in holdings.get("items", []):
            if float(item.get("quantity") or 0) <= 0:
                continue
            # 통화 슬리브 필터: self.currency(기본 usd)와 같은 종목만.
            # (다통화 계좌에서 원·달러가 섞여 equity와 불일치하는 것을 방지)
            if str(item.get("currency", "")).upper() != cur:
                continue
            mv = item.get("marketValue", {})
            out[item["symbol"]] = float(mv.get("amount") or 0.0)
        return out

    # --- 시세 / 주문 --------------------------------------------------------
    def _last_price(self, symbol: str) -> float:
        resp = self.client.get(
            "/api/v1/prices",
            params={"symbols": symbol},
            headers={"Authorization": f"Bearer {self.access_token}"},
        )
        for row in self._result(resp):
            if row.get("symbol") == symbol:
                price = float(row["lastPrice"])
                if price <= 0:
                    raise ValueError(
                        f"TOSS {symbol} 현재가 비정상({price}) — 주문 불가(정류/장전 등)")
                return price
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
