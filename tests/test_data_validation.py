import pandas as pd
import numpy as np
from ohmystock.core.data.validation import validate_bars

def _good():
    idx = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    return pd.DataFrame(
        {"open": [10.0, 11.0, 11.5], "high": [12.0, 12.0, 12.0],
         "low": [9.0, 10.0, 11.0], "close": [11.0, 11.5, 11.8],
         "volume": [100, 120, 110]}, index=idx)

def test_clean_data_passes():
    report = validate_bars({"AAPL": _good()})
    assert report.passed is True
    assert report.issues == []

def test_detects_nonpositive_price():
    df = _good()
    df.loc[df.index[1], "close"] = 0.0
    report = validate_bars({"AAPL": df})
    assert report.passed is False
    assert any("0/음수 가격" in i for i in report.issues)

def test_detects_duplicate_index():
    df = _good()
    df = pd.concat([df, df.iloc[[0]]])
    report = validate_bars({"AAPL": df})
    assert report.passed is False
    assert any("중복" in i for i in report.issues)

def test_detects_nan():
    df = _good()
    df.loc[df.index[2], "close"] = np.nan
    report = validate_bars({"AAPL": df})
    assert report.passed is False
    assert any("결측" in i for i in report.issues)
