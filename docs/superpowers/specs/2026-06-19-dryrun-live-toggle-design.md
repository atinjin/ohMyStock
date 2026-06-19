# 드라이런 ↔ 실계좌 모드 토글 (API 키 가드) 설계

**작성일:** 2026-06-19
**상태:** 설계 확정
**로드맵:** 실계좌 스케줄링 § "드라이런 ↔ 실계좌 모드 토글(API 키 가드)"

---

## 1. 목표

"진짜 주문을 낼지(실계좌) vs 시뮬만 할지(드라이런)"를 **안전하게 토글**한다. 핵심은 **실주문이 실수로 나가지 않도록 모드+API 키 가드**로 막는 것. 완전한 라이브 트레이딩 루프·KIS 실연동은 비범위(별도 항목).

확정된 결정:
- 범위: **안전 토글 + 브로커 선택만**. `build_broker(mode)`로 드라이런→PaperBroker, 실계좌→AlpacaBroker. 기존 `rebalance` 경로 재사용.
- 가드: live 모드인데 키가 없으면 **`ValueError`로 즉시 거부(폴백 금지)**. 기본 모드는 항상 dry-run.
- 모드 출처: **CLI 플래그 > 환경변수 `OHMYSTOCK_MODE` > 기본 "dry-run"**.
- 3단계 안전: ① dry-run = PaperBroker(증권사 접속 0) ② live + 키 = AlpacaBroker가 **Alpaca 페이퍼 엔드포인트(모의머니)** ③ 실제 돈 = `ALPACA_BASE_URL`을 라이브로 **명시적** 변경해야만.

재사용: `core/broker/paper.py::PaperBroker(cash)`, `core/broker/alpaca.py::AlpacaBroker(api_key=None, secret_key=None, base_url="https://paper-api.alpaca.markets", client=None)`(env `ALPACA_API_KEY`/`ALPACA_SECRET_KEY` 폴백, get_account/get_positions/submit_order), `core/broker/rebalance.py::rebalance`, `core/broker/risk.py::RiskGuard`, `report.py::build_strategy`.

---

## 2. 모듈 구조

```
ohmystock/broker_select.py     # 안전 토글 핵심 (모드 해석 + 브로커 선택 + 가드)
  resolve_mode(cli_mode, env=None) -> str            # "dry-run" | "live"
  build_broker(mode, *, cash, env=None, client=None) -> Broker
ohmystock/live.py              # live_execute(...) (모드 인지) + CLI --mode
```

`live_preview`(기존 대시보드 미리보기, dry-run 전용)는 **변경하지 않는다**(서버 `/api/live/preview`·대시보드 패널·test_live 보존). `live_execute`를 새로 추가한다.

---

## 3. 모드 해석 & 가드 (`broker_select.py`)

```python
import os
from ohmystock.core.broker.paper import PaperBroker
from ohmystock.core.broker.alpaca import AlpacaBroker

_VALID_MODES = ("dry-run", "live")
_DEFAULT_PAPER_URL = "https://paper-api.alpaca.markets"


def resolve_mode(cli_mode: str | None = None, env: dict | None = None) -> str:
    env = os.environ if env is None else env
    mode = cli_mode if cli_mode is not None else env.get("OHMYSTOCK_MODE", "dry-run")
    if mode not in _VALID_MODES:
        raise ValueError(f"알 수 없는 모드: {mode!r} (dry-run|live)")
    return mode


def build_broker(mode: str, *, cash: float, env: dict | None = None, client=None):
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

- CLI > env > 기본. 잘못된 값은 에러.
- live+키없음 → 거부(조용한 폴백 없음). base_url 기본은 페이퍼.

---

## 4. 실행 (`live.py::live_execute`)

```python
def live_execute(symbols, start, end, adapter, strategy, config, *,
                 mode="dry-run", env=None, broker=None,
                 max_position_weight=None) -> dict:
    resolved = resolve_mode(mode, env)
    bars = adapter.get_daily_bars(symbols, start, end)
    if broker is None:
        broker = build_broker(resolved, cash=config.initial_capital, env=env)
    if isinstance(broker, PaperBroker):               # dry-run: 가격 시드 필요
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

- **dry-run**: PaperBroker(자본+최신 종가) → `rebalance`(인메모리, 실제 제출 없음). 주문은 계산 결과.
- **live**: AlpacaBroker → `get_account`/`get_positions`로 **실계좌 상태**, `rebalance`가 **실주문 제출**. 가격 시드 불필요(Alpaca가 시장가 체결).
- `RiskGuard` peak = 현재 자산(라이브 고점 영속은 향후 — 명시된 한계: 단일 forward 실행에선 MDD 차단이 약함).
- `broker`/`env` 주입 → 네트워크 없이 테스트(주입 mock AlpacaBroker).

---

## 5. CLI (`live.py`)

기존 `main`/preview를 모드 인지 `run_cli`로 교체:
- `python -m ohmystock.live [--mode dry-run|live] [--strategy NAME] [--symbols A,B,C] [--start D] [--end D] [--capital N]`
- `mode = resolve_mode(args.mode, env)` (CLI None이면 env→기본 dry-run). 전략은 `build_strategy(args.strategy, {})`.
- `live_execute(...)` 실행 후 결과 dict 한 줄 출력. live+키없음 → `ValueError`로 비-0 종료.
- 테스트 위해 `run_cli(argv, *, adapter=None, env=None)` 주입 가능.

---

## 6. 에러 처리

- `resolve_mode`: 잘못된 모드 값 → `ValueError`.
- `build_broker` live+키없음 → `ValueError`(큰 소리로 거부).
- `live_execute` live: Alpaca 응답 오류는 `AlpacaBroker`가 `raise_for_status`로 전파(부분 체결 방지). CLI는 비-0 종료.

---

## 7. 테스트 (오프라인·결정적)

- `resolve_mode`: cli "live" → live / cli None+env OHMYSTOCK_MODE=live → live / 무지정 → dry-run / 잘못된 값 → ValueError / CLI가 env 무시(우선).
- `build_broker`: dry-run → PaperBroker / live+키(env) → AlpacaBroker(주입 client) / **live+키없음(env={}) → ValueError** / ALPACA_BASE_URL 적용 확인.
- `live_execute`:
  - dry-run(FakeAdapter): orders 계산, mode="dry-run", account 반환(기존 미리보기와 동등).
  - live: 주입한 AlpacaBroker(httpx.MockTransport — account/positions 응답 + 주문 캡처) → `rebalance`가 주문 제출(POST /v2/orders 호출됨), mode="live".
- CLI `run_cli`: `--mode` 미지정→dry-run / `--mode live` + env 키없음 → ValueError / 주입 adapter·env로 출력 확인.

---

## 8. 비범위

- 완전한 라이브 트레이딩 루프(스케줄러→실계좌 연결), KIS 실연동, 라이브 MDD 고점 영속, 체결 reconciliation, 주문 타입/소수점 정밀화, 알림.
- `build_broker`는 재사용 가능하게 두어, 향후 스케줄러-라이브 연결 시 그대로 활용.
