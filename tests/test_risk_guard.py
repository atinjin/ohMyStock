import pytest
from ohmystock.config import Config
from ohmystock.core.broker.base import Order
from ohmystock.core.broker.risk import RiskGuard


def test_peak_updates_on_update():
    rg = RiskGuard(Config())
    rg.update(100.0)
    rg.update(150.0)
    rg.update(120.0)
    assert rg.peak == pytest.approx(150.0)


def test_drawdown_computed_correctly():
    rg = RiskGuard(Config(), peak_equity=200.0)
    assert rg.drawdown(150.0) == pytest.approx(0.25)
    # peak <= 0 -> 0 drawdown
    rg2 = RiskGuard(Config())
    assert rg2.drawdown(100.0) == pytest.approx(0.0)


def test_in_breach_when_below_mdd_limit():
    cfg = Config(mdd_limit=0.20)
    rg = RiskGuard(cfg, peak_equity=100.0)
    assert rg.in_breach(75.0) is True   # 25% dd > 20%
    assert rg.in_breach(85.0) is False  # 15% dd < 20%


def test_filter_orders_blocks_buys_keeps_sells_in_breach():
    cfg = Config(mdd_limit=0.20)
    rg = RiskGuard(cfg, peak_equity=100.0)
    orders = [
        Order("AAPL", "buy", 50.0),
        Order("MSFT", "sell", 30.0),
    ]
    out = rg.filter_orders(orders, equity=75.0)  # in breach
    sides = [o.side for o in out]
    assert "buy" not in sides
    assert "sell" in sides
    # input not mutated
    assert len(orders) == 2


def test_filter_orders_passes_buys_when_not_in_breach():
    cfg = Config(mdd_limit=0.20)
    rg = RiskGuard(cfg, peak_equity=100.0)
    orders = [Order("AAPL", "buy", 50.0)]
    out = rg.filter_orders(orders, equity=95.0)
    assert len(out) == 1
    assert out[0].side == "buy"


def test_filter_orders_caps_notional():
    cfg = Config(mdd_limit=0.20)
    rg = RiskGuard(cfg, peak_equity=100.0)
    orders = [Order("AAPL", "buy", 80.0), Order("MSFT", "sell", 10.0)]
    out = rg.filter_orders(orders, equity=95.0, max_position_notional=40.0)
    notionals = {o.symbol: o.notional for o in out}
    assert notionals["AAPL"] == pytest.approx(40.0)
    assert notionals["MSFT"] == pytest.approx(10.0)
    # inputs unchanged
    assert orders[0].notional == pytest.approx(80.0)
