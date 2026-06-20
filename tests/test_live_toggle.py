from datetime import date

import httpx
import numpy as np
import pandas as pd
import pytest

from ohmystock.config import Config
from ohmystock.core.broker.alpaca import AlpacaBroker
from ohmystock.core.strategy.momentum import Momentum
from ohmystock.live import live_execute, run_cli


class FakeAdapter:
    def get_daily_bars(self, symbols, start, end):
        idx = pd.date_range("2024-01-01", periods=60, freq="B")
        out = {}
        for i, s in enumerate(symbols):
            closes = np.linspace(10 + i, 30 + i, 60)
            out[s] = pd.DataFrame(
                {"open": closes, "high": closes, "low": closes,
                 "close": closes, "volume": [1e6] * 60}, index=idx)
        return out


def test_live_execute_dry_run():
    res = live_execute(["AAPL", "MSFT"], date(2024, 1, 1), date(2024, 3, 1),
                       FakeAdapter(), Momentum(lookback=20, top_k=2), Config(),
                       mode="dry-run", env={})
    assert res["mode"] == "dry-run"
    assert isinstance(res["orders"], list)
    assert all(o["side"] in ("buy", "sell") for o in res["orders"])


def test_live_execute_live_submits_orders():
    posted = []

    def handler(request):
        if request.url.path == "/v2/account":
            return httpx.Response(200, json={"equity": "100000", "cash": "100000"})
        if request.url.path == "/v2/positions":
            return httpx.Response(200, json=[])
        if request.url.path == "/v2/orders":
            posted.append(request)
            return httpx.Response(200, json={"id": "x"})
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler),
                          base_url="https://paper-api.alpaca.markets")
    broker = AlpacaBroker(api_key="k", secret_key="s", client=client)
    res = live_execute(["AAPL", "MSFT"], date(2024, 1, 1), date(2024, 3, 1),
                       FakeAdapter(), Momentum(lookback=20, top_k=2), Config(),
                       mode="live", broker=broker, env={})
    assert res["mode"] == "live"
    assert len(posted) >= 1


def test_run_cli_default_dry_run(capsys):
    res = run_cli(["--symbols", "AAPL,MSFT", "--strategy", "Momentum",
                   "--start", "2024-01-01", "--end", "2024-03-01"],
                  adapter=FakeAdapter(), env={})
    assert res["mode"] == "dry-run"
    assert "mode" in capsys.readouterr().out


def test_run_cli_live_without_keys_raises():
    with pytest.raises(ValueError):
        run_cli(["--mode", "live", "--symbols", "AAPL",
                 "--start", "2024-01-01", "--end", "2024-03-01"],
                adapter=FakeAdapter(), env={})


def test_live_execute_rejects_live_broker_in_dry_run():
    # 실브로커를 dry-run으로 주입 -> 모순 거부 (실주문이 'dry-run'으로 오기록되는 것 차단)
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"equity": "1", "cash": "1"})),
        base_url="https://paper-api.alpaca.markets")
    broker = AlpacaBroker(api_key="k", secret_key="s", client=client)
    with pytest.raises(ValueError):
        live_execute(["AAPL"], date(2024, 1, 1), date(2024, 3, 1),
                     FakeAdapter(), Momentum(lookback=20, top_k=2), Config(),
                     mode="dry-run", broker=broker, env={})


def test_live_execute_rejects_paper_broker_in_live():
    from ohmystock.core.broker.paper import PaperBroker
    with pytest.raises(ValueError):
        live_execute(["AAPL"], date(2024, 1, 1), date(2024, 3, 1),
                     FakeAdapter(), Momentum(lookback=20, top_k=2), Config(),
                     mode="live", broker=PaperBroker(cash=1000.0), env={})


def test_live_execute_broker_name_forwarded():
    # broker_name 이 build_broker 까지 전달되는지 — toss + 키 없음 → ValueError
    with pytest.raises(ValueError):
        live_execute(["AAPL"], date(2024, 1, 1), date(2024, 3, 1),
                     FakeAdapter(), Momentum(lookback=20, top_k=2), Config(),
                     mode="live", broker_name="toss", env={})


def test_run_cli_broker_flag_forwarded():
    # --broker toss + live + 키 없음 → ValueError (선택이 build_broker 까지 전달됨)
    with pytest.raises(ValueError):
        run_cli(["--mode", "live", "--broker", "toss", "--symbols", "AAPL",
                 "--start", "2024-01-01", "--end", "2024-03-01"],
                adapter=FakeAdapter(), env={})
