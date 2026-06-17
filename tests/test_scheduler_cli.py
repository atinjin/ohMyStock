from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from ohmystock.config import Config
from ohmystock.core.calendar.exchange import us_market_calendar
from ohmystock.paper.service import PaperService
from ohmystock.paper.sqlite_store import SqlitePaperStore
from ohmystock.scheduler import run_cli

ET = ZoneInfo("America/New_York")


class FakeAdapter:
    def get_daily_bars(self, symbols, start, end):
        idx = pd.bdate_range("2024-06-03", periods=20)
        out = {}
        for i, s in enumerate(symbols):
            closes = np.linspace(10 + i, 30 + i, 20)
            out[s] = pd.DataFrame(
                {"open": closes, "high": closes, "low": closes,
                 "close": closes, "volume": [1e6] * 20}, index=idx)
        return out


def test_run_cli_run_once(tmp_path, capsys):
    svc = PaperService(SqlitePaperStore(tmp_path / "p.db"), FakeAdapter(), Config())
    svc.init_account("MACrossover", {"short": 3, "long": 10}, ["AAPL"],
                     1_000_000, "2024-06-03", "2024-06-28")
    res = run_cli(["run-once"], service=svc, calendar=us_market_calendar(),
                  now=datetime(2024, 6, 28, 17, 0, tzinfo=ET))
    assert res["ran"] is True
    assert "ran" in capsys.readouterr().out
