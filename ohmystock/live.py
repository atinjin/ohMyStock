"""실거래 드라이런(페이퍼) — 오늘자 목표 리밸런싱 주문 미리보기.

PaperBroker로 현재 자산을 시뮬레이션해 오늘 제출할 주문을 계산한다.
실주문은 나가지 않는다(실계좌는 6단계 어댑터에 키를 넣어야만 동작).
"""
from datetime import date

from ohmystock.config import Config
from ohmystock.core.data.cache import ParquetCache
from ohmystock.core.data.yfinance_adapter import YFinanceAdapter
from ohmystock.core.strategy.momentum import Momentum
from ohmystock.core.broker.paper import PaperBroker
from ohmystock.core.broker.risk import RiskGuard
from ohmystock.core.broker.rebalance import rebalance


def live_preview(symbols, start, end, adapter, strategy, config,
                 max_position_weight=None) -> dict:
    """오늘자 목표 리밸런싱 주문을 PaperBroker로 계산해 JSON-직렬화 가능 dict 반환."""
    bars = adapter.get_daily_bars(symbols, start, end)
    broker = PaperBroker(cash=config.initial_capital)
    prices = {sym: float(df["close"].iloc[-1]) for sym, df in bars.items()}
    broker.set_prices(prices)
    risk = RiskGuard(config, peak_equity=config.initial_capital)

    before = broker.get_account()
    orders = rebalance(strategy, bars, broker, risk, config,
                       max_position_weight=max_position_weight)
    after = broker.get_account()

    return {
        "strategy": type(strategy).__name__,
        "symbols": list(symbols),
        "account_before": {"equity": before.equity, "cash": before.cash},
        "account_after": {"equity": after.equity, "cash": after.cash},
        "orders": [
            {"symbol": o.symbol, "side": o.side, "notional": round(o.notional, 2)}
            for o in orders
        ],
        "risk": {
            "in_breach": bool(risk.in_breach(before.equity)),
            "drawdown": float(risk.drawdown(before.equity)),
        },
        "prices": {k: float(v) for k, v in prices.items()},
    }


def main():
    config = Config()
    adapter = YFinanceAdapter(cache=ParquetCache(".cache"))
    symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]
    preview = live_preview(
        symbols=symbols, start=date(2020, 1, 1), end=date(2024, 1, 1),
        adapter=adapter, strategy=Momentum(90, 3), config=config)

    print("=" * 48)
    print("OhMyStock 실거래 드라이런 (페이퍼 — 실주문 없음)")
    print("=" * 48)
    print(f"전략: {preview['strategy']}  자금: {preview['account_before']['equity']:,.0f}")
    print(f"리스크: {'MDD 한도 위반(신규진입 차단)' if preview['risk']['in_breach'] else '정상'}"
          f" (낙폭 {preview['risk']['drawdown']:.1%})")
    print("-" * 48)
    print("오늘 제출할 주문:")
    if not preview["orders"]:
        print("  (없음 — 이미 목표 비중)")
    for o in preview["orders"]:
        print(f"  {o['side'].upper():4} {o['symbol']:6} ${o['notional']:,.2f}")
    print("=" * 48)


if __name__ == "__main__":
    main()
