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

    def get_account(self) -> Account:
        """주식잔고조회로 총평가금액(equity)과 예수금(cash)을 가져온다."""
        data = self._inquire_balance()
        summary = data["output2"][0]
        return Account(
            equity=float(summary["tot_evlu_amt"]),
            cash=float(summary["dnca_tot_amt"]),
        )

    def get_positions(self) -> dict[str, float]:
        """종목코드 -> 평가금액(원). 평가금액 0 이하 종목은 제외."""
        data = self._inquire_balance()
        return {
            row["pdno"]: float(row["evlu_amt"])
            for row in data["output1"]
            if float(row.get("evlu_amt", 0)) > 0
        }

    def _inquire_balance(self) -> dict:
        resp = self.client.get(
            _BALANCE_PATH, headers=self._auth_headers(_BALANCE_TR_ID)
        )
        resp.raise_for_status()
        return resp.json()

    def submit_order(self, order: Order) -> None:
        """현금 주문 전송.

        주의: KIS 주문은 수량(ORD_QTY) 기반이며 notional(금액) 기반이 아니다.
        프로덕션에서는 실시간 호가로 notional -> 수량 변환이 반드시 필요하다.
        이 어댑터에서는 단순화하여 side 에 따라 올바른 tr_id 헤더와 경로/메서드만
        보장하고, notional 의도는 본문에 그대로 실어 보낸다.
        """
        tr_id = _BUY_TR_ID if order.side == "buy" else _SELL_TR_ID
        cano = (self.account_no or "").split("-")[0]
        body = {
            "CANO": cano,
            "PDNO": order.symbol,
            "ORD_DVSN": "01",
            "ORD_UNPR": "0",
            "side": order.side,
            "notional": order.notional,
        }
        resp = self.client.post(
            _ORDER_PATH, headers=self._auth_headers(tr_id), json=body
        )
        resp.raise_for_status()
