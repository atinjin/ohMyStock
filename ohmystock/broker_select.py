import os

from ohmystock.core.broker.paper import PaperBroker
from ohmystock.core.broker.alpaca import AlpacaBroker

_VALID_MODES = ("dry-run", "live")
_DEFAULT_PAPER_URL = "https://paper-api.alpaca.markets"


def resolve_mode(cli_mode: str | None = None, env: dict | None = None) -> str:
    """모드 해석: CLI > env(OHMYSTOCK_MODE) > 기본 'dry-run'. 잘못된 값은 ValueError."""
    env = os.environ if env is None else env
    mode = cli_mode if cli_mode is not None else env.get("OHMYSTOCK_MODE", "dry-run")
    if mode not in _VALID_MODES:
        raise ValueError(f"알 수 없는 모드: {mode!r} (dry-run|live)")
    return mode


def build_broker(mode: str, *, cash: float, env: dict | None = None, client=None):
    """모드에 맞는 Broker 생성. live는 Alpaca 키 필수(없으면 거부)."""
    env = os.environ if env is None else env
    if mode == "dry-run":
        return PaperBroker(cash=cash)
    if mode == "live":
        key = env.get("ALPACA_API_KEY")
        secret = env.get("ALPACA_SECRET_KEY")
        if not key or not secret:
            raise ValueError(
                "실계좌(live) 모드인데 ALPACA_API_KEY/ALPACA_SECRET_KEY가 없습니다. "
                "키를 설정하거나 dry-run으로 실행하세요."
            )
        base_url = env.get("ALPACA_BASE_URL", _DEFAULT_PAPER_URL)
        return AlpacaBroker(api_key=key, secret_key=secret, base_url=base_url, client=client)
    raise ValueError(f"알 수 없는 모드: {mode!r}")
