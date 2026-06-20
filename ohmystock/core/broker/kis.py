"""한국투자증권(KIS) Open API 브로커 어댑터.

모의투자(paper) 우선. paper=True면 모의 도메인+V* tr_id, paper=False면 실전+T*.
httpx.Client 주입으로 httpx.MockTransport 오프라인 테스트가 가능하다. 환경변수
KIS_APP_KEY / KIS_APP_SECRET / KIS_ACCOUNT_NO 폴백을 지원한다.
"""

import math
import os
import time
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
        sleep=None,
        max_retries=3,
        retry_delay=0.5,
    ):
        self.app_key = app_key or os.environ.get("KIS_APP_KEY")
        self.app_secret = app_secret or os.environ.get("KIS_APP_SECRET")
        self.account_no = account_no or os.environ.get("KIS_ACCOUNT_NO")
        self.paper = paper
        self.use_hashkey = use_hashkey
        self.access_token = access_token
        self.token_expires_at = token_expires_at
        self._now = now or datetime.now
        self._sleep = sleep or time.sleep
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        if base_url is None:
            base_url = _PAPER_URL if paper else _LIVE_URL
        self.client = client or httpx.Client(base_url=base_url)

    def _send(self, method: str, path: str, **kwargs) -> httpx.Response:
        """KIS 호출. EGW00201(초당 거래건수 초과) 시 짧게 대기 후 재시도한다.

        EGW00201은 요청이 실행 전에 거부된 것이라 주문(POST)에도 재시도가 안전하다
        (체결 중복 위험 없음). 다른 오류는 즉시 반환해 호출부가 처리한다.
        """
        resp = self.client.request(method, path, **kwargs)
        for _ in range(self._max_retries):
            if resp.status_code != 500:
                break
            try:
                if resp.json().get("msg_cd") != "EGW00201":
                    break
            except Exception:
                break
            self._sleep(self._retry_delay)
            resp = self.client.request(method, path, **kwargs)
        return resp

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
        self._ensure_token()
        resp = self._send(
            "GET",
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

    def _current_price(self, symbol: str) -> float:
        self._ensure_token()
        resp = self._send(
            "GET",
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
        resp = self._send(
            "POST", _ORDER_PATH, json=body, headers=self._auth_headers(tr_id, hashkey)
        )
        resp.raise_for_status()
        j = resp.json()
        if j.get("rt_cd") != "0":
            raise ValueError(f"KIS 주문 실패 [{j.get('rt_cd')}] {j.get('msg1')}")
