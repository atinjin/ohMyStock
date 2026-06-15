import pytest
from ohmystock.core.broker.paper import PaperBroker


def test_buy_creates_position_and_reduces_cash():
    b = PaperBroker(cash=1000.0)
    b.set_prices({"AAPL": 10.0})
    from ohmystock.core.broker.base import Order
    b.submit_order(Order(symbol="AAPL", side="buy", notional=100.0))
    assert b.shares["AAPL"] == pytest.approx(10.0)
    assert b.cash == pytest.approx(900.0)
    assert b.get_positions()["AAPL"] == pytest.approx(100.0)
    # cash -> position, equity unchanged
    assert b.get_account().equity == pytest.approx(1000.0)


def test_sell_reduces_shares_and_increases_cash():
    from ohmystock.core.broker.base import Order
    b = PaperBroker(cash=1000.0)
    b.set_prices({"AAPL": 10.0})
    b.submit_order(Order("AAPL", "buy", 100.0))
    b.submit_order(Order("AAPL", "sell", 50.0))
    assert b.shares["AAPL"] == pytest.approx(5.0)
    assert b.cash == pytest.approx(950.0)


def test_sell_more_than_held_clamps_to_held():
    from ohmystock.core.broker.base import Order
    b = PaperBroker(cash=1000.0)
    b.set_prices({"AAPL": 10.0})
    b.submit_order(Order("AAPL", "buy", 100.0))  # 10 shares
    b.submit_order(Order("AAPL", "sell", 500.0))  # would be 50 shares
    assert b.shares["AAPL"] == pytest.approx(0.0)
    assert b.cash == pytest.approx(1000.0)


def test_buy_beyond_cash_raises():
    from ohmystock.core.broker.base import Order
    b = PaperBroker(cash=100.0)
    b.set_prices({"AAPL": 10.0})
    with pytest.raises(ValueError):
        b.submit_order(Order("AAPL", "buy", 200.0))


def test_unknown_price_raises():
    from ohmystock.core.broker.base import Order
    b = PaperBroker(cash=1000.0)
    with pytest.raises(ValueError):
        b.submit_order(Order("AAPL", "buy", 100.0))


def test_get_account_equity_is_cash_plus_positions():
    from ohmystock.core.broker.base import Order
    b = PaperBroker(cash=1000.0)
    b.set_prices({"AAPL": 10.0, "MSFT": 20.0})
    b.submit_order(Order("AAPL", "buy", 300.0))
    b.submit_order(Order("MSFT", "buy", 200.0))
    acct = b.get_account()
    positions = b.get_positions()
    assert acct.cash == pytest.approx(500.0)
    assert acct.equity == pytest.approx(b.cash + sum(positions.values()))
    assert acct.equity == pytest.approx(1000.0)


def test_positions_only_includes_held_symbols():
    b = PaperBroker(cash=1000.0)
    b.set_prices({"AAPL": 10.0})
    assert b.get_positions() == {}
