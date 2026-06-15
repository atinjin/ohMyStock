import pandas as pd
from ohmystock.config import Config
from ohmystock.core.backtest.engine import run_backtest

def _bars(closes):
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="B")
    return {"AAPL": pd.DataFrame(
        {"open": closes, "high": closes, "low": closes,
         "close": closes, "volume": [100] * len(closes)}, index=idx)}

def test_equity_grows_with_held_uptrend_no_cost():
    bars = _bars([10.0, 11.0, 12.0])          # +10%, +9.09%
    idx = list(bars["AAPL"].index)
    weights = pd.DataFrame({"AAPL": [1.0, 1.0, 1.0]}, index=idx)
    cfg = Config(commission_bps=0, slippage_bps=0, spread_bps=0, initial_capital=100.0)
    res = run_backtest(bars, weights, cfg)
    # day1 보유수익 없음(기준), day2 +10%, day3 +9.09% → 100*1.1*1.0909≈120
    assert abs(res.equity_curve.iloc[-1] - 120.0) < 1e-6

def test_cost_reduces_return_on_entry():
    bars = _bars([10.0, 10.0])
    idx = list(bars["AAPL"].index)
    weights = pd.DataFrame({"AAPL": [1.0, 1.0]}, index=idx)  # 첫날 진입(회전율 1)
    cfg = Config(commission_bps=0, slippage_bps=5, spread_bps=2, initial_capital=100.0)
    res = run_backtest(bars, weights, cfg)
    # 가격 변동 0, 첫날 진입비용 7bps → 자산 100*(1-0.0007)=99.93
    assert abs(res.equity_curve.iloc[0] - 99.93) < 1e-6

def test_trades_record_round_trip():
    bars = _bars([10.0, 11.0, 12.0, 12.0])
    idx = list(bars["AAPL"].index)
    # 1일 진입, 3일 청산
    weights = pd.DataFrame({"AAPL": [1.0, 1.0, 0.0, 0.0]}, index=idx)
    cfg = Config(commission_bps=0, slippage_bps=0, spread_bps=0, initial_capital=100.0)
    res = run_backtest(bars, weights, cfg)
    assert len(res.trades) == 1
    row = res.trades.iloc[0]
    assert row["symbol"] == "AAPL"
    assert row["pnl"] > 0      # 10 → 12 보유 구간
