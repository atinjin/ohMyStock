from ohmystock.core.broker.base import Account, Order


class PaperBroker:
    """네트워크 없는 인메모리 체결 시뮬레이터. Broker 프로토콜 구현."""

    def __init__(self, cash: float):
        self.cash = cash
        self.shares: dict[str, float] = {}
        self.prices: dict[str, float] = {}

    def set_prices(self, prices: dict[str, float]) -> None:
        self.prices.update(prices)

    def _price(self, sym: str) -> float:
        if sym not in self.prices:
            raise ValueError(f"가격 미확인 종목: {sym}")
        return self.prices[sym]

    def get_positions(self) -> dict[str, float]:
        return {
            sym: qty * self._price(sym)
            for sym, qty in self.shares.items()
            if qty > 0
        }

    def get_account(self) -> Account:
        positions_value = sum(self.get_positions().values())
        return Account(equity=self.cash + positions_value, cash=self.cash)

    def submit_order(self, order: Order) -> None:
        price = self._price(order.symbol)
        if order.side == "buy":
            if self.cash < order.notional:
                raise ValueError(
                    f"현금 부족: 필요 {order.notional}, 보유 {self.cash}"
                )
            self.cash -= order.notional
            self.shares[order.symbol] = (
                self.shares.get(order.symbol, 0.0) + order.notional / price
            )
        elif order.side == "sell":
            held = self.shares.get(order.symbol, 0.0)
            shares_to_sell = min(order.notional / price, held)
            self.cash += shares_to_sell * price
            self.shares[order.symbol] = held - shares_to_sell
        else:
            raise ValueError(f"알 수 없는 side: {order.side}")
