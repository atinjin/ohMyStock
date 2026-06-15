import os

import httpx

from ohmystock.core.broker.base import Account, Order


class AlpacaBroker:
    """Alpaca REST 어댑터 (US, paper/live). Broker 프로토콜 구현.

    테스트는 httpx.MockTransport 로 만든 client 를 주입해 오프라인으로 검증한다.
    """

    def __init__(
        self,
        api_key: str | None = None,
        secret_key: str | None = None,
        base_url: str = "https://paper-api.alpaca.markets",
        client: httpx.Client | None = None,
    ):
        self.api_key = api_key or os.environ.get("ALPACA_API_KEY")
        self.secret_key = secret_key or os.environ.get("ALPACA_SECRET_KEY")
        headers = {
            "APCA-API-KEY-ID": self.api_key or "",
            "APCA-API-SECRET-KEY": self.secret_key or "",
        }
        self.client = client or httpx.Client(base_url=base_url, headers=headers)

    def get_account(self) -> Account:
        resp = self.client.get("/v2/account")
        resp.raise_for_status()
        j = resp.json()
        return Account(equity=float(j["equity"]), cash=float(j["cash"]))

    def get_positions(self) -> dict[str, float]:
        resp = self.client.get("/v2/positions")
        resp.raise_for_status()
        return {p["symbol"]: float(p["market_value"]) for p in resp.json()}

    def submit_order(self, order: Order) -> None:
        resp = self.client.post(
            "/v2/orders",
            json={
                "symbol": order.symbol,
                "notional": round(order.notional, 2),
                "side": order.side,
                "type": "market",
                "time_in_force": "day",
            },
        )
        resp.raise_for_status()
