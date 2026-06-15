import numpy as np
import pandas as pd
from datetime import date
from ohmystock.config import Config
from ohmystock.core.data.yfinance_adapter import YFinanceAdapter
from ohmystock.core.data.cache import ParquetCache
from ohmystock.core.strategy.ma_crossover import MACrossover
from ohmystock.cli import build_report

def _fake_dl(symbol, start, end):
    closes = list(np.linspace(10, 30, 80))
    idx = pd.date_range("2024-01-01", periods=80, freq="B")
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes,
         "close": closes, "volume": [100] * 80}, index=idx)

def test_build_report_contains_metrics(tmp_path):
    adapter = YFinanceAdapter(cache=ParquetCache(tmp_path), downloader=_fake_dl)
    report = build_report(
        symbols=["AAPL"], start=date(2024, 1, 1), end=date(2024, 4, 30),
        adapter=adapter, strategy=MACrossover(short=5, long=20), config=Config())
    assert "MDD" in report
    assert "Sharpe" in report
    assert "Profit Factor" in report
    assert "데이터 검증" in report
    # G2 자금·리스크 섹션
    assert "자금·리스크" in report
    assert "Kelly" in report
    assert "RuinProbability" in report
    assert "Capacity" in report
    # G3 견고성 섹션
    assert "견고성" in report
    assert "OutOfSample" in report
    assert "WalkForward" in report
    assert "MonteCarlo" in report
    assert "StressTest" in report
    # G4 시장구조 섹션
    assert "시장구조" in report
    assert "Regime" in report
    assert "Correlation" in report
    assert "FactorExposure" in report
    assert "EconomicEdge" in report
