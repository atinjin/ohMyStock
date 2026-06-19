"""실거래 드라이런(페이퍼) — 오늘자 목표 리밸런싱 주문 미리보기.

PaperBroker로 현재 자산을 시뮬레이션해 오늘 제출할 주문을 계산한다.
실주문은 나가지 않는다(실계좌는 6단계 어댑터에 키를 넣어야만 동작).
"""
import argparse
from datetime import date

from ohmystock.config import Config
from ohmystock.core.data.cache import ParquetCache
from ohmystock.core.data.yfinance_adapter import YFinanceAdapter
from ohmystock.core.strategy.momentum import Momentum
from ohmystock.core.broker.paper import PaperBroker
from ohmystock.core.broker.risk import RiskGuard
from ohmystock.core.broker.rebalance import rebalance
from ohmystock.broker_select import resolve_mode, build_broker
from ohmystock.report import build_strategy


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


def live_execute(symbols, start, end, adapter, strategy, config, *,
                 mode="dry-run", env=None, broker=None,
                 max_position_weight=None) -> dict:
    """모드 인지 실행. dry-run=PaperBroker 시뮬, live=AlpacaBroker 실주문."""
    resolved = resolve_mode(mode, env)
    bars = adapter.get_daily_bars(symbols, start, end)
    if broker is None:
        broker = build_broker(resolved, cash=config.initial_capital, env=env)
    if isinstance(broker, PaperBroker):
        broker.set_prices({s: float(df["close"].iloc[-1]) for s, df in bars.items()})

    before = broker.get_account()
    risk = RiskGuard(config, peak_equity=before.equity)
    orders = rebalance(strategy, bars, broker, risk, config,
                       max_position_weight=max_position_weight)
    after = broker.get_account()
    return {
        "mode": resolved,
        "strategy": type(strategy).__name__,
        "symbols": list(symbols),
        "account_before": {"equity": before.equity, "cash": before.cash},
        "account_after": {"equity": after.equity, "cash": after.cash},
        "orders": [{"symbol": o.symbol, "side": o.side, "notional": round(o.notional, 2)}
                   for o in orders],
        "risk": {"in_breach": bool(risk.in_breach(before.equity)),
                 "drawdown": float(risk.drawdown(before.equity))},
    }


def run_cli(argv=None, *, adapter=None, env=None) -> dict:
    parser = argparse.ArgumentParser(prog="ohmystock.live")
    parser.add_argument("--mode", choices=["dry-run", "live"], default=None)
    parser.add_argument("--strategy", default="Momentum")
    parser.add_argument("--symbols", default="AAPL,MSFT,GOOGL,AMZN,META")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2024-01-01")
    parser.add_argument("--capital", type=float, default=5_000_000)
    args = parser.parse_args(argv)

    mode = resolve_mode(args.mode, env)
    if adapter is None:
        adapter = YFinanceAdapter(cache=ParquetCache(".cache"))
    config = Config(initial_capital=args.capital)
    strategy = build_strategy(args.strategy, {})
    result = live_execute(
        args.symbols.split(","), date.fromisoformat(args.start),
        date.fromisoformat(args.end), adapter, strategy, config, mode=mode, env=env)
    print(result)
    return result


def main() -> None:
    run_cli()


if __name__ == "__main__":
    main()
