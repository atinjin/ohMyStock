import pytest

from datetime import date, datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from ohmystock.config import Config
from ohmystock.core.calendar.exchange import us_market_calendar
from ohmystock.paper.service import PaperService
from ohmystock.paper.sqlite_store import SqlitePaperStore
from ohmystock.scheduler import compute_target_date, run_once

UTCZ = ZoneInfo("UTC")

ET = ZoneInfo("America/New_York")


class FakeAdapter:
    def get_daily_bars(self, symbols, start, end):
        idx = pd.bdate_range("2024-06-03", periods=20)  # 마지막 = 2024-06-28(금)
        out = {}
        for i, s in enumerate(symbols):
            closes = np.linspace(10 + i, 30 + i, 20)
            out[s] = pd.DataFrame(
                {"open": closes, "high": closes, "low": closes,
                 "close": closes, "volume": [1e6] * 20}, index=idx)
        return out


def _service(tmp_path):
    return PaperService(SqlitePaperStore(tmp_path / "p.db"), FakeAdapter(), Config())


def _inited(tmp_path):
    svc = _service(tmp_path)
    svc.init_account("MACrossover", {"short": 3, "long": 10}, ["AAPL"],
                     1_000_000, "2024-06-03", "2024-06-28")
    return svc


def test_target_after_close():
    cal = us_market_calendar()
    assert compute_target_date(cal, datetime(2024, 7, 2, 17, 0, tzinfo=ET)) == date(2024, 7, 2)


def test_target_before_close():
    cal = us_market_calendar()
    assert compute_target_date(cal, datetime(2024, 7, 2, 12, 0, tzinfo=ET)) == date(2024, 7, 1)


def test_target_half_day_after_close():
    cal = us_market_calendar()
    assert compute_target_date(cal, datetime(2024, 7, 3, 14, 0, tzinfo=ET)) == date(2024, 7, 3)


def test_target_weekend():
    cal = us_market_calendar()
    assert compute_target_date(cal, datetime(2024, 7, 6, 10, 0, tzinfo=ET)) == date(2024, 7, 5)


def test_target_holiday():
    cal = us_market_calendar()
    assert compute_target_date(cal, datetime(2024, 7, 4, 10, 0, tzinfo=ET)) == date(2024, 7, 3)


def test_run_once_advances_to_latest(tmp_path):
    svc = _inited(tmp_path)
    res = run_once(svc, us_market_calendar(), datetime(2024, 6, 28, 17, 0, tzinfo=ET))
    assert res["ran"] is True
    assert res["steps"] > 0
    last = pd.bdate_range("2024-06-03", periods=20)[-1].strftime("%Y-%m-%d")
    assert svc.get_state()["cursor_date"] == last


def test_run_once_idempotent(tmp_path):
    svc = _inited(tmp_path)
    cal = us_market_calendar()
    now = datetime(2024, 6, 28, 17, 0, tzinfo=ET)
    run_once(svc, cal, now)
    res2 = run_once(svc, cal, now)
    assert res2["ran"] is False
    assert res2["reason"] == "최신"


def test_run_once_no_account(tmp_path):
    res = run_once(_service(tmp_path), us_market_calendar(),
                   datetime(2024, 6, 28, 17, 0, tzinfo=ET))
    assert res["ran"] is False
    assert res["reason"] == "계좌 없음"


def test_target_requires_tz_aware():
    cal = us_market_calendar()
    with pytest.raises(ValueError):
        compute_target_date(cal, datetime(2024, 7, 2, 17, 0))  # naive


def test_target_normalizes_non_et_timezone():
    cal = us_market_calendar()
    # 2024-07-02 17:00 ET == 21:00 UTC (마감 후) -> 07-02
    assert compute_target_date(cal, datetime(2024, 7, 2, 21, 0, tzinfo=UTCZ)) == date(2024, 7, 2)
    # 2024-07-02 12:00 ET == 16:00 UTC (마감 전) -> 직전거래일 07-01
    assert compute_target_date(cal, datetime(2024, 7, 2, 16, 0, tzinfo=UTCZ)) == date(2024, 7, 1)


def test_run_once_exact_multiday_steps(tmp_path):
    # cursor None -> 데이터 20 거래일 전부 전진 (정확히 20 스텝)
    svc = _inited(tmp_path)
    res = run_once(svc, us_market_calendar(), datetime(2024, 6, 28, 17, 0, tzinfo=ET))
    assert res["ran"] is True
    assert res["steps"] == 20


def test_run_once_before_close_does_not_regress(tmp_path):
    # 06-28 마감 후 전진(커서=06-28). 이후 06-28 마감 전 now -> target=직전거래일(06-27)
    # -> 커서 06-28 >= 06-27 이므로 "최신"(후퇴/재전진 없음)
    svc = _inited(tmp_path)
    cal = us_market_calendar()
    run_once(svc, cal, datetime(2024, 6, 28, 17, 0, tzinfo=ET))
    res = run_once(svc, cal, datetime(2024, 6, 28, 12, 0, tzinfo=ET))
    assert res["ran"] is False
    assert res["reason"] == "최신"
    assert svc.get_state()["cursor_date"] == "2024-06-28"


def test_run_once_data_exhausted_no_op(tmp_path):
    # 데이터 끝(06-28)까지 전진 후, target이 데이터 너머(07-02)면 진전 0 -> "데이터 없음"
    svc = _inited(tmp_path)
    cal = us_market_calendar()
    run_once(svc, cal, datetime(2024, 6, 28, 17, 0, tzinfo=ET))   # 커서 06-28
    res = run_once(svc, cal, datetime(2024, 7, 2, 17, 0, tzinfo=ET))  # target 07-02 > 06-28
    assert res["ran"] is False
    assert res["reason"] == "데이터 없음"
    assert svc.get_state()["cursor_date"] == "2024-06-28"  # 상태 불변(무해)
