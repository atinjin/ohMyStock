from ohmystock.config import Config

def test_default_config_values():
    cfg = Config()
    assert cfg.initial_capital == 5_000_000
    assert cfg.mdd_limit == 0.20
    assert cfg.trading_days == 252
    assert cfg.risk_free_rate == 0.0
    assert cfg.commission_bps == 0.0   # 미국 Alpaca 0%
    assert cfg.slippage_bps == 5.0
    assert cfg.spread_bps == 2.0

def test_cost_rate_per_turnover():
    cfg = Config()
    # (0 + 5 + 2) bps = 7 bps = 0.0007
    assert abs(cfg.cost_rate() - 0.0007) < 1e-12
