import json
from datetime import datetime, timedelta

import httpx
import pytest

from ohmystock.core.broker.base import Account, Order
from ohmystock.core.broker.toss import TossBroker

_BASE = "https://openapi.tossinvest.com"


def _make_broker(handler, **kwargs):
    """MockTransport 기반 오프라인 TossBroker. 네트워크 미사용."""
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url=_BASE)
    kwargs.setdefault("client_id", "CID")
    kwargs.setdefault("client_secret", "CSEC")
    kwargs.setdefault("account_seq", "42")
    return TossBroker(client=client, **kwargs)


def test_issue_token_sets_token_and_expiry():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"access_token": "tok123",
                                         "token_type": "Bearer", "expires_in": 3600})

    fixed = datetime(2026, 6, 20, 9, 0, 0)
    broker = _make_broker(handler, now=lambda: fixed)
    token = broker.issue_token()

    assert token == "tok123"
    assert broker.access_token == "tok123"
    assert broker.token_expires_at == fixed + timedelta(seconds=3600)
    assert captured["method"] == "POST"
    assert captured["path"] == "/oauth2/token"
    assert "grant_type=client_credentials" in captured["body"]
    assert "client_id=CID" in captured["body"]


def test_env_credential_fallback(monkeypatch):
    monkeypatch.setenv("TOSS_CLIENT_ID", "env_id")
    monkeypatch.setenv("TOSS_CLIENT_SECRET", "env_secret")
    monkeypatch.setenv("TOSS_ACCOUNT_SEQ", "777")

    client = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={})), base_url=_BASE)
    broker = TossBroker(client=client)

    assert broker.client_id == "env_id"
    assert broker.client_secret == "env_secret"
    assert broker._account_seq == "777"


def test_ensure_token_refreshes_when_expired():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"access_token": "fresh", "expires_in": 3600})

    fixed = datetime(2026, 6, 20, 9, 0, 0)
    # 토큰은 있으나 만료시각이 과거 → 재발급되어야 함
    broker = _make_broker(handler, now=lambda: fixed,
                          access_token="stale",
                          token_expires_at=fixed - timedelta(seconds=1))
    broker._ensure_token()

    assert calls["n"] == 1
    assert broker.access_token == "fresh"


def test_ensure_token_keeps_valid_token():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("유효 토큰인데 재발급 호출됨")

    fixed = datetime(2026, 6, 20, 9, 0, 0)
    broker = _make_broker(handler, now=lambda: fixed,
                          access_token="good",
                          token_expires_at=fixed + timedelta(hours=1))
    broker._ensure_token()  # 호출돼도 네트워크 안 침

    assert broker.access_token == "good"


def test_result_unwraps_envelope_and_raises_without_result():
    broker = _make_broker(lambda r: httpx.Response(200, json={}))
    ok = httpx.Response(200, json={"result": {"x": 1}})
    assert broker._result(ok) == {"x": 1}
    with pytest.raises(ValueError):
        broker._result(httpx.Response(200, json={"no_result": True}))
