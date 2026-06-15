import pandas as pd
from ohmystock.core.backtest.result import BacktestResult
from ohmystock.core.validation.base import ValidationReport

def test_backtest_result_holds_series_and_frames():
    idx = pd.to_datetime(["2024-01-02", "2024-01-03"])
    eq = pd.Series([100.0, 110.0], index=idx)
    res = BacktestResult(
        equity_curve=eq,
        returns=eq.pct_change().fillna(0.0),
        trades=pd.DataFrame(columns=["symbol", "entry_date", "exit_date", "qty", "pnl", "cost"]),
        positions=pd.DataFrame(index=idx),
    )
    assert res.equity_curve.iloc[-1] == 110.0
    assert list(res.trades.columns) == ["symbol", "entry_date", "exit_date", "qty", "pnl", "cost"]

def test_validation_report_fields():
    rep = ValidationReport(name="Sharpe", value=1.2, passed=True, threshold=1.0, message="ok")
    assert rep.passed is True
    assert rep.threshold == 1.0
