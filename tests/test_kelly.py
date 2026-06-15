import pandas as pd
from ohmystock.core.backtest.result import BacktestResult
from ohmystock.core.validation.kelly import kelly_criterion


def _result(trades_pnl):
    idx = pd.date_range("2024-01-01", periods=2, freq="B")
    r = pd.Series([0.0, 0.0], index=idx)
    eq = 100.0 * (1 + r).cumprod()
    if trades_pnl:
        tidx = pd.date_range("2024-01-01", periods=len(trades_pnl), freq="B")
        trades = pd.DataFrame(
            {"symbol": ["X"] * len(trades_pnl), "entry_date": tidx,
             "exit_date": tidx, "qty": [1.0] * len(trades_pnl),
             "pnl": trades_pnl, "cost": [0.0] * len(trades_pnl)}
        )
    else:
        trades = pd.DataFrame(columns=["symbol", "entry_date", "exit_date",
                                       "qty", "pnl", "cost"])
    return BacktestResult(equity_curve=eq, returns=r, trades=trades,
                          positions=pd.DataFrame(index=idx))


def test_kelly_fraction_value_and_pass():
    # p=0.6, avg_win=2.0, avg_loss=1.0 -> f* = 0.6 - 0.4/2.0 = 0.4
    res = _result([2.0, 2.0, 2.0, -1.0, -1.0])
    report = kelly_criterion(res, threshold=0.0)
    assert report.name == "Kelly"
    assert abs(report.value - 0.4) < 1e-9
    assert report.passed is True
    assert "0.20" in report.message  # half-kelly mentioned


def test_kelly_all_wins_no_losses():
    res = _result([2.0, 2.0, 2.0])
    report = kelly_criterion(res, threshold=0.0)
    assert report.passed is False
    assert report.value == 0.0


def test_kelly_empty_trades():
    res = _result([])
    report = kelly_criterion(res, threshold=0.0)
    assert report.passed is False
    assert report.value == 0.0
