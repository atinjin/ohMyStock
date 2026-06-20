import os
from urllib.parse import urlparse

from ohmystock.core.broker.paper import PaperBroker
from ohmystock.core.broker.alpaca import AlpacaBroker
from ohmystock.core.broker.kis import KISBroker
from ohmystock.core.broker.toss import TossBroker

_VALID_MODES = ("dry-run", "live")
_DEFAULT_PAPER_URL = "https://paper-api.alpaca.markets"
_VALID_BROKERS = ("alpaca", "toss", "kis")
_TRUTHY = ("1", "true", "yes")
# 가짜 돈(모의)으로 인정하는 Alpaca 호스트 allowlist. 그 외 호스트는 모두 실제 돈 취급.
_ALPACA_PAPER_HOSTS = ("paper-api.alpaca.markets",)


def resolve_mode(cli_mode: str | None = None, env: dict | None = None) -> str:
    """모드 해석: CLI > env(OHMYSTOCK_MODE) > 기본 'dry-run'. 잘못된 값은 ValueError."""
    env = os.environ if env is None else env
    mode = cli_mode if cli_mode is not None else env.get("OHMYSTOCK_MODE", "dry-run")
    if mode not in _VALID_MODES:
        raise ValueError(f"알 수 없는 모드: {mode!r} (dry-run|live)")
    return mode


def resolve_broker(cli_broker: str | None = None, env: dict | None = None) -> str:
    """브로커 해석: CLI > env(OHMYSTOCK_BROKER) > 기본 'alpaca'. 잘못된 값 ValueError."""
    env = os.environ if env is None else env
    broker = cli_broker if cli_broker is not None else env.get("OHMYSTOCK_BROKER", "alpaca")
    if broker not in _VALID_BROKERS:
        raise ValueError(f"알 수 없는 브로커: {broker!r} (alpaca|toss|kis)")
    return broker


def _require_real_money_ack(env, label):
    val = (env.get("OHMYSTOCK_ALLOW_REAL_MONEY") or "").strip().lower()
    if val not in _TRUTHY:
        raise ValueError(
            f"{label} — 실제 돈이 걸린 주문입니다. OHMYSTOCK_ALLOW_REAL_MONEY=1 을 설정해 "
            f"명시적으로 동의하거나, 가짜 돈(페이퍼/모의) 구성 또는 dry-run으로 실행하세요."
        )


def _build_alpaca(env, client):
    key = env.get("ALPACA_API_KEY")
    secret = env.get("ALPACA_SECRET_KEY")
    if not key or not secret:
        raise ValueError(
            "alpaca live 모드인데 ALPACA_API_KEY/ALPACA_SECRET_KEY가 없습니다.")
    base_url = env.get("ALPACA_BASE_URL", _DEFAULT_PAPER_URL)
    host = (urlparse(base_url).hostname or "").lower()
    if host not in _ALPACA_PAPER_HOSTS:   # allowlist 외 호스트는 실제 돈 취급(fail-safe)
        _require_real_money_ack(env, f"Alpaca 라이브({base_url})")
    return AlpacaBroker(api_key=key, secret_key=secret, base_url=base_url, client=client)


def _build_kis(env, client):
    key = env.get("KIS_APP_KEY")
    secret = env.get("KIS_APP_SECRET")
    account = env.get("KIS_ACCOUNT_NO")
    if not key or not secret or not account:
        raise ValueError(
            "kis live 모드인데 KIS_APP_KEY/KIS_APP_SECRET/KIS_ACCOUNT_NO가 없습니다.")
    paper = env.get("OHMYSTOCK_KIS_PAPER", "1").strip().lower() not in ("0", "false", "no")
    if not paper:
        _require_real_money_ack(env, "KIS 실전")
    return KISBroker(app_key=key, app_secret=secret, account_no=account,
                     paper=paper, client=client)


def _build_toss(env, client):
    cid = env.get("TOSS_CLIENT_ID")
    csec = env.get("TOSS_CLIENT_SECRET")
    if not cid or not csec:
        raise ValueError(
            "toss live 모드인데 TOSS_CLIENT_ID/TOSS_CLIENT_SECRET가 없습니다.")
    _require_real_money_ack(env, "TOSS(샌드박스 없음)")
    account_seq = env.get("TOSS_ACCOUNT_SEQ")
    return TossBroker(client_id=cid, client_secret=csec,
                      account_seq=account_seq, client=client)


def build_broker(mode, *, cash, env=None, client=None, broker_name=None):
    """모드+브로커에 맞는 Broker 생성. live는 키 가드, 실제 돈은 명시 동의 필요."""
    env = os.environ if env is None else env
    if mode == "dry-run":
        return PaperBroker(cash=cash)
    if mode == "live":
        broker = resolve_broker(broker_name, env)
        if broker == "alpaca":
            return _build_alpaca(env, client)
        if broker == "kis":
            return _build_kis(env, client)
        return _build_toss(env, client)
    raise ValueError(f"알 수 없는 모드: {mode!r}")
