from ohmystock.config import Config
from ohmystock.core.broker.base import Order


class RiskGuard:
    """고점 대비 낙폭(MDD) 기반 리스크 가드."""

    def __init__(self, config: Config, peak_equity: float | None = None):
        self.config = config
        self.peak = peak_equity or 0.0

    def update(self, equity: float) -> None:
        self.peak = max(self.peak, equity)

    def drawdown(self, equity: float) -> float:
        if self.peak <= 0:
            return 0.0
        return (self.peak - equity) / self.peak

    def in_breach(self, equity: float) -> bool:
        return self.drawdown(equity) > self.config.mdd_limit

    def filter_orders(
        self,
        orders: list[Order],
        equity: float,
        max_position_notional: float | None = None,
    ) -> list[Order]:
        breached = self.in_breach(equity)
        result: list[Order] = []
        for o in orders:
            if breached and o.side == "buy":
                continue  # 낙폭 초과 시 신규/추가 익스포저 차단
            notional = o.notional
            if max_position_notional is not None:
                notional = min(notional, max_position_notional)
            result.append(Order(symbol=o.symbol, side=o.side, notional=notional))
        return result
