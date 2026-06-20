# broker_select에 TOSS·KIS 배선 (실제-돈 동의 게이트) 설계

**작성일:** 2026-06-20
**상태:** 설계 확정
**로드맵:** 실계좌 스케줄링 (브로커 선택 배선)
**선행:** `broker_select`(dry-run/live 토글), `AlpacaBroker`/`KISBroker`/`TossBroker` 완료.

---

## 1. 목표

`build_broker`가 live 모드에서 **alpaca/toss/kis 중 선택**하도록 확장한다. 핵심은 **실제 돈이 걸린 브로커가 실수로 발사되지 않도록** 3단계 안전(특히 샌드박스 없는 TOSS)을 두는 것. 스케줄러-라이브 루프 연결은 비범위.

확정된 결정:
- 범위(Q1=A): `build_broker` 브로커 선택 + `resolve_broker` + `--broker` CLI/env + 브로커별 키 가드 + 오프라인 테스트. 스케줄러 연결은 비범위.
- 선택 출처(Q2=A): **CLI `--broker` > env `OHMYSTOCK_BROKER` > 기본 `alpaca`**. 기본 alpaca = 페이퍼 엔드포인트(가짜 돈)라 가장 안전.
- 실제-돈 게이트(Q3=A): **3단계 안전**. 실제 돈이 걸린 구성은 키 + `OHMYSTOCK_ALLOW_REAL_MONEY` 명시 동의 없으면 거부.

재사용/수정: `ohmystock/broker_select.py`(확장), `ohmystock/live.py`(`live_execute`/`run_cli`). 브로커: `AlpacaBroker(api_key, secret_key, base_url, client)`, `KISBroker(app_key, app_secret, account_no, *, paper, client, ...)`, `TossBroker(client_id, client_secret, account_seq=None, *, currency, client, ...)`.

---

## 2. 3단계 안전 + 실제-돈 분류

| 단계 | 구성 | 필요 조건 |
|------|------|-----------|
| ① dry-run | `PaperBroker`(증권사 접속 0) | 없음 (기본) |
| ② live + **가짜 돈** | Alpaca 페이퍼 엔드포인트 · KIS 모의투자(paper=True) | 해당 브로커 **키만** |
| ③ live + **실제 돈** | **TOSS(항상)** · Alpaca 라이브(base_url에 "paper" 없음) · KIS 실전(`OHMYSTOCK_KIS_PAPER=0`) | 키 **+ `OHMYSTOCK_ALLOW_REAL_MONEY` 동의** |

- 동의 값: `OHMYSTOCK_ALLOW_REAL_MONEY` 가 `"1"`/`"true"`/`"yes"`(대소문자 무시) 중 하나면 허용, 아니면 거부.
- 실제-돈 판정은 **fail-safe**: Alpaca base_url에 "paper"가 없으면 실제 돈으로 간주(커스텀 URL도 동의 요구). dry-run에서는 broker_name·동의 무관(PaperBroker).

---

## 3. `resolve_broker` (broker_select.py)

```python
_VALID_BROKERS = ("alpaca", "toss", "kis")

def resolve_broker(cli_broker: str | None = None, env: dict | None = None) -> str:
    """브로커 해석: CLI > env(OHMYSTOCK_BROKER) > 기본 'alpaca'. 잘못된 값 ValueError."""
```

- `mode`와 동일 우선순위. 반환은 `"alpaca"|"toss"|"kis"`.

## 4. `build_broker` 확장 (broker_select.py)

```python
def build_broker(mode, *, cash, env=None, client=None, broker_name=None):
    # dry-run → PaperBroker(cash)  (broker_name 무시)
    # live → resolve_broker(broker_name, env) 로 분기
```

분기별(모두 live에서, 키 누락은 네트워크 전 ValueError):

- **alpaca**: `ALPACA_API_KEY`/`ALPACA_SECRET_KEY` 필요. `base_url = ALPACA_BASE_URL` 또는 페이퍼 기본 `https://paper-api.alpaca.markets`. `"paper" not in base_url.lower()` → 실제 돈 → 동의 게이트. → `AlpacaBroker(api_key, secret_key, base_url, client)`.
- **kis**: `KIS_APP_KEY`/`KIS_APP_SECRET`/`KIS_ACCOUNT_NO` 필요. `paper = env.get("OHMYSTOCK_KIS_PAPER", "1") not in ("0","false","no")`(기본 모의). `not paper` → 실제 돈 → 동의 게이트. → `KISBroker(app_key, app_secret, account_no, paper=paper, client=client)`.
- **toss**: `TOSS_CLIENT_ID`/`TOSS_CLIENT_SECRET` 필요. **항상 실제 돈** → 동의 게이트. `account_seq = env.get("TOSS_ACCOUNT_SEQ")`(없으면 None=자동). → `TossBroker(client_id, client_secret, account_seq=account_seq, client=client)`.

동의 게이트 헬퍼:
```python
def _require_real_money_ack(env, broker_label):
    val = (env.get("OHMYSTOCK_ALLOW_REAL_MONEY") or "").strip().lower()
    if val not in ("1", "true", "yes"):
        raise ValueError(
            f"{broker_label}는 실제 돈이 걸린 주문입니다. "
            f"OHMYSTOCK_ALLOW_REAL_MONEY=1 을 설정해 명시적으로 동의하거나, "
            f"가짜 돈(페이퍼/모의) 구성 또는 dry-run으로 실행하세요."
        )
```

## 5. live.py 배선

- `live_execute(..., *, mode="dry-run", env=None, broker=None, broker_name=None, max_position_weight=None)`: `broker is None`일 때 `build_broker(resolved, cash=..., env=env, broker_name=broker_name)`. 기존 모순 가드(live⟺non-Paper)·`set_prices`(PaperBroker만)는 유지.
- `run_cli`: `--broker {alpaca,toss,kis}`(default None) 추가 → `live_execute(..., broker_name=args.broker)`. dry-run 기본 유지.

## 6. 에러 처리

- 잘못된 `broker_name`(또는 OHMYSTOCK_BROKER) → `ValueError`(alpaca|toss|kis 안내).
- 브로커별 키 누락 → `ValueError`(어떤 env 키인지 명시).
- 실제 돈인데 동의 없음 → `ValueError`(OHMYSTOCK_ALLOW_REAL_MONEY 안내).
- 모두 브로커 생성/네트워크 **전에** 거부. dry-run은 키·동의·broker_name 무관.

## 7. 테스트 (오프라인·결정적)

- `resolve_broker`: CLI "toss" → toss / env OHMYSTOCK_BROKER=kis → kis / 무지정 → alpaca / 잘못된 값 → ValueError / CLI가 env 우선.
- `build_broker` dry-run: broker_name 무엇이든(또는 toss) → PaperBroker, 동의·키 불필요.
- `build_broker` live alpaca: 키(env)+주입 client → AlpacaBroker(페이퍼 기본, 동의 불필요) / 키 없음 → ValueError / `ALPACA_BASE_URL`=live(paper 없음) + 동의 없음 → ValueError / +동의 → AlpacaBroker.
- `build_broker` live kis: 키 3종 → KISBroker(paper 기본, 동의 불필요) / 키 없음 → ValueError / `OHMYSTOCK_KIS_PAPER=0` + 동의 없음 → ValueError / +동의 → KISBroker(paper=False).
- `build_broker` live toss: 키 + **동의 없음 → ValueError** / 키 + 동의 → TossBroker / 키 없음 → ValueError.
- `live_execute`/`run_cli`: `--broker` 전달 확인(주입 broker로 네트워크 없이), 기본 dry-run 유지, live+키없음/동의없음 → 비-0 종료.

## 8. 비범위

- 스케줄러-라이브 루프 연결(자동 자동매매), 브로커별 심볼·통화 적합성 검증(KIS=KR 6자리, TOSS=usd 기본, Alpaca=US), 라이브 MDD 고점 영속, 체결 reconciliation, 주문 타입 정밀화.
- `build_broker`는 재사용 가능하게 두어 향후 스케줄러-라이브 연결 시 활용.
