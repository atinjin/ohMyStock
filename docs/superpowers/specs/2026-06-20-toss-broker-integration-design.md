# 토스증권(TOSS Invest) Open API 어댑터 설계

**작성일:** 2026-06-20
**상태:** 설계 확정
**로드맵:** 실계좌 스케줄링 (KIS보다 우선)
**참고:** [TOSS Invest Open API 문서](https://developers.tossinvest.com/docs) / OpenAPI 정본 `https://openapi.tossinvest.com/openapi-docs/latest/openapi.json` 으로 엔드포인트·필드 검증함.

---

## 1. 목표

토스증권 Open API를 `Broker` 프로토콜로 구현(`TossBroker`)하고 **오프라인으로 정확히 검증**한다. 실제 계좌 end-to-end 스모크는 자격증명을 가진 사용자가 **제공된 스크립트**로 실행한다.

확정된 결정:
- 범위(Q1=A): `TossBroker`(get_account/get_positions/submit_order) + OAuth 토큰 관리 + **오프라인 MockTransport 테스트** + 사용자용 **실 스모크 스크립트**. broker_select/live 모드 배선은 비범위.
- **TOSS는 샌드박스(모의투자)가 없다 — 모든 주문이 실거래.** 따라서 TOSS는 **실(live) 브로커**로 취급하고, 에이전트는 절대 실주문을 내지 않으며(오프라인 테스트만), 실 스모크는 사용자가 명시적으로 실행한다.
- 수량(Q2=A): 주문 시 `/api/v1/prices`로 `lastPrice` 조회 → `quantity = floor(notional / lastPrice)`, `orderType="MARKET"`. 전 시장·전 시간대 일관. 1주 미만이면 스킵. `clientOrderId`(멱등키)로 중복 주문 방지.
- 통화: 우리 바스켓은 US 주식 → 기본 `currency="usd"`(Price의 `usd` 필드, buying-power USD). `currency` 파라미터로 KR(`krw`) 분기 가능.

재사용/신규: 신규 `ohmystock/core/broker/toss.py::TossBroker`, `core/broker/base.py::Account/Order`(재사용). 신규 `tests/test_toss.py`, `scripts/toss_smoke.py`. env `TOSS_CLIENT_ID`/`TOSS_CLIENT_SECRET`/(선택)`TOSS_ACCOUNT_SEQ`.

---

## 2. 검증된 TOSS 사양 (구현 기준)

| 항목 | 값 |
|------|-----|
| base URL | `https://openapi.tossinvest.com` (**샌드박스 없음 — 실거래**) |
| 토큰 | `POST /oauth2/token` `Content-Type: application/x-www-form-urlencoded`, body `grant_type=client_credentials&client_id=…&client_secret=…` → `access_token`, `token_type`, `expires_in`(초). 클라이언트당 유효 토큰 1개(재발급 시 이전 무효), refresh 토큰 없음 |
| 공통 헤더 | `Authorization: Bearer {access_token}`. 계좌·자산·주문 호출엔 추가로 `X-Tossinvest-Account: {accountSeq}` |
| 응답 envelope | OAuth 외 응답은 공통 envelope `{ "result": … }` 로 감싸짐 → `resp.json()["result"]` |
| 계좌 | `GET /api/v1/accounts` → `result[]`, 각 `accountSeq`(계좌식별자, X-Tossinvest-Account에 사용), `accountType`(현재 `BROKERAGE`) |
| 보유 | `GET /api/v1/holdings` (헤더 X-Tossinvest-Account) → `result.marketValue.amount`(Price `{krw,usd}`, 전체 평가액), `result.items[]`: `symbol`, `name`, `currency`, `quantity`, `lastPrice`, `marketValue`(MarketValue: 평면 `purchaseAmount`/`amount`/`amountAfterCost`) |
| 매수여력 | `GET /api/v1/buying-power?currency=USD` (헤더 X-Tossinvest-Account) → `result.cashBuyingPower`(평면 BigDecimal, 해당 통화 현금), `result.currency` |
| 시세 | `GET /api/v1/prices?symbols=AAPL,MSFT` (최대 200, 콤마구분) → `result[]`: `symbol`, `lastPrice`(현재가), `timestamp`(null 가능), `currency` |
| 주문 | `POST /api/v1/orders` (헤더 X-Tossinvest-Account) body `{symbol, side:"BUY"|"SELL", orderType:"MARKET", quantity:<int>, clientOrderId, timeInForce:"DAY"}` → `result.orderId` |

> 주: buying-power의 `currency` 쿼리 파라미터명은 실 스모크에서 최종 검증한다(샌드박스가 없어 요청 형태 확인은 사용자 실행으로 보장).

---

## 3. TossBroker 구조

```python
class TossBroker:
    def __init__(self, client_id=None, client_secret=None, account_seq=None, *,
                 currency="usd", base_url="https://openapi.tossinvest.com",
                 client=None, access_token=None, token_expires_at=None,
                 client_order_id_fn=None): ...
    # 내부: _ensure_token(), _resolve_account_seq(), _acct_headers(),
    #       _last_price(symbol), _result(resp)
    def issue_token(self) -> str
    def get_account(self) -> Account
    def get_positions(self) -> dict[str, float]
    def submit_order(self, order: Order) -> None
```

- `client_id`/`client_secret` 미지정 시 env `TOSS_CLIENT_ID`/`TOSS_CLIENT_SECRET` 폴백.
- `account_seq` 미지정 시 env `TOSS_ACCOUNT_SEQ`, 그래도 없으면 `GET /accounts` 첫 `BROKERAGE`의 `accountSeq`로 해석(캐시).
- `currency`(기본 `"usd"`)가 Price의 `usd`/`krw` 선택 + buying-power 쿼리(`USD`/`KRW`).
- `client` 주입 시 그 client 사용(테스트). 미주입 시 `base_url`로 httpx.Client 생성.
- `client_order_id_fn` 주입 가능(테스트 결정성). 미지정 시 uuid4 hex.

---

## 4. 토큰 라이프사이클 (`_ensure_token`)

- `access_token` + `token_expires_at`(datetime) 캐시. 모든 API 호출 전 `_ensure_token()`:
  - 토큰 없거나 만료(또는 임박: now ≥ expires - 60s)면 `issue_token()`.
- `issue_token()`: `POST /oauth2/token`(form) → `access_token` 저장, `token_expires_at = now + expires_in초`.
- 주입된 `access_token`이 있고 만료시각이 미래면 재사용.

## 5. 계좌/포지션 조회

- `get_account()`:
  1. `seq = _resolve_account_seq()`.
  2. `holdings = GET /holdings` → 포지션 평가액 `pos = result.marketValue.amount[currency]`(usd/krw, 없으면 0).
  3. `cash = GET /buying-power?currency=CUR` → `result.cashBuyingPower`.
  4. `Account(equity=pos + cash, cash=cash)`.
- `get_positions()`: `holdings.result.items[]` 중 `quantity > 0` 이고 통화 일치 → `{symbol: marketValue.amount}`.

## 6. 주문 흐름 (`submit_order`)

1. `_ensure_token()`, `seq = _resolve_account_seq()`.
2. `price = _last_price(order.symbol)` (`GET /prices?symbols=SYM` → 해당 symbol의 `lastPrice`).
3. `qty = floor(order.notional / price)`. `qty < 1`이면 **스킵**(무동작, 예외 아님).
4. `body = {symbol, side: "BUY" if order.side=="buy" else "SELL", orderType:"MARKET", quantity: qty, clientOrderId: client_order_id_fn(), timeInForce:"DAY"}`.
5. `POST /orders` (헤더 X-Tossinvest-Account). `raise_for_status()` 후 `result.orderId` 존재 확인.

## 7. 에러 처리

- 비-2xx → `raise_for_status()` + 본문 메시지로 명확한 예외(어떤 단계/종목인지).
- 응답 envelope 누락/`result` 없음 → 명확한 예외.
- `qty < 1`(소액) → 스킵(무동작).
- 토큰 만료 → `_ensure_token`이 선제 갱신.
- `clientOrderId` 멱등키로 재시도 시 중복 체결 방지.

## 8. 테스트 (오프라인, httpx MockTransport — 실 스키마 흉내, 네트워크 0)

- 토큰: `issue_token` → access_token 저장·만료시각 설정. `_ensure_token`이 만료 시 재발급(주입 now/만료로 검증).
- 계좌해석: `account_seq` 미지정 → `GET /accounts`의 첫 BROKERAGE seq 사용, 이후 캐시(재호출 없음).
- get_account: holdings(`marketValue.amount.usd`) + buying-power(`cashBuyingPower`) → `Account(equity=pos+cash, cash)`.
- get_positions: items(usd) → `{symbol: marketValue.amount}`, quantity 0/타통화 제외.
- 주문: `submit_order`가 `prices`로 floor 수량 계산, body(side BUY/SELL, orderType MARKET, quantity, clientOrderId) POST, `result.orderId` 확인. `qty<1` → POST 안 함(스킵). 주입 `client_order_id_fn`로 결정적 검증.
- envelope: `result` 래핑 파싱. 비-2xx → 예외.
- 모든 응답은 MockTransport가 path로 라우팅.

## 9. 실 스모크 스크립트 (`scripts/toss_smoke.py`, 사용자 실행)

env `TOSS_CLIENT_ID`/`TOSS_CLIENT_SECRET`(선택 `TOSS_ACCOUNT_SEQ`) 설정 후:
1. `TossBroker()` → `issue_token()` 성공 출력.
2. `_resolve_account_seq()`·`get_account()`·`get_positions()` 출력(실 계좌 상태).
3. (선택, 기본 비활성 플래그) 소량 `submit_order(Order(symbol,"buy", 소액))` → orderId 출력.
4. **경고문**: TOSS는 모의투자가 없어 **실제 체결**된다 — 소액·취소 가능 상황에서만, 본인 책임 하에 실행.

## 10. 비범위

- broker_select/live 모드 배선(실주문 경로 — 별도 신중 작업), 정정/취소(modify/cancel), KR 종목 운용, 체결조회·웹소켓 실시간, 다통화 FX 합산, `orderAmount`(US 정규장) 경로, sellable-quantity/commission 활용.
