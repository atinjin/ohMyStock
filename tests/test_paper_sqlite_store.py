from ohmystock.paper.account import PaperAccount
from ohmystock.paper.sqlite_store import SqlitePaperStore


def _account():
    return PaperAccount(
        strategy="Momentum", params={"top_k": 2}, symbols=["AAPL", "MSFT"],
        initial_capital=1_000_000, start_date="2024-01-01", end_date="2024-06-30",
        cursor_date=None, cash=1_000_000, peak_equity=1_000_000)


def test_initialize_and_load(tmp_path):
    store = SqlitePaperStore(tmp_path / "p.db")
    assert store.load_account() is None
    store.initialize(_account())
    a = store.load_account()
    assert a is not None
    assert a.strategy == "Momentum"
    assert a.params == {"top_k": 2}
    assert a.symbols == ["AAPL", "MSFT"]
    assert a.cash == 1_000_000


def test_save_account_and_positions(tmp_path):
    store = SqlitePaperStore(tmp_path / "p.db")
    store.initialize(_account())
    a = store.load_account()
    a.cursor_date = "2024-01-03"
    a.cash = 500_000
    a.peak_equity = 1_100_000
    store.save_account(a)
    store.save_positions({"AAPL": 10.0, "MSFT": 0.0})
    a2 = store.load_account()
    assert a2.cursor_date == "2024-01-03"
    assert a2.cash == 500_000
    assert store.load_positions() == {"AAPL": 10.0}  # 0 주는 저장 안 함


def test_snapshots_and_trades(tmp_path):
    store = SqlitePaperStore(tmp_path / "p.db")
    store.initialize(_account())
    store.append_snapshot("2024-01-02", 1_000_000, 1_000_000)
    store.append_snapshot("2024-01-03", 1_010_000, 400_000)
    store.append_trades("2024-01-03", [
        {"symbol": "AAPL", "side": "buy", "notional": 600_000, "price": 100.0, "shares": 6000.0},
    ])
    snaps = store.snapshots()
    assert [s["date"] for s in snaps] == ["2024-01-02", "2024-01-03"]
    assert snaps[-1]["equity"] == 1_010_000
    trades = store.trades()
    assert len(trades) == 1
    assert trades[0]["side"] == "buy"
    assert trades[0]["symbol"] == "AAPL"


def test_initialize_resets(tmp_path):
    store = SqlitePaperStore(tmp_path / "p.db")
    store.initialize(_account())
    store.append_snapshot("2024-01-02", 1, 1)
    store.initialize(_account())  # reset
    assert store.snapshots() == []
