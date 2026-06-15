import numpy as np
import pandas as pd
from ohmystock.core.validation._stats import (
    annualized_sharpe, total_return, max_drawdown_from_returns,
)


def test_total_return():
    # (1.1)(0.8)(1.3) - 1 = 0.144
    assert abs(total_return([0.10, -0.20, 0.30]) - 0.144) < 1e-9


def test_total_return_empty():
    assert total_return([]) == 0.0


def test_max_drawdown_from_returns():
    # 100 -> 110 -> 88 : 고점 110 대비 -20%
    assert abs(max_drawdown_from_returns([0.10, -0.20]) - 0.20) < 1e-9


def test_sharpe_zero_when_flat():
    assert annualized_sharpe([0.01, 0.01, 0.01]) == 0.0


def test_sharpe_zero_when_too_short():
    assert annualized_sharpe([0.01]) == 0.0


def test_sharpe_positive_for_positive_mean():
    assert annualized_sharpe([0.01, -0.005, 0.02, 0.0, 0.015]) > 0


def test_sharpe_matches_metrics_convention():
    # _stats.annualized_sharpe는 metrics.sharpe_ratio와 동일 값이어야 한다
    from ohmystock.config import Config
    from ohmystock.core.backtest.result import BacktestResult
    from ohmystock.core.validation.metrics import sharpe_ratio
    rets = [0.01, -0.005, 0.02, 0.0, 0.015, -0.01, 0.008]
    idx = pd.date_range("2024-01-01", periods=len(rets), freq="B")
    r = pd.Series(rets, index=idx)
    eq = 100.0 * (1 + r).cumprod()
    res = BacktestResult(equity_curve=eq, returns=r,
                         trades=pd.DataFrame(columns=["symbol", "pnl"]),
                         positions=pd.DataFrame(index=idx))
    assert abs(annualized_sharpe(rets) - sharpe_ratio(res, Config())) < 1e-9
