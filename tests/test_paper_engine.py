import numpy as np
import pandas as pd
from ohmystock.config import Config
from ohmystock.paper.account import PaperAccount
from ohmystock.paper.sqlite_store import SqlitePaperStore
from ohmystock.paper import engine


def _bars(symbols, n=40):
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    out = {}
    for i, s in enumerate(symbols):
        closes = np.linspace(10 + i, 30 + i, n)  # 꾸준한 상승추세
        out[s] = pd.DataFrame(
            {"open": closes, "high": closes, "low": closes,
             "close": closes, "volume": [1e6] * n}, index=idx)
    return out


def _fresh(tmp_path, symbols=("AAPL",)):
    acct = PaperAccount(
        strategy="MACrossover", params={"short": 3, "long": 10},
        symbols=list(symbols), initial_capital=1_000_000,
        start_date="2024-01-01", end_date="2024-03-31",
        cursor_date=None, cash=1_000_000, peak_equity=1_000_000)
    store = SqlitePaperStore(tmp_path / "p.db")
    store.initialize(acct)
    return acct, store


def test_step_advances_cursor_and_records(tmp_path):
    acct, store = _fresh(tmp_path)
    bars = _bars(["AAPL"], 40)
    res = engine.step(acct, store, bars, Config())
    assert res is not None
    assert res["date"] == "2024-01-01"  # 첫 거래일
    loaded = store.load_account()
    assert loaded.cursor_date == "2024-01-01"
    assert len(store.snapshots()) == 1


def test_step_returns_none_when_complete(tmp_path):
    acct, store = _fresh(tmp_path)
    bars = _bars(["AAPL"], 40)
    last = bars["AAPL"].index[-1].strftime("%Y-%m-%d")
    acct.cursor_date = last
    store.save_account(acct)
    assert engine.step(acct, store, bars, Config()) is None


def test_repeated_steps_build_equity_and_trades(tmp_path):
    acct, store = _fresh(tmp_path)
    bars = _bars(["AAPL"], 40)
    for _ in range(60):
        a = store.load_account()
        if engine.step(a, store, bars, Config()) is None:
            break
    snaps = store.snapshots()
    assert len(snaps) >= 30
    assert store.load_account().cursor_date == bars["AAPL"].index[-1].strftime("%Y-%m-%d")
    assert len(store.trades()) >= 1
    assert snaps[-1]["equity"] > 1_000_000
