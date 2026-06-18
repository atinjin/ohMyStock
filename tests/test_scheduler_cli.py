from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from ohmystock.config import Config
from ohmystock.core.calendar.exchange import us_market_calendar
from ohmystock.paper.service import PaperService
from ohmystock.paper.sqlite_store import SqlitePaperStore
from ohmystock.scheduler import run_cli
from ohmystock.scheduler_store import SqliteSchedulerStore

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


def _svc(tmp_path):
    svc = PaperService(SqlitePaperStore(tmp_path / "p.db"), FakeAdapter(), Config())
    svc.init_account("MACrossover", {"short": 3, "long": 10}, ["AAPL"],
                     1_000_000, "2024-06-03", "2024-06-28")
    return svc


def test_run_once_records(tmp_path, capsys):
    store = SqliteSchedulerStore(tmp_path / "p.db")
    res = run_cli(["run-once"], service=_svc(tmp_path), calendar=us_market_calendar(),
                  store=store, now=datetime(2024, 6, 28, 17, 0, tzinfo=ET))
    assert res["status"] == "ok"
    assert "ran" in capsys.readouterr().out
    assert store.last_run()["status"] == "ok"


def test_history_and_last_run(tmp_path, capsys):
    store = SqliteSchedulerStore(tmp_path / "p.db")
    run_cli(["run-once"], service=_svc(tmp_path), calendar=us_market_calendar(),
            store=store, now=datetime(2024, 6, 28, 17, 0, tzinfo=ET))
    hist = run_cli(["history", "--limit", "5"], store=store)
    assert isinstance(hist, list) and len(hist) == 1
    last = run_cli(["last-run"], store=store)
    assert last["last_run"]["status"] == "ok"
    assert last["last_success"]["status"] == "ok"
