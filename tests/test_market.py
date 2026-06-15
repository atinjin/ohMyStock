import pandas as pd
from ohmystock.core.validation._market import equal_weight_benchmark


def _bars(closes_by_sym):
    n = len(next(iter(closes_by_sym.values())))
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return {sym: pd.DataFrame(
        {"open": c, "high": c, "low": c, "close": c, "volume": [100] * n},
        index=idx) for sym, c in closes_by_sym.items()}


def test_single_symbol_benchmark_matches_its_returns():
    bars = _bars({"A": [10.0, 11.0, 12.0]})
    bench = equal_weight_benchmark(bars)
    # 첫날 0, 둘째날 +10%, 셋째날 +9.09%
    assert abs(bench.iloc[0] - 0.0) < 1e-12
    assert abs(bench.iloc[1] - 0.10) < 1e-12
    assert abs(bench.iloc[2] - (12 / 11 - 1)) < 1e-12


def test_equal_weight_average_of_two_symbols():
    bars = _bars({"A": [10.0, 12.0], "B": [10.0, 10.0]})
    bench = equal_weight_benchmark(bars)
    # 둘째날: A +20%, B 0% -> 평균 +10%
    assert abs(bench.iloc[1] - 0.10) < 1e-12
