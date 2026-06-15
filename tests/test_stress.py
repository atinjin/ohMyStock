import pandas as pd
from ohmystock.core.backtest.result import BacktestResult
from ohmystock.core.validation.stress import stress_test, DEFAULT_CRISES


def _result(returns):
    idx = pd.date_range("2024-01-01", periods=len(returns), freq="B")
    r = pd.Series(returns, index=idx, dtype=float)
    eq = 100.0 * (1 + r).cumprod()
    trades = pd.DataFrame(columns=["symbol", "entry_date", "exit_date",
                                   "qty", "pnl", "cost"])
    return BacktestResult(equity_curve=eq, returns=r, trades=trades,
                          positions=pd.DataFrame(index=idx))


def _result_from_equity(values):
    """명시적 DatetimeIndex(영업일)를 가진 equity 곡선으로 결과 구성."""
    idx = pd.date_range("2024-01-01", periods=len(values), freq="B")
    eq = pd.Series(values, index=idx, dtype=float)
    r = eq.pct_change().fillna(0.0)
    trades = pd.DataFrame(columns=["symbol", "entry_date", "exit_date",
                                   "qty", "pnl", "cost"])
    return BacktestResult(equity_curve=eq, returns=r, trades=trades,
                          positions=pd.DataFrame(index=idx))


def test_default_crises_defined():
    assert DEFAULT_CRISES[0][0] == "COVID 2020"
    assert len(DEFAULT_CRISES) == 3
    # 각 항목은 (name, start, end) 3-튜플
    for name, s, e in DEFAULT_CRISES:
        assert isinstance(name, str)
        assert pd.Timestamp(s) <= pd.Timestamp(e)


def test_moderate_drop_passes():
    # 2024-01-01 시작, 영업일 인덱스. 30% 하락을 커스텀 창에 배치.
    # 30영업일: 처음 평탄(100), 창 안에서 100 -> 70 으로 하락.
    values = [100.0] * 5 + [100.0, 95.0, 90.0, 85.0, 80.0,
                            78.0, 76.0, 74.0, 72.0, 70.0] + [70.0] * 15
    res = _result_from_equity(values)
    win = ("t", "2024-01-05", "2024-01-25")
    rep = stress_test(res, windows=[win])
    assert rep.name == "StressTest"
    assert rep.passed is True
    assert abs(rep.value - 0.30) < 0.02
    assert rep.threshold == 0.5


def test_severe_drop_fails():
    # 동일 창에서 ~60% 하락 -> worst mdd >= 0.5 -> 실패.
    values = [100.0] * 5 + [100.0, 90.0, 80.0, 70.0, 60.0,
                            55.0, 50.0, 47.0, 44.0, 40.0] + [40.0] * 15
    res = _result_from_equity(values)
    win = ("t", "2024-01-05", "2024-01-25")
    rep = stress_test(res, windows=[win])
    assert rep.passed is False
    assert rep.value >= 0.5


def test_no_overlap_window_passes():
    # 인덱스와 전혀 겹치지 않는 창 -> 통과, 메시지에 "데이터 없음" 포함.
    res = _result([0.001] * 20)
    win = ("nope", "2099-01-01", "2099-12-31")
    rep = stress_test(res, windows=[win])
    assert rep.passed is True
    assert "데이터 없음" in rep.message
    assert rep.value == 0.0
