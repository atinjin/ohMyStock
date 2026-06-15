import pandas as pd
from ohmystock.config import Config
from ohmystock.core.backtest.costs import cost_series
from ohmystock.core.backtest.result import BacktestResult


def _close_panel(bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return pd.DataFrame({sym: df["close"] for sym, df in bars.items()})


def _extract_trades(weights: pd.DataFrame, closes: pd.DataFrame,
                    equity: pd.Series) -> pd.DataFrame:
    """비중 0→양수=진입, 양수→0=청산. round-trip 거래내역 생성."""
    rows = []
    for sym in weights.columns:
        w = weights[sym]
        price = closes[sym]
        in_pos = False
        entry_date = entry_price = entry_equity = None
        for dt in w.index:
            if not in_pos and w.loc[dt] > 0:
                in_pos, entry_date = True, dt
                entry_price, entry_equity = price.loc[dt], equity.loc[dt]
            elif in_pos and w.loc[dt] == 0:
                pnl_pct = price.loc[dt] / entry_price - 1
                rows.append({
                    "symbol": sym, "entry_date": entry_date, "exit_date": dt,
                    "qty": entry_equity / entry_price,
                    "pnl": pnl_pct * entry_equity, "cost": 0.0,
                })
                in_pos = False
    return pd.DataFrame(
        rows, columns=["symbol", "entry_date", "exit_date", "qty", "pnl", "cost"])


def run_backtest(bars: dict[str, pd.DataFrame], weights: pd.DataFrame,
                 config: Config) -> BacktestResult:
    closes = _close_panel(bars).reindex(weights.index)
    asset_returns = closes.pct_change().fillna(0.0)
    # 그날 보유 비중으로 포트폴리오 총수익
    gross = (weights * asset_returns).sum(axis=1)
    costs = cost_series(weights, config)
    net = gross - costs
    equity = config.initial_capital * (1 + net).cumprod()
    trades = _extract_trades(weights, closes, equity)
    return BacktestResult(
        equity_curve=equity, returns=net, trades=trades, positions=weights)
