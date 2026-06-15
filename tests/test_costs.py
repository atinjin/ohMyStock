import pandas as pd
from ohmystock.config import Config
from ohmystock.core.backtest.costs import turnover_series, cost_series

def test_turnover_counts_weight_changes():
    idx = pd.date_range("2024-01-01", periods=3, freq="B")
    w = pd.DataFrame({"AAPL": [0.0, 1.0, 0.0]}, index=idx)
    # 변화: 0->0(0), 0->1(1), 1->0(1)
    t = turnover_series(w)
    assert list(t.values) == [0.0, 1.0, 1.0]

def test_cost_is_turnover_times_rate():
    idx = pd.date_range("2024-01-01", periods=2, freq="B")
    w = pd.DataFrame({"AAPL": [0.0, 1.0]}, index=idx)
    cfg = Config()  # cost_rate = 0.0007
    c = cost_series(w, cfg)
    assert abs(c.iloc[1] - 0.0007) < 1e-12
    assert c.iloc[0] == 0.0
