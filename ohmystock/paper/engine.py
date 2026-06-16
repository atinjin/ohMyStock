import pandas as pd

from ohmystock.core.broker.paper import PaperBroker
from ohmystock.core.broker.risk import RiskGuard
from ohmystock.core.broker.rebalance import rebalance
from ohmystock.report import build_strategy


def close_panel(bars: dict, start: str, end: str) -> pd.DataFrame:
    """종가 패널: 거래일 합집합 인덱스로 정렬·ffill, [start,end]로 한정."""
    closes = pd.DataFrame({sym: df["close"] for sym, df in bars.items()})
    closes = closes.sort_index().ffill()
    mask = (closes.index >= pd.Timestamp(start)) & (closes.index <= pd.Timestamp(end))
    return closes[mask]


def next_trading_day(index: pd.DatetimeIndex, cursor_date):
    """cursor 다음 거래일. cursor None이면 첫 날, 더 없으면 None."""
    if len(index) == 0:
        return None
    if cursor_date is None:
        return index[0]
    after = index[index > pd.Timestamp(cursor_date)]
    return None if len(after) == 0 else after[0]


def step(account, store, bars: dict, config):
    """커서를 다음 거래일로 전진해 리밸런싱·기록. 결과 dict 또는 완료 시 None."""
    panel = close_panel(bars, account.start_date, account.end_date)
    d = next_trading_day(panel.index, account.cursor_date)
    if d is None:
        return None

    sliced = {sym: df[df.index <= d] for sym, df in bars.items()}
    prices = {
        sym: float(panel.loc[d, sym])
        for sym in panel.columns
        if pd.notna(panel.loc[d, sym])
    }
    broker = PaperBroker(cash=account.cash)
    # 가격을 아는 보유 종목만 복원(유니버스 축소/데이터 공백 시 _price 예외 방지)
    broker.shares = {
        sym: qty for sym, qty in store.load_positions().items() if sym in prices
    }
    broker.set_prices(prices)

    strategy = build_strategy(account.strategy, account.params)
    risk = RiskGuard(config, peak_equity=account.peak_equity)
    orders = rebalance(strategy, sliced, broker, risk, config)

    acct = broker.get_account()
    equity = acct.equity
    date_str = d.strftime("%Y-%m-%d")
    order_rows = [
        {
            "symbol": o.symbol, "side": o.side, "notional": round(o.notional, 2),
            "price": prices.get(o.symbol, 0.0),
            "shares": (o.notional / prices[o.symbol]) if o.symbol in prices else 0.0,
        }
        for o in orders
    ]

    account.cursor_date = date_str
    account.cash = acct.cash
    account.peak_equity = max(account.peak_equity, equity)
    store.save_positions(broker.shares)
    store.append_snapshot(date_str, equity, acct.cash)
    store.append_trades(date_str, order_rows)
    store.save_account(account)

    return {
        "date": date_str, "equity": equity, "cash": acct.cash,
        "orders": order_rows,
        "in_breach": bool(risk.in_breach(equity)),
        "drawdown": float(risk.drawdown(equity)),
    }
