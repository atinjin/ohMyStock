import numpy as np
import pandas as pd

from ohmystock.config import Config
from ohmystock.core.strategy.ma_crossover import MACrossover
from ohmystock.core.validation.overfitting import overfitting


def _bars_from_closes(closes_by_sym: dict) -> dict[str, pd.DataFrame]:
    n = len(next(iter(closes_by_sym.values())))
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    bars = {}
    for sym, close in closes_by_sym.items():
        close = np.asarray(close, dtype=float)
        bars[sym] = pd.DataFrame(
            {"open": close, "high": close * 1.01, "low": close * 0.99,
             "close": close, "volume": 1_000_000.0},
            index=idx,
        )
    return bars


def _noisy_uptrend(n_symbols=3, n_days=400, seed=0):
    """드리프트+노이즈가 있는 상승추세(비퇴화). 양 구간 모두 유한·유사 Sharpe."""
    rng = np.random.default_rng(seed)
    out = {}
    for i in range(n_symbols):
        steps = rng.normal(0.0012, 0.006, n_days)        # 양의 드리프트 + 실 노이즈
        out[f"SYM{i}"] = 100.0 * np.cumprod(1.0 + steps)
    return _bars_from_closes(out)


def _rise_then_crash(n_symbols=3, n_rise=280, n_crash=120, seed=1):
    """앞 70% 상승 후 뒤 30% 폭락. OOS(뒤 30%)에서 전략이 무너지도록."""
    rng = np.random.default_rng(seed)
    out = {}
    for i in range(n_symbols):
        up = np.cumprod(1.0 + rng.normal(0.0015, 0.006, n_rise))
        down = up[-1] * np.cumprod(1.0 + rng.normal(-0.004, 0.012, n_crash))
        out[f"SYM{i}"] = 100.0 * np.concatenate([up, down])
    return _bars_from_closes(out)


def _factory(p):
    return MACrossover(p[0], p[1])


_GRID = [(10, 50), (20, 60), (20, 100)]


def test_robust_uptrend_passes():
    rep = overfitting(_factory, _GRID, _noisy_uptrend(), Config())
    assert rep.name == "Overfitting"
    assert np.isfinite(rep.value)
    assert rep.threshold == 1.0
    # 견고한 상승추세: 최적 IS 파라미터의 OOS도 양수이고 격차가 작음 -> 통과
    assert rep.passed is True
    assert rep.value <= 1.0          # 격차가 gap_limit 이내(임계가 실제로 작동)


def test_regime_break_fails():
    # 상승 후 폭락: IS는 좋지만 OOS가 무너짐 -> 통과 실패
    rep = overfitting(_factory, _GRID, _rise_then_crash(), Config())
    assert rep.name == "Overfitting"
    assert rep.passed is False


def test_empty_grid():
    rep = overfitting(_factory, [], _noisy_uptrend(), Config())
    assert rep.value == 0.0
    assert rep.passed is False
    assert rep.threshold == 1.0
    assert "비어있음" in rep.message
