import numpy as np
import pandas as pd
from ohmystock.paper.__main__ import build_parser, run_cli


class FakeAdapter:
    def get_daily_bars(self, symbols, start, end):
        idx = pd.date_range("2024-01-01", periods=40, freq="B")
        out = {}
        for i, s in enumerate(symbols):
            closes = np.linspace(10 + i, 30 + i, 40)
            out[s] = pd.DataFrame(
                {"open": closes, "high": closes, "low": closes,
                 "close": closes, "volume": [1e6] * 40}, index=idx)
        return out


def test_cli_init_step_status(tmp_path, capsys):
    db = str(tmp_path / "p.db")
    adapter = FakeAdapter()
    run_cli(["--db", db, "init", "--strategy", "MACrossover",
             "--symbols", "AAPL", "--capital", "1000000",
             "--start", "2024-01-01", "--end", "2024-03-31"], adapter=adapter)
    run_cli(["--db", db, "step"], adapter=adapter)
    run_cli(["--db", db, "status"], adapter=adapter)
    out = capsys.readouterr().out
    assert "초기화" in out
    assert "2024-01-01" in out  # status가 커서 출력
