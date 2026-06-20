import httpx
import pytest

from ohmystock.broker_select import resolve_mode, build_broker
from ohmystock.core.broker.paper import PaperBroker
from ohmystock.core.broker.alpaca import AlpacaBroker


def test_resolve_default_dry_run():
    assert resolve_mode(None, env={}) == "dry-run"


def test_resolve_cli_live():
    assert resolve_mode("live", env={}) == "live"


def test_resolve_env_live():
    assert resolve_mode(None, env={"OHMYSTOCK_MODE": "live"}) == "live"


def test_resolve_cli_overrides_env():
    assert resolve_mode("dry-run", env={"OHMYSTOCK_MODE": "live"}) == "dry-run"


def test_resolve_invalid_raises():
    with pytest.raises(ValueError):
        resolve_mode("paper", env={})


def test_build_dry_run_paper():
    b = build_broker("dry-run", cash=1000.0, env={})
    assert isinstance(b, PaperBroker)
    assert b.cash == 1000.0


def test_build_live_without_keys_raises():
    with pytest.raises(ValueError):
        build_broker("live", cash=1000.0, env={})


def test_build_live_with_keys():
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={})))
    b = build_broker("live", cash=1000.0,
                     env={"ALPACA_API_KEY": "k", "ALPACA_SECRET_KEY": "s"}, client=client)
    assert isinstance(b, AlpacaBroker)
    assert b.api_key == "k"


def test_build_live_base_url_override():
    b = build_broker("live", cash=1000.0, env={
        "ALPACA_API_KEY": "k", "ALPACA_SECRET_KEY": "s",
        "ALPACA_BASE_URL": "https://api.alpaca.markets"})
    assert isinstance(b, AlpacaBroker)
    assert "api.alpaca.markets" in str(b.client.base_url)
    assert "paper" not in str(b.client.base_url)


def test_resolve_empty_string_env_raises():
    # OHMYSTOCK_MODE="" 는 조용히 dry-run/live로 빠지지 않고 ValueError
    with pytest.raises(ValueError):
        resolve_mode(None, env={"OHMYSTOCK_MODE": ""})


def test_build_dry_run_ignores_alpaca_keys():
    # dry-run은 키가 있어도 PaperBroker (실브로커로 바뀌지 않음)
    b = build_broker("dry-run", cash=1000.0,
                     env={"ALPACA_API_KEY": "k", "ALPACA_SECRET_KEY": "s"})
    assert isinstance(b, PaperBroker)


def test_resolve_broker_default_alpaca():
    from ohmystock.broker_select import resolve_broker
    assert resolve_broker(None, env={}) == "alpaca"


def test_resolve_broker_cli():
    from ohmystock.broker_select import resolve_broker
    assert resolve_broker("toss", env={}) == "toss"


def test_resolve_broker_env():
    from ohmystock.broker_select import resolve_broker
    assert resolve_broker(None, env={"OHMYSTOCK_BROKER": "kis"}) == "kis"


def test_resolve_broker_cli_overrides_env():
    from ohmystock.broker_select import resolve_broker
    assert resolve_broker("alpaca", env={"OHMYSTOCK_BROKER": "kis"}) == "alpaca"


def test_resolve_broker_invalid_raises():
    from ohmystock.broker_select import resolve_broker
    import pytest
    with pytest.raises(ValueError):
        resolve_broker("ibkr", env={})
