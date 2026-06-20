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


def test_build_live_base_url_override_requires_ack():
    env = {"ALPACA_API_KEY": "k", "ALPACA_SECRET_KEY": "s",
           "ALPACA_BASE_URL": "https://api.alpaca.markets"}
    with pytest.raises(ValueError):                       # 동의 없음 → 거부
        build_broker("live", cash=1000.0, broker_name="alpaca", env=env)
    env["OHMYSTOCK_ALLOW_REAL_MONEY"] = "1"
    b = build_broker("live", cash=1000.0, broker_name="alpaca", env=env)
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


def _mock_client():
    return httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={})))


def test_build_dry_run_ignores_broker_name():
    b = build_broker("dry-run", cash=1000.0, broker_name="toss",
                     env={"OHMYSTOCK_BROKER": "toss"})
    assert isinstance(b, PaperBroker)


def test_build_live_kis_paper_no_ack():
    from ohmystock.core.broker.kis import KISBroker
    env = {"KIS_APP_KEY": "k", "KIS_APP_SECRET": "s", "KIS_ACCOUNT_NO": "12345678-01"}
    b = build_broker("live", cash=1000.0, broker_name="kis", env=env, client=_mock_client())
    assert isinstance(b, KISBroker)
    assert b.paper is True


def test_build_live_kis_missing_account_raises():
    env = {"KIS_APP_KEY": "k", "KIS_APP_SECRET": "s"}     # 계좌번호 없음
    with pytest.raises(ValueError):
        build_broker("live", cash=1000.0, broker_name="kis", env=env, client=_mock_client())


def test_build_live_kis_real_requires_ack():
    from ohmystock.core.broker.kis import KISBroker
    env = {"KIS_APP_KEY": "k", "KIS_APP_SECRET": "s", "KIS_ACCOUNT_NO": "12345678-01",
           "OHMYSTOCK_KIS_PAPER": "0"}
    with pytest.raises(ValueError):                       # 실전 + 동의 없음
        build_broker("live", cash=1000.0, broker_name="kis", env=env, client=_mock_client())
    env["OHMYSTOCK_ALLOW_REAL_MONEY"] = "yes"
    b = build_broker("live", cash=1000.0, broker_name="kis", env=env, client=_mock_client())
    assert b.paper is False


def test_build_live_toss_requires_ack():
    from ohmystock.core.broker.toss import TossBroker
    env = {"TOSS_CLIENT_ID": "c", "TOSS_CLIENT_SECRET": "s"}
    with pytest.raises(ValueError):                       # TOSS는 항상 실제 돈 → 동의 필요
        build_broker("live", cash=1000.0, broker_name="toss", env=env, client=_mock_client())
    env["OHMYSTOCK_ALLOW_REAL_MONEY"] = "1"
    b = build_broker("live", cash=1000.0, broker_name="toss", env=env, client=_mock_client())
    assert isinstance(b, TossBroker)


def test_build_live_toss_missing_keys_raises():
    env = {"OHMYSTOCK_ALLOW_REAL_MONEY": "1"}             # 동의는 있으나 키 없음
    with pytest.raises(ValueError):
        build_broker("live", cash=1000.0, broker_name="toss", env=env, client=_mock_client())


def test_build_live_alpaca_paper_in_custom_host_requires_ack():
    # 호스트 allowlist 하드닝: "paper"가 호스트에 들어간 비-Alpaca 실거래 URL도 동의 필요
    env = {"ALPACA_API_KEY": "k", "ALPACA_SECRET_KEY": "s",
           "ALPACA_BASE_URL": "https://paper.fake-live.example"}
    with pytest.raises(ValueError):                       # 동의 없음 → 거부
        build_broker("live", cash=1000.0, broker_name="alpaca", env=env, client=_mock_client())
    env["OHMYSTOCK_ALLOW_REAL_MONEY"] = "1"
    b = build_broker("live", cash=1000.0, broker_name="alpaca", env=env, client=_mock_client())
    assert isinstance(b, AlpacaBroker)


def test_build_live_alpaca_default_paper_host_no_ack():
    # 진짜 Alpaca 페이퍼 호스트(기본)는 동의 없이 생성(가짜 돈)
    env = {"ALPACA_API_KEY": "k", "ALPACA_SECRET_KEY": "s"}
    b = build_broker("live", cash=1000.0, broker_name="alpaca", env=env, client=_mock_client())
    assert isinstance(b, AlpacaBroker)


@pytest.mark.parametrize("ack", ["0", "", " ", "no", "false", "2", "y"])
def test_real_money_ack_falsy_values_refused(ack):
    env = {"TOSS_CLIENT_ID": "c", "TOSS_CLIENT_SECRET": "s",
           "OHMYSTOCK_ALLOW_REAL_MONEY": ack}
    with pytest.raises(ValueError):
        build_broker("live", cash=1000.0, broker_name="toss", env=env, client=_mock_client())


@pytest.mark.parametrize("ack", ["1", "true", "yes", " TRUE ", "Yes"])
def test_real_money_ack_truthy_values_accepted(ack):
    from ohmystock.core.broker.toss import TossBroker
    env = {"TOSS_CLIENT_ID": "c", "TOSS_CLIENT_SECRET": "s",
           "OHMYSTOCK_ALLOW_REAL_MONEY": ack}
    b = build_broker("live", cash=1000.0, broker_name="toss", env=env, client=_mock_client())
    assert isinstance(b, TossBroker)
