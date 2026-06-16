from ohmystock.paper.account import PaperAccount

def test_paper_account_fields():
    a = PaperAccount(
        strategy="Momentum", params={"top_k": 3}, symbols=["AAPL", "MSFT"],
        initial_capital=1_000_000, start_date="2024-01-01", end_date="2024-06-30",
        cursor_date=None, cash=1_000_000, peak_equity=1_000_000)
    assert a.symbols == ["AAPL", "MSFT"]
    assert a.cursor_date is None
    assert a.cash == 1_000_000
