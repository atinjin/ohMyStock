# 드라이런 ↔ 실계좌 모드 토글 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** dry-run/live 모드 토글 + API 키 가드로, 실주문이 명시적 live 모드 + Alpaca 키일 때만 나가게 한다.

**Architecture:** `broker_select.py`(resolve_mode + build_broker[가드]) + `live.py`에 `live_execute`(모드 인지: dry-run=PaperBroker 시뮬, live=AlpacaBroker 실주문) + CLI `--mode`. 기존 `rebalance`/`RiskGuard`/브로커 재사용.

**Tech Stack:** Python 3.11 stdlib os/argparse, httpx(MockTransport 테스트), 기존 코어.

## Global Constraints

- 테스트 `uv run pytest <path> -q`. "VIRTUAL_ENV 3.9.11 ... ignored" 경고 무해. 전부 오프라인(env/broker/adapter 주입, httpx MockTransport).
- 기본 모드는 항상 **dry-run**. live+키없음 → **`ValueError`로 거부**(조용한 폴백 금지).
- 모드 우선순위: **CLI 플래그 > 환경변수 `OHMYSTOCK_MODE` > "dry-run"**.

---

## 참고 — 재사용 (구현됨)

- `ohmystock/core/broker/paper.py::PaperBroker(cash)` (`.cash`, set_prices, get_account, get_positions, submit_order)
- `ohmystock/core/broker/alpaca.py::AlpacaBroker(api_key=None, secret_key=None, base_url="https://paper-api.alpaca.markets", client=None)` — `.api_key`/`.client`; get_account/get_positions/submit_order(REST). env `ALPACA_API_KEY`/`ALPACA_SECRET_KEY` 폴백.
- `ohmystock/core/broker/rebalance.py::rebalance(strategy, bars, broker, risk_guard, config, max_position_weight=None) -> list[Order]` (Order: .symbol/.side/.notional; broker.submit_order 호출)
- `ohmystock/core/broker/risk.py::RiskGuard(config, peak_equity)`; `ohmystock/report.py::build_strategy(name, params)`; `ohmystock/config.py::Config`.
- `ohmystock/live.py`(기존): `live_preview(...)` + `main()`. **`live_preview`는 변경하지 않는다**(서버/대시보드/test_live 보존).

---

## Task 1: broker_select (resolve_mode + build_broker 가드)

**Files:** Create `ohmystock/broker_select.py`; Test `tests/test_broker_select.py`

**Interfaces:**
- Produces: `resolve_mode(cli_mode: str|None=None, env: dict|None=None) -> str` ("dry-run"|"live"); `build_broker(mode: str, *, cash: float, env: dict|None=None, client=None) -> Broker` (dry-run→PaperBroker, live→AlpacaBroker, live+키없음→ValueError).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_broker_select.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_broker_select.py -q`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write `ohmystock/broker_select.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_broker_select.py -q`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add ohmystock/broker_select.py tests/test_broker_select.py
git commit -m "feat: add broker_select (mode resolution + build_broker with API key guard)"
```

---

## Task 2: live_execute + CLI --mode

**Files:** Modify `ohmystock/live.py`; Test `tests/test_live_toggle.py`

**Interfaces:**
- Consumes: `resolve_mode`/`build_broker` (Task 1), `rebalance`/`RiskGuard`/`PaperBroker`, `build_strategy`.
- Produces: `live_execute(symbols, start, end, adapter, strategy, config, *, mode="dry-run", env=None, broker=None, max_position_weight=None) -> dict` (키 `mode`/`strategy`/`symbols`/`account_before`/`account_after`/`orders`/`risk`); `run_cli(argv=None, *, adapter=None, env=None) -> dict`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_live_toggle.py
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
    assert len(posted) >= 1   # 실주문이 제출됨(POST /v2/orders)


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_live_toggle.py -q`
Expected: FAIL (ImportError: cannot import name 'live_execute')

- [ ] **Step 3: Modify `ohmystock/live.py`**

Add to the imports at the top (with the existing imports):
```python
import argparse
from datetime import date

from ohmystock.broker_select import resolve_mode, build_broker
from ohmystock.report import build_strategy
```
(`PaperBroker`, `RiskGuard`, `rebalance`, `Config`, `ParquetCache`, `YFinanceAdapter` are already imported in live.py.)

Append `live_execute` AFTER the existing `live_preview` function:
```python
def live_execute(symbols, start, end, adapter, strategy, config, *,
                 mode="dry-run", env=None, broker=None,
                 max_position_weight=None) -> dict:
    """모드 인지 실행. dry-run=PaperBroker 시뮬, live=AlpacaBroker 실주문."""
    resolved = resolve_mode(mode, env)
    bars = adapter.get_daily_bars(symbols, start, end)
    if broker is None:
        broker = build_broker(resolved, cash=config.initial_capital, env=env)
    if isinstance(broker, PaperBroker):
        broker.set_prices({s: float(df["close"].iloc[-1]) for s, df in bars.items()})

    before = broker.get_account()
    risk = RiskGuard(config, peak_equity=before.equity)
    orders = rebalance(strategy, bars, broker, risk, config,
                       max_position_weight=max_position_weight)
    after = broker.get_account()
    return {
        "mode": resolved,
        "strategy": type(strategy).__name__,
        "symbols": list(symbols),
        "account_before": {"equity": before.equity, "cash": before.cash},
        "account_after": {"equity": after.equity, "cash": after.cash},
        "orders": [{"symbol": o.symbol, "side": o.side, "notional": round(o.notional, 2)}
                   for o in orders],
        "risk": {"in_breach": bool(risk.in_breach(before.equity)),
                 "drawdown": float(risk.drawdown(before.equity))},
    }
```

Replace the existing `main()` function (and keep the `if __name__ == "__main__"` block) with:
```python
def run_cli(argv=None, *, adapter=None, env=None) -> dict:
    parser = argparse.ArgumentParser(prog="ohmystock.live")
    parser.add_argument("--mode", choices=["dry-run", "live"], default=None)
    parser.add_argument("--strategy", default="Momentum")
    parser.add_argument("--symbols", default="AAPL,MSFT,GOOGL,AMZN,META")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2024-01-01")
    parser.add_argument("--capital", type=float, default=5_000_000)
    args = parser.parse_args(argv)

    mode = resolve_mode(args.mode, env)
    if adapter is None:
        adapter = YFinanceAdapter(cache=ParquetCache(".cache"))
    config = Config(initial_capital=args.capital)
    strategy = build_strategy(args.strategy, {})
    result = live_execute(
        args.symbols.split(","), date.fromisoformat(args.start),
        date.fromisoformat(args.end), adapter, strategy, config, mode=mode, env=env)
    print(result)
    return result


def main() -> None:
    run_cli()


if __name__ == "__main__":
    main()
```

(If the old `main()` had a different body, delete it entirely and use the above. Do NOT touch `live_preview`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_live_toggle.py -q`
Then full suite: `uv run pytest -q`
Expected: PASS (전체). `live_preview` 관련 기존 테스트(test_live.py)도 그대로 통과.

- [ ] **Step 5: Commit**

```bash
git add ohmystock/live.py tests/test_live_toggle.py
git commit -m "feat: add live_execute (mode-aware) + scheduler.live CLI --mode toggle"
```

---

## Task 3: 스모크 + 머지

- [ ] **Step 1: 전체 테스트**

Run: `uv run pytest -q`
Expected: 전체 PASS.

- [ ] **Step 2: CLI 가드 스모크 (네트워크 불필요)**

```bash
# dry-run 기본 — 키 없어도 안전 (실주문 0). (실데이터 fetch는 네트워크 사용)
uv run python -m ohmystock.live --mode dry-run --symbols AAPL,MSFT --strategy Momentum --start 2024-01-01 --end 2024-06-30
# live + 키 없음 -> 큰 소리로 거부 (비-0 종료)
OHMYSTOCK_MODE= uv run python -m ohmystock.live --mode live --symbols AAPL,MSFT --start 2024-01-01 --end 2024-06-30 ; echo "exit=$?"
```
Expected: dry-run은 `{'mode': 'dry-run', ...}` 출력; live는 `ValueError: ... ALPACA_API_KEY ...`로 비-0 종료(exit≠0).

- [ ] **Step 3: 머지**

```bash
git checkout main && git merge --no-ff <feature-branch>
uv run pytest -q
git push origin main
```

---

## Self-Review

**Spec 커버리지:**
- §2 모듈(broker_select / live_execute / CLI) → Task 1,2 ✓
- §3 resolve_mode + build_broker 가드(live+키없음 거부, base_url) → Task 1 + 9 테스트 ✓
- §4 live_execute(dry-run 시뮬 / live 실주문, peak=현재자산) → Task 2 ✓
- §5 CLI(--mode, env, build_strategy) → Task 2 ✓
- §6 에러(잘못된 모드/키없음/Alpaca 오류 전파) → Task 1·2 테스트 ✓
- §7 테스트(resolve/build/live_execute/CLI, 오프라인 MockTransport) → 각 Task ✓
- §8 비범위(전체 루프·KIS·라이브 MDD 영속) — 미포함(정상). `live_preview` 보존 ✓

**플레이스홀더:** 완전한 코드(검증된 AlpacaBroker/PaperBroker/rebalance 시그니처).

**타입 일관성:**
- `resolve_mode(cli_mode, env) -> str`, `build_broker(mode, *, cash, env, client) -> Broker` — Task 1 ↔ Task 2 live_execute 호출 일치 ✓
- `live_execute(..., *, mode, env, broker, max_position_weight) -> dict(+mode)` — Task 2 정의 ↔ run_cli/테스트 일치 ✓
- AlpacaBroker `.api_key`/`.client.base_url` — Task 1 테스트가 검증, 실제 속성 존재 ✓

**검증된 사실:** AlpacaBroker는 `base_url` 기본 페이퍼·env 키 폴백; submit_order는 POST /v2/orders. live_execute는 PaperBroker일 때만 set_prices(Alpaca는 시장가 체결이라 불필요). `live_preview`/서버 `/api/live/preview`는 손대지 않아 기존 통과 유지.
