# broker_select 배선(alpaca/toss/kis + 실제-돈 게이트) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `build_broker`가 live 모드에서 alpaca/toss/kis를 선택하게 하고, 실제 돈이 걸린 구성은 명시적 동의 없이는 거부한다.

**Architecture:** `broker_select.py`에 `resolve_broker`(CLI>env>alpaca)와 브로커별 빌더(키 가드 + 실제-돈 동의 게이트)를 추가하고, `build_broker(mode, *, cash, env, client, broker_name)`가 live에서 분기한다. `live.py`의 `live_execute`/`run_cli`가 `broker_name`을 전달한다. 모든 테스트는 `httpx.MockTransport` client 주입으로 네트워크 없이 돈다.

**Tech Stack:** Python 3.11, httpx, pytest, uv.

## Global Constraints

- 실행: `uv run pytest <path> -q` (VIRTUAL_ENV 3.9.11 경고 무해).
- 선택 우선순위: CLI `--broker` > env `OHMYSTOCK_BROKER` > 기본 `"alpaca"`. 유효값 `("alpaca","toss","kis")`.
- 3단계 안전: ① dry-run=PaperBroker ② live+가짜돈(Alpaca 페이퍼·KIS 모의)=키만 ③ live+실제돈(TOSS 항상·Alpaca 라이브·KIS 실전)=키+`OHMYSTOCK_ALLOW_REAL_MONEY` 동의.
- 동의 값: `OHMYSTOCK_ALLOW_REAL_MONEY` 가 `"1"`/`"true"`/`"yes"`(대소문자 무시)면 허용.
- 실제-돈 판정(fail-safe): Alpaca `"paper" not in base_url.lower()` → 실제 돈. KIS `OHMYSTOCK_KIS_PAPER` 가 `"0"`/`"false"`/`"no"` → 실전(실제 돈). TOSS는 항상 실제 돈.
- 브로커 생성자: `AlpacaBroker(api_key, secret_key, base_url, client)`, `KISBroker(app_key, app_secret, account_no, *, paper, client)`, `TossBroker(client_id, client_secret, account_seq=None, *, client)`.
- 키 누락·동의 누락·잘못된 broker는 **네트워크 전** `ValueError`. dry-run은 키·동의·broker_name 무관. 각 태스크 끝 커밋(atinjin).

---

### Task 1: `resolve_broker`

**Files:**
- Modify: `ohmystock/broker_select.py` (`resolve_broker` 추가 + `_VALID_BROKERS` 상수)
- Test: `tests/test_broker_select.py` (테스트 추가)

**Interfaces:**
- Produces: `resolve_broker(cli_broker: str | None = None, env: dict | None = None) -> str` (`"alpaca"|"toss"|"kis"`).

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_broker_select.py` 끝에 추가 (상단 import에 `resolve_broker`가 없으면 `from ohmystock.broker_select import ... resolve_broker` 로 추가):
```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_broker_select.py -q`
Expected: FAIL (`ImportError: cannot import name 'resolve_broker'`).

- [ ] **Step 3: `resolve_broker` 구현**

`ohmystock/broker_select.py`의 `_VALID_MODES` 아래에 상수와 함수를 추가:
```python
_VALID_BROKERS = ("alpaca", "toss", "kis")


def resolve_broker(cli_broker: str | None = None, env: dict | None = None) -> str:
    """브로커 해석: CLI > env(OHMYSTOCK_BROKER) > 기본 'alpaca'. 잘못된 값 ValueError."""
    env = os.environ if env is None else env
    broker = cli_broker if cli_broker is not None else env.get("OHMYSTOCK_BROKER", "alpaca")
    if broker not in _VALID_BROKERS:
        raise ValueError(f"알 수 없는 브로커: {broker!r} (alpaca|toss|kis)")
    return broker
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_broker_select.py -q`
Expected: PASS (기존 + 신규 5개 그린).

- [ ] **Step 5: 커밋**

```bash
git add ohmystock/broker_select.py tests/test_broker_select.py
git commit -m "feat(broker-select): add resolve_broker (CLI>env>alpaca)"
```

---

### Task 2: `build_broker` 분기 + 실제-돈 동의 게이트

**Files:**
- Modify: `ohmystock/broker_select.py` (import 추가, `build_broker` 교체, 빌더/게이트 헬퍼 추가)
- Test: `tests/test_broker_select.py` (build_broker 테스트 추가 + 기존 `test_build_live_base_url_override` 갱신)

**Interfaces:**
- Consumes: Task 1의 `resolve_broker`, `_VALID_BROKERS`.
- Produces: `build_broker(mode, *, cash, env=None, client=None, broker_name=None)`; live에서 alpaca/kis/toss 분기. 실제 돈 구성은 `OHMYSTOCK_ALLOW_REAL_MONEY` 없으면 ValueError.

- [ ] **Step 1: 기존 테스트 갱신 + 신규 테스트**

`tests/test_broker_select.py`에서 기존 `test_build_live_base_url_override`를 아래로 **교체**(라이브 URL은 이제 동의 필요):
```python
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
```
파일 끝에 신규 테스트 추가(상단 import에 `KISBroker`/`TossBroker`가 없으면 추가):
```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_broker_select.py -q`
Expected: FAIL (`build_broker`가 `broker_name`/`OHMYSTOCK_KIS_PAPER`/동의 게이트를 모름; toss/kis 미분기).

- [ ] **Step 3: `build_broker` 교체 + 헬퍼 추가**

`ohmystock/broker_select.py` 상단 import에 추가:
```python
from ohmystock.core.broker.kis import KISBroker
from ohmystock.core.broker.toss import TossBroker
```
`_DEFAULT_PAPER_URL` 아래에 상수 추가:
```python
_TRUTHY = ("1", "true", "yes")
```
기존 `build_broker` 함수 전체를 아래(헬퍼 포함)로 **교체**:
```python
def _require_real_money_ack(env, label):
    val = (env.get("OHMYSTOCK_ALLOW_REAL_MONEY") or "").strip().lower()
    if val not in _TRUTHY:
        raise ValueError(
            f"{label}는 실제 돈이 걸린 주문입니다. OHMYSTOCK_ALLOW_REAL_MONEY=1 을 설정해 "
            f"명시적으로 동의하거나, 가짜 돈(페이퍼/모의) 구성 또는 dry-run으로 실행하세요."
        )


def _build_alpaca(env, client):
    key = env.get("ALPACA_API_KEY")
    secret = env.get("ALPACA_SECRET_KEY")
    if not key or not secret:
        raise ValueError(
            "alpaca live 모드인데 ALPACA_API_KEY/ALPACA_SECRET_KEY가 없습니다.")
    base_url = env.get("ALPACA_BASE_URL", _DEFAULT_PAPER_URL)
    if "paper" not in base_url.lower():
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
```

- [ ] **Step 4: 통과 확인 + 전체 스위트**

Run: `uv run pytest tests/test_broker_select.py -q`
Expected: PASS (기존 alpaca live 테스트 + 신규 kis/toss/게이트 테스트 그린).
Run: `uv run pytest -q`
Expected: PASS (전 프로젝트 그린).

- [ ] **Step 5: 커밋**

```bash
git add ohmystock/broker_select.py tests/test_broker_select.py
git commit -m "feat(broker-select): build_broker dispatch alpaca/kis/toss + real-money ack gate"
```

---

### Task 3: live.py 배선 (`--broker` + `broker_name` 전달)

**Files:**
- Modify: `ohmystock/live.py` (`live_execute` 시그니처 + `build_broker` 호출, `run_cli` `--broker` 플래그)
- Test: `tests/test_live_toggle.py` (테스트 추가)

**Interfaces:**
- Consumes: Task 2의 `build_broker(..., broker_name=...)`.
- Produces: `live_execute(..., *, mode="dry-run", env=None, broker=None, broker_name=None, max_position_weight=None)`; `run_cli`의 `--broker {alpaca,toss,kis}`.

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_live_toggle.py` 끝에 추가:
```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_live_toggle.py -q`
Expected: FAIL (`live_execute`가 `broker_name` 인자를 모름 / `run_cli`에 `--broker` 없음).

- [ ] **Step 3: live.py 수정**

`ohmystock/live.py`의 `live_execute` 시그니처와 `build_broker` 호출을 수정:
```python
def live_execute(symbols, start, end, adapter, strategy, config, *,
                 mode="dry-run", env=None, broker=None, broker_name=None,
                 max_position_weight=None) -> dict:
    """모드 인지 실행. dry-run=PaperBroker 시뮬, live=선택 브로커 실주문."""
    resolved = resolve_mode(mode, env)
    bars = adapter.get_daily_bars(symbols, start, end)
    if broker is None:
        broker = build_broker(resolved, cash=config.initial_capital, env=env,
                              broker_name=broker_name)
```
(그 아래 모순 가드·set_prices·rebalance·반환 dict는 그대로 둔다.)

`run_cli`에 `--broker` 인자를 추가하고 `live_execute`에 전달:
```python
    parser.add_argument("--mode", choices=["dry-run", "live"], default=None)
    parser.add_argument("--broker", choices=["alpaca", "toss", "kis"], default=None)
```
그리고 `live_execute(...)` 호출에 `broker_name=args.broker` 를 추가:
```python
    result = live_execute(
        args.symbols.split(","), date.fromisoformat(args.start),
        date.fromisoformat(args.end), adapter, strategy, config,
        mode=mode, env=env, broker_name=args.broker)
```

- [ ] **Step 4: 통과 확인 + 전체 스위트**

Run: `uv run pytest tests/test_live_toggle.py -q`
Expected: PASS.
Run: `uv run pytest -q`
Expected: PASS (전 프로젝트 그린).

- [ ] **Step 5: 커밋**

```bash
git add ohmystock/live.py tests/test_live_toggle.py
git commit -m "feat(live): thread --broker/broker_name through live_execute + run_cli"
```

---

## 완료 후

- 적대적 안전 리뷰(실주문 경로 — 실제 돈이 동의 없이 새어나갈 경로 점검) 후 main 머지·푸시.
- ROADMAP에 브로커 선택 배선 항목 표기.
- (선택) README에 `--broker`/`OHMYSTOCK_BROKER`/`OHMYSTOCK_ALLOW_REAL_MONEY` 사용법 추가.
