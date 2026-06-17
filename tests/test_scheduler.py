from datetime import date, datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from ohmystock.config import Config
from ohmystock.core.calendar.exchange import us_market_calendar
from ohmystock.paper.service import PaperService
from ohmystock.paper.sqlite_store import SqlitePaperStore
from ohmystock.scheduler import compute_target_date, run_once

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
