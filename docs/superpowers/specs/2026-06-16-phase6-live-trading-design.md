# OhMyStock 6단계 — 실거래(페이퍼) + 리스크 가드 + 어댑터 설계

**작성일:** 2026-06-16
**선행:** 1~5단계 완료(main). 20개 검증 + 웹 대시보드.

## 원칙 (안전 최우선)

- 실주문 경로는 **주입식 클라이언트**로만 외부와 통신. API 키가 없으면 실주문 불가.
- **PaperBroker(인메모리 시뮬)** 로 리밸런싱·리스크 가드 전 구간을 네트워크 없이 테스트.
- 기본 모드는 **드라이런/페이퍼**. 실계좌 주문은 키를 명시적으로 넣어야만 가능.
- 리스크 가드가 MDD 한도(-20%)를 넘으면 **신규 진입 차단**.

## 코어 브로커 계층 (`core/broker/`)

### base.py — 인터페이스/DTO
- `@dataclass Account(equity: float, cash: float)`
- `@dataclass Order(symbol: str, side: str["buy"|"sell"], notional: float)` (소수점 금액 주문)
- `class Broker(Protocol)`: `get_account()->Account`, `get_positions()->dict[str,float]`(심볼→시장가치$), `submit_order(order)->None`

### paper.py — PaperBroker (시뮬)
- 현금·보유주식·최신가 보유. `set_prices(dict)`, `get_account`, `get_positions`(시장가치), `submit_order`(notional/price 만큼 체결, 현금·주식 갱신). 매도는 보유 한도 내.

### risk.py — RiskGuard
- `Config`와 peak_equity 추적. `update(equity)`로 고점 갱신. `in_drawdown_breach(equity)->bool`(고점 대비 낙폭>mdd_limit). `filter_orders(orders, equity)->orders`: 낙폭 한도 위반 시 **매수(신규/추가) 차단, 매도는 허용**. 단일 주문 상한(max_position_weight)도 적용.

### rebalance.py — 일일 리밸런서
- `rebalance(strategy, bars, broker, risk_guard, config) -> list[Order]`:
  1. `strategy.generate_signals(bars)` 마지막 행 = 오늘 목표비중.
  2. `account = broker.get_account()`; equity 확보. risk_guard.update(equity).
  3. 심볼별 목표금액 = 비중×equity. 현재가치 = broker.get_positions().
  4. 차이 → Order(buy/sell, |diff|). risk_guard.filter_orders 적용.
  5. 각 주문 broker.submit_order. 제출된 주문 리스트 반환.

## 어댑터 (주입식 클라이언트, REST)

### alpaca.py — AlpacaBroker (미국, 페이퍼/실계좌)
- `AlpacaBroker(key, secret, base_url="https://paper-api.alpaca.markets", client=httpx.Client)`. 키는 env(ALPACA_API_KEY/ALPACA_SECRET_KEY)에서도 로드. `get_account`/`get_positions`/`submit_order`를 Alpaca REST로 구현. 테스트는 주입한 mock transport로 네트워크 없이.

### kis.py — KISBroker (한국, 확장)
- `KISBroker(app_key, app_secret, account, base_url, client)`. 동일 Broker 인터페이스. 한국투자증권 REST 형태(주문/잔고/계좌). 주입식 클라이언트로 테스트. 한국 확장 지점.

## 통합

- CLI `python -m ohmystock.live`: PaperBroker로 오늘자 리밸런스 **드라이런**(실주문 없음), 생성된 주문·계좌 출력.
- FastAPI `POST /api/live/preview`: 전략·심볼로 오늘 목표 주문을 PaperBroker로 계산해 반환(실거래 아님).
- 대시보드에 "실거래 미리보기" 패널(선택): 오늘 주문 목록·리스크 상태 표시.

## 비범위

실시간 스트리밍·체결 콜백·세금 리포팅은 이후. 실계좌 자동매매 스케줄링은 키 투입 후 cron으로.
