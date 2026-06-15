import pandas as pd
import pytest

from ohmystock.config import Config
from ohmystock.core.broker.paper import PaperBroker
from ohmystock.core.broker.risk import RiskGuard
from ohmystock.core.broker.rebalance import rebalance


class StubStrategy:
    """generate_signals가 고정 가중 프레임을 반환하는 결정적 스텁."""

    def __init__(self, weights: pd.DataFrame):
        self._weights = weights

    def generate_signals(self, bars):
        return self._weights


def _bars():
    idx = pd.date_range("2024-01-01", periods=3, freq="B")
    aapl = pd.DataFrame({"close": [9.0, 9.5, 10.0]}, index=idx)
    msft = pd.DataFrame({"close": [18.0, 19.0, 20.0]}, index=idx)
    return {"AAPL": aapl, "MSFT": msft}


def _weights(idx, last_row: dict):
    rows = [{"AAPL": 0.0, "MSFT": 0.0} for _ in idx]
    rows[-1] = last_row
    return pd.DataFrame(rows, index=idx)


def test_full_allocation_then_flatten():
    bars = _bars()
    idx = bars["AAPL"].index
    broker = PaperBroker(cash=1000.0)
    broker.set_prices({"AAPL": 10.0, "MSFT": 20.0})
    cfg = Config(mdd_limit=0.20)
    rg = RiskGuard(cfg)

    # target 100% AAPL
    strat = StubStrategy(_weights(idx, {"AAPL": 1.0, "MSFT": 0.0}))
    orders = rebalance(strat, bars, broker, rg, cfg)
    assert len(orders) == 1
    assert orders[0].symbol == "AAPL"
    assert orders[0].side == "buy"
    assert orders[0].notional == pytest.approx(1000.0)
    # ~100% invested
    acct = broker.get_account()
    assert broker.get_positions()["AAPL"] == pytest.approx(1000.0)
    assert acct.cash == pytest.approx(0.0)

    # now target 0 -> sell to flat
    strat2 = StubStrategy(_weights(idx, {"AAPL": 0.0, "MSFT": 0.0}))
    orders2 = rebalance(strat2, bars, broker, rg, cfg)
    assert len(orders2) == 1
    assert orders2[0].side == "sell"
    assert broker.get_positions() == {}
    assert broker.get_account().cash == pytest.approx(1000.0)


def test_breach_blocks_buys_but_allows_sells():
    bars = _bars()
    idx = bars["AAPL"].index
    broker = PaperBroker(cash=1000.0)
    broker.set_prices({"AAPL": 10.0, "MSFT": 20.0})
    cfg = Config(mdd_limit=0.20)

    # seed an existing AAPL position so a sell is available
    from ohmystock.core.broker.base import Order
    broker.submit_order(Order("AAPL", "buy", 500.0))  # 50 shares, cash 500

    # peak far above current equity -> in breach
    rg = RiskGuard(cfg, peak_equity=10_000.0)

    # target: buy MSFT (new exposure), sell AAPL to 0
    strat = StubStrategy(_weights(idx, {"AAPL": 0.0, "MSFT": 0.5}))
    orders = rebalance(strat, bars, broker, rg, cfg)
    sides = {(o.symbol, o.side) for o in orders}
    # MSFT buy blocked
    assert ("MSFT", "buy") not in sides
    # AAPL sell allowed
    assert ("AAPL", "sell") in sides
    assert broker.get_positions().get("AAPL", 0.0) == pytest.approx(0.0)


def test_max_position_weight_caps_order():
    bars = _bars()
    idx = bars["AAPL"].index
    broker = PaperBroker(cash=1000.0)
    broker.set_prices({"AAPL": 10.0, "MSFT": 20.0})
    cfg = Config(mdd_limit=0.20)
    rg = RiskGuard(cfg)

    strat = StubStrategy(_weights(idx, {"AAPL": 1.0, "MSFT": 0.0}))
    orders = rebalance(strat, bars, broker, rg, cfg, max_position_weight=0.3)
    assert orders[0].notional == pytest.approx(300.0)  # 0.3 * 1000
