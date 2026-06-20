# 실 계좌 현황 패널 (읽기 전용) 설계

**작성일:** 2026-06-20
**상태:** 설계 확정
**선행:** `KISBroker`/`TossBroker` 실 API 검증 완료, FastAPI 대시보드(server/app.py + web/).

---

## 1. 목표

대시보드에 **실 계좌(KIS 모의·TOSS) 현황을 읽기 전용으로** 표시하는 패널을 추가한다. CLI로 검증한 `get_account`/`get_positions` 데이터를 브라우저에서 안전하게 본다. **주문은 추가하지 않는다**(실주문은 CLI 이중 게이트 유지).

확정된 결정:
- 브로커(Q1=A): **KIS + TOSS**. Alpaca는 비범위(키 없음).
- 갱신(Q2=B+A): **자동 폴링(기본 30초) + 수동 새로고침 버튼**. 선택된 브로커만 조회.
- 읽기 전용: 주문 엔드포인트 없음. 서버가 브로커 인스턴스를 캐시해 토큰을 재사용(KIS 분당 발급제한 회피); KIS 초당 제한(EGW00201)은 어댑터 `_send` 재시도가 처리.

재사용/수정: `server/app.py`(엔드포인트 추가), `web/src/api.ts`(클라이언트), 신규 `web/src/components/BrokerAccountPanel.tsx`, `web/src/App.tsx`(패널 배치). 브로커: `KISBroker(paper=...)`, `TossBroker()`.

---

## 2. 백엔드 엔드포인트

`GET /api/broker/account?broker={kis|toss}` → 200:
```json
{
  "broker": "kis",
  "mode": "paper",
  "equity": 10000000.0,
  "cash": 10000000.0,
  "positions": [{"symbol": "005930", "value": 354000.0}]
}
```
- `broker` ∈ `{"kis","toss"}`. 그 외 → `HTTPException(400, "broker는 kis|toss")`.
- `mode`: KIS는 `"paper"`/`"live"`(broker.paper 기준), TOSS는 `"live"`.
- 동작: `b = _cached_broker(broker)` → `b.get_account()` + `b.get_positions()`. positions는 `{symbol: value}`를 `[{symbol, value}]` 리스트로.
- 예외(키 없음·IP 미허용·EGW02007 등) → `HTTPException(502, str(예외))`(패널에 표시, 서버 크래시 X).
- **읽기 전용**: 이 엔드포인트는 get_account/get_positions만 호출. 주문/변경 없음.

## 3. 브로커 인스턴스 캐시 + 읽기 전용 팩토리

- `app.state.brokers: dict[str, Broker]` — 브로커명별 인스턴스 캐시. 폴링마다 새 인스턴스를 만들지 않아 토큰(KIS 24h)을 재사용한다.
- `app.state.broker_factory(name) -> Broker` — 미캐시 시 생성. 기본값 `_read_only_broker`. **테스트는 이걸 가짜로 주입**.
- `_read_only_broker(name, env=os.environ)`:
  - `"kis"`: `KISBroker(paper=env.get("OHMYSTOCK_KIS_PAPER","1") not in ("0","false","no"))` (키는 KISBroker가 env 폴백). 키 없으면 호출 시 KIS가 거부 → 502.
  - `"toss"`: `TossBroker()` (키는 env 폴백).
  - **build_broker(주문·실제-돈 게이트)와 분리** — 읽기는 게이트 불필요(돈 안 움직임).
- 서버 시작 시 `.env` 자동 로드: `create_app`에서 guarded `load_dotenv()`(python-dotenv 있으면, .env 있으면). env 미설정 환경엔 무영향.

## 4. 프론트엔드 (`BrokerAccountPanel.tsx`)

- 상단: 제목 "실 계좌 현황" + **"읽기 전용 · 실 계좌"** 배지 + **브로커 선택**(KIS/TOSS 토글) + **새로고침** 버튼.
- 본문: `equity`·`cash` 카드 + 모드 라벨(모의/실전) + **보유 테이블**(종목 · 평가금액). 보유 0건이면 "보유 종목 없음".
  - **통화 포맷은 브로커별**: KIS → KRW(`₩`/원), TOSS → USD(`$`). 카드·테이블·금액 모두 동일 통화로 표시.
- 상태: 로딩 / 에러(빨강 메시지) / 데이터. 에러 시에도 패널 유지.
- 갱신: 선택된 브로커를 **마운트 시 + 30초 간격 자동 + 새로고침 클릭 시** 조회. 브로커 전환 시 즉시 조회하고 타이머 리셋. 언마운트 시 타이머 정리.
- `App.tsx`의 `app-main` 하단(다른 패널들과 함께)에 배치.
- 스타일: 기존 `card`/`orders-table` 클래스 재사용.

## 5. api.ts 클라이언트

```ts
export interface BrokerAccount {
  broker: string
  mode: string
  equity: number
  cash: number
  positions: { symbol: string; value: number }[]
}
export async function getBrokerAccount(broker: 'kis' | 'toss'): Promise<BrokerAccount>
```
- `fetch('/api/broker/account?broker=' + broker)`, 비-2xx → 기존 `parseError`(detail).

## 6. 에러 처리

- 잘못된 broker → 400. 브로커 조회 실패(키/네트워크/IP/KIS rt_cd) → 502 + 메시지. 프론트는 메시지를 패널에 표시(자동 폴링도 계속, 다음 주기에 복구 시 정상 표시).
- 실 잔고는 서버에서 로그/영속하지 않는다.

## 7. 테스트

- 백엔드(`tests/test_server.py` 또는 신규): `create_app`에 가짜 `broker_factory` 주입.
  - 정상: 가짜 브로커가 `Account(equity, cash)` + positions 반환 → 엔드포인트 JSON(broker/mode/equity/cash/positions) 검증.
  - 잘못된 broker(`?broker=ibkr`) → 400.
  - 브로커가 예외 → 502 + detail.
  - 캐시: 두 번 호출 시 `broker_factory`가 1회만 불림(인스턴스 재사용).
- 프론트: 기존 패널처럼 FE 자동 테스트 없음(레포 관행). `npm run build` 타입체크 통과로 확인.

## 8. 비범위

- 실주문(계속 CLI 이중 게이트), Alpaca(키 없음), 다계좌, 과거 잔고 추이 차트, 통화 환산 합산(TOSS는 usd 슬리브), 인증/접근제어(로컬 대시보드 전용).
