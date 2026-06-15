import numpy as np
import pandas as pd
from ohmystock.config import Config
from ohmystock.core.backtest.result import BacktestResult
from ohmystock.core.validation.metrics import (
    max_drawdown, sharpe_ratio, sortino_ratio, calmar_ratio,
    profit_factor, recovery_factor,
)

def _result(returns, trades_pnl=None):
    idx = pd.date_range("2024-01-01", periods=len(returns), freq="B")
    r = pd.Series(returns, index=idx)
    eq = 100.0 * (1 + r).cumprod()
    if trades_pnl:
        tidx = pd.date_range("2024-01-01", periods=len(trades_pnl), freq="B")
        trades = pd.DataFrame(
            {"symbol": ["X"] * len(trades_pnl), "entry_date": tidx,
             "exit_date": tidx, "qty": [1.0] * len(trades_pnl),
             "pnl": trades_pnl, "cost": [0.0] * len(trades_pnl)}
        )
    else:
        trades = pd.DataFrame(columns=["symbol", "pnl"])
    return BacktestResult(equity_curve=eq, returns=r, trades=trades,
                          positions=pd.DataFrame(index=idx))

def test_max_drawdown():
    res = _result([0.10, -0.20])   # 100 -> 110 -> 88 : -20%
    assert abs(max_drawdown(res) - 0.20) < 1e-9

def test_sharpe_zero_when_no_volatility():
    res = _result([0.01, 0.01, 0.01])
    cfg = Config(risk_free_rate=0.0)
    assert sharpe_ratio(res, cfg) == 0.0

def test_sharpe_positive_for_positive_mean():
    res = _result([0.01, -0.005, 0.02, 0.0, 0.015])
    assert sharpe_ratio(res, Config()) > 0

def test_sortino_ge_sharpe_magnitude_when_downside_small():
    res = _result([0.02, 0.02, -0.01, 0.02])
    assert sortino_ratio(res, Config()) > 0

def test_calmar_is_cagr_over_mdd():
    res = _result([0.10, -0.20, 0.30])
    cfg = Config()
    mdd = max_drawdown(res)
    cagr = (res.equity_curve.iloc[-1] / 100.0) ** (cfg.trading_days / len(res.returns)) - 1
    assert abs(calmar_ratio(res, cfg) - cagr / mdd) < 1e-6

def test_profit_factor():
    res = _result([0.0, 0.0], trades_pnl=[30.0, -10.0, 20.0])
    assert abs(profit_factor(res) - 5.0) < 1e-9   # 이익50 / 손실10

def test_recovery_factor():
    res = _result([0.10, -0.20, 0.30])
    cfg = Config()
    total_ret = res.equity_curve.iloc[-1] / 100.0 - 1
    assert abs(recovery_factor(res) - total_ret / max_drawdown(res)) < 1e-6
