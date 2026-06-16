from ohmystock.config import Config
from ohmystock.core.broker.base import Order


def rebalance(
    strategy,
    bars,
    broker,
    risk_guard,
    config: Config,
    max_position_weight: float | None = None,
) -> list[Order]:
    """전략의 오늘 목표 가중을 현재 포지션과 비교해 일일 리밸런싱 주문 생성·제출."""
    signals = strategy.generate_signals(bars)
    target_weights = signals.iloc[-1]  # 오늘 목표 가중(마지막 행)

    account = broker.get_account()
    equity = account.equity
    risk_guard.update(equity)

    positions = broker.get_positions()  # 종목 -> 현재 평가 금액

    symbols = sorted(set(target_weights.index) | set(positions.keys()))
    threshold = max(1e-6 * equity, 1.0)

    orders: list[Order] = []
    for symbol in symbols:
        target_value = float(target_weights.get(symbol, 0.0)) * equity
        current_value = float(positions.get(symbol, 0.0))
        diff = target_value - current_value
        if abs(diff) < threshold:
            continue
        side = "buy" if diff > 0 else "sell"
        orders.append(Order(symbol=symbol, side=side, notional=abs(diff)))

    max_position_notional = (
        max_position_weight * equity if max_position_weight else None
    )
    orders = risk_guard.filter_orders(
        orders, equity, max_position_notional=max_position_notional
    )

    # 매도를 먼저 체결해 현금을 확보한 뒤 매수: 다종목 풀투자 시 현금 부족 방지
    submit_order = sorted(orders, key=lambda o: 0 if o.side == "sell" else 1)
    for order in submit_order:
        broker.submit_order(order)
    return orders
