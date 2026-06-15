import json
from datetime import date

import numpy as np
import pandas as pd

from ohmystock.config import Config
from ohmystock.core.data.cache import ParquetCache
from ohmystock.core.data.yfinance_adapter import YFinanceAdapter
from ohmystock.report import build_strategy, full_report


def _fake_dl(symbol, start, end):
    # 완만한 상승 추세의 합성 OHLCV 약 120일
    n = 120
    closes = list(np.linspace(10, 18, n))
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes,
         "close": closes, "volume": [1000] * n}, index=idx)


def _adapter(tmp_path):
    return YFinanceAdapter(cache=ParquetCache(tmp_path), downloader=_fake_dl)


def test_full_report_shape(tmp_path):
    report = full_report(
        symbols=["AAPL", "MSFT"], start=date(2024, 1, 1), end=date(2024, 6, 30),
        adapter=_adapter(tmp_path), strategy=build_strategy("MACrossover", {"short": 5, "long": 20}),
        config=Config())

    assert report["strategy"] == "MACrossover"
    assert report["symbols"] == ["AAPL", "MSFT"]
    assert report["start"] == "2024-01-01"
    assert report["end"] == "2024-06-30"
    assert isinstance(report["final_equity"], float)
    assert "data_validation" in report
    assert isinstance(report["data_validation"]["passed"], bool)
    assert len(report["equity_curve"]) > 0
    assert set(report["equity_curve"][0].keys()) == {"date", "value"}


def test_full_report_metrics_and_validations(tmp_path):
    report = full_report(
        symbols=["AAPL", "MSFT"], start=date(2024, 1, 1), end=date(2024, 6, 30),
        adapter=_adapter(tmp_path), strategy=build_strategy("Momentum", {"lookback": 20, "top_k": 1}),
        config=Config())

    assert len(report["metrics"]) == 6
    metric_keys = [m["key"] for m in report["metrics"]]
    assert metric_keys == ["mdd", "sharpe", "sortino", "calmar", "profit_factor", "recovery_factor"]
    for m in report["metrics"]:
        assert isinstance(m["value"], float)
        assert isinstance(m["display"], str)

    # 명세의 그룹 분해 G2(3)+G3(4)+G4(4)=11 (CLI와 동일)
    assert len(report["validations"]) == 11
    for v in report["validations"]:
        assert v["group"] in {"G2", "G3", "G4"}
        assert isinstance(v["value"], float)
        assert isinstance(v["passed"], bool)
    groups = [v["group"] for v in report["validations"]]
    assert groups == ["G2"] * 3 + ["G3"] * 4 + ["G4"] * 4


def test_full_report_json_serializable(tmp_path):
    report = full_report(
        symbols=["AAPL"], start=date(2024, 1, 1), end=date(2024, 6, 30),
        adapter=_adapter(tmp_path), strategy=build_strategy("MACrossover", {}),
        config=Config())
    # numpy 타입이 섞여 있으면 여기서 실패한다
    json.dumps(report)


def test_build_strategy_unknown():
    import pytest
    with pytest.raises(ValueError):
        build_strategy("Nope", {})
