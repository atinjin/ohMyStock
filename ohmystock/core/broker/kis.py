"""한국투자증권(KIS) Open API 브로커 어댑터.

한국 시장 확장을 위한 Broker 프로토콜 구현. httpx 클라이언트를 주입할 수
있어 httpx.MockTransport 로 완전히 오프라인 테스트가 가능하다. 환경변수
KIS_APP_KEY / KIS_APP_SECRET / KIS_ACCOUNT_NO 로 키 폴백을 지원한다.
"""

import os

import httpx

from ohmystock.core.broker.base import Account, Order

_BUY_TR_ID = "TTTC0802U"   # 현금 매수 주문
_SELL_TR_ID = "TTTC0801U"  # 현금 매도 주문
_BALANCE_TR_ID = "TTTC8434R"  # 주식잔고조회

_TOKEN_PATH = "/oauth2/tokenP"
_BALANCE_PATH = "/uapi/domestic-stock/v1/trading/inquire-balance"
_ORDER_PATH = "/uapi/domestic-stock/v1/trading/order-cash"


class KISBroker:
    """한국투자증권 Open API 어댑터 (Broker 프로토콜)."""

    def __init__(
        self,
        app_key=None,
        app_secret=None,
        account_no=None,
        base_url="https://openapi.koreainvestment.com:9443",
        client=None,
        access_token=None,
    ):
        self.app_key = app_key or os.environ.get("KIS_APP_KEY")
        self.app_secret = app_secret or os.environ.get("KIS_APP_SECRET")
        self.account_no = account_no or os.environ.get("KIS_ACCOUNT_NO")
        self.access_token = access_token  # issue_token() 호출 전엔 None 가능
        self.client = client or httpx.Client(base_url=base_url)

    def _auth_headers(self, tr_id: str) -> dict:
        return {
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key or "",
            "appsecret": self.app_secret or "",
            "tr_id": tr_id,
            "content-type": "application/json",
        }

    def issue_token(self) -> str:
        """OAuth2 접근토큰 발급 후 self.access_token 에 저장하고 반환."""
        resp = self.client.post(
            _TOKEN_PATH,
            json={
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
            },
        )
        resp.raise_for_status()
        self.access_token = resp.json()["access_token"]
        return self.access_token

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
