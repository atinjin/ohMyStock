# KIS 어댑터 실연동 설계 (모의투자 우선)

**작성일:** 2026-06-20
**상태:** 설계 확정
**로드맵:** 실계좌 스케줄링 § "KIS 어댑터 실연동 검증"
**참고:** KIS 공식 샘플 [koreainvestment/open-trading-api](https://github.com/koreainvestment/open-trading-api)로 tr_id·엔드포인트·필드 검증함.

---

## 1. 목표

인터페이스만 맞춰둔 `KISBroker`를 **프로덕션급으로 재작성**하고(OAuth 자동 갱신·실 응답 스키마·hashkey·notional→수량 변환·모의/실전 스위치), **오프라인으로 정확히 검증**한다. 실제 모의투자 계좌 end-to-end 스모크는 키를 가진 사용자가 **제공된 스크립트**로 실행한다.

확정된 결정:
- 범위: `KISBroker` 정확성 + 오프라인 검증 + 사용자용 실 스모크 스크립트. (broker_select 연결·전체 라이브 루프는 비범위)
- 안전: **모의투자(paper) 우선**. `paper=True`(기본)면 모의 도메인+`V*` tr_id, `paper=False`면 실전+`T*`. 실전은 명시적으로만.
- 가격: 주문 시 KIS 현재가 조회로 `수량 = floor(notional / 현재가)`(정수, 소수점 불가). 1주 미만이면 주문 스킵.
- 실 스모크는 사용자 실행(키 보안). 에이전트는 오프라인(MockTransport)으로만 검증.

재사용/수정: `ohmystock/core/broker/kis.py::KISBroker`(재작성), `core/broker/base.py::Account/Order`. env `KIS_APP_KEY`/`KIS_APP_SECRET`/`KIS_ACCOUNT_NO`.

---

## 2. 검증된 KIS 사양 (구현 기준)

| 항목 | 값 |
|------|-----|
| base URL | 실전 `https://openapi.koreainvestment.com:9443` / 모의 `https://openapivts.koreainvestment.com:29443` |
| 토큰 | `POST /oauth2/tokenP` body `{grant_type:"client_credentials", appkey, appsecret}` → `access_token`, `access_token_token_expired`("%Y-%m-%d %H:%M:%S"), `expires_in`(초) |
| hashkey | `POST /uapi/hashkey` (주문 본문 → `{HASH}`); KIS "필수 아님, 생략 가능" |
| 잔고 | `GET /uapi/domestic-stock/v1/trading/inquire-balance` tr_id `TTTC8434R`/`VTTC8434R`. 쿼리: CANO, ACNT_PRDT_CD, AFHR_FLPR_YN="N", OFL_YN="", INQR_DVSN="02", UNPR_DVSN="01", FUND_STTL_ICLD_YN="N", FNCG_AMT_AUTO_RDPT_YN="N", PRCS_DVSN="00", CTX_AREA_FK100="", CTX_AREA_NK100="". 응답 `output2[0].tot_evlu_amt`(총평가=equity)·`dnca_tot_amt`(예수금=cash), `output1[].pdno`·`evlu_amt`(평가금액)·`hldg_qty`(보유수량) |
| 현재가 | `GET /uapi/domestic-stock/v1/quotations/inquire-price` tr_id `FHKST01010100`. 쿼리 `FID_COND_MRKT_DIV_CODE="J"`, `FID_INPUT_ISCD`=종목6자리. 응답 `output.stck_prpr`(현재가) |
| 주문 | `POST /uapi/domestic-stock/v1/trading/order-cash` tr_id 매수 `TTTC0802U`/`VTTC0802U`·매도 `TTTC0801U`/`VTTC0801U`. body `CANO, ACNT_PRDT_CD, PDNO, ORD_DVSN="01"(시장가), ORD_QTY=str(int(qty)), ORD_UNPR="0"`. 성공 `rt_cd=="0"`(200이어도 본문으로 판정) |
| 계좌번호 | `"12345678-01"` → `CANO="12345678"`, `ACNT_PRDT_CD="01"` |

---

## 3. KISBroker 구조 (재작성)

```python
class KISBroker:
    def __init__(self, app_key=None, app_secret=None, account_no=None, *,
                 paper=True, client=None, access_token=None,
                 token_expires_at=None, use_hashkey=False): ...
    # 내부: _ensure_token(), _hashkey(body), _current_price(symbol),
    #       _tr(buy/sell/balance), _auth_headers(tr_id, hashkey=None)
    def issue_token(self) -> str: ...          # 토큰 발급 + 만료시각 저장
    def get_account(self) -> Account: ...       # inquire-balance
    def get_positions(self) -> dict[str,float]: ...
    def submit_order(self, order: Order) -> None: ...
```

- `paper`로 base_url(client 미주입 시)과 tr_id 접두(V/T)를 선택. `_tr("buy")` 등이 모드에 맞는 tr_id 반환.
- `client` 주입 시 그 client 사용(테스트). 미주입 시 `paper` 기준 base_url로 httpx.Client 생성.
- `use_hashkey=False` 기본(KIS 선택 사항). True면 주문 본문 hashkey 생성 후 헤더 첨부.

---

## 4. 토큰 라이프사이클 (`_ensure_token`)

- `access_token` + `token_expires_at`(datetime) 캐시. 모든 API 호출 전 `_ensure_token()`:
  - 토큰 없거나 만료(또는 만료 임박: now ≥ expires - 60s)면 `issue_token()` 호출.
- `issue_token()`: `/oauth2/tokenP` 호출 → `access_token` 저장, `access_token_token_expired`(파싱) 또는 `expires_in`(now+초)로 `token_expires_at` 설정.
- (주입된 `access_token`이 있으면 그대로 사용, 만료시각 없으면 유효 가정.)

## 5. 주문 흐름 (`submit_order`)

1. `_ensure_token()`.
2. `price = _current_price(order.symbol)` (inquire-price → `output.stck_prpr`).
3. `qty = floor(order.notional / price)`. `qty < 1`이면 **주문 스킵**(소액 — 예외 아님, 무동작).
4. `body = {CANO, ACNT_PRDT_CD, PDNO=symbol, ORD_DVSN="01", ORD_QTY=str(qty), ORD_UNPR="0"}`.
5. `use_hashkey`면 `hashkey = _hashkey(body)` → 헤더 첨부.
6. `POST order-cash` (tr_id=매수/매도, 모드 분기). `resp.raise_for_status()` 후 `rt_cd=="0"` 확인, 아니면 `msg1` 포함 예외.

## 6. 에러 처리

- KIS는 HTTP 200이어도 `rt_cd != "0"`로 실패 표시 → 본문 검사해 `ValueError(f"KIS 주문 실패 [{rt_cd}] {msg1}")`.
- 토큰 만료 → `_ensure_token`이 선제 갱신(또는 호출 후 만료 감지 시 재발급).
- 현재가 0/조회 실패 → 명확한 예외(어떤 종목인지).
- 수량 0(소액) → 스킵(무동작), 잔고 부족은 KIS rt_cd로 노출.

## 7. 테스트 (오프라인, httpx MockTransport — 실 스키마 흉내)

- 토큰: `issue_token` → access_token 저장·만료시각 설정. `_ensure_token`이 만료 시 재발급(주입 now/만료로 검증).
- 잔고: `inquire-balance` 응답(output1/output2) → `get_account`(tot_evlu_amt/dnca_tot_amt), `get_positions`(pdno/evlu_amt, 0 제외).
- 현재가: `inquire-price` → `output.stck_prpr` 파싱.
- 주문: `submit_order`가 현재가로 floor 수량 계산, 올바른 tr_id(paper vs live), body(ORD_QTY/ORD_DVSN/ORD_UNPR) POST, `rt_cd=="0"` 통과. `rt_cd!="0"` → 예외. `qty<1` → 스킵(POST 안 함). `use_hashkey=True` → hashkey 헤더 포함.
- 모드: `paper=True/False`로 tr_id 접두 V/T 분기 검증.
- 모든 응답은 MockTransport가 path/tr_id로 라우팅(네트워크 없음).

## 8. 실 스모크 스크립트 (사용자 실행)

`scripts/kis_smoke.py`(또는 README 안내): env `KIS_APP_KEY`/`KIS_APP_SECRET`/`KIS_ACCOUNT_NO` 설정 후
1. `KISBroker(paper=True)` 생성 → `issue_token()` 성공 출력.
2. `get_account()`·`get_positions()` 출력(모의투자 잔고).
3. (선택) 소량 `submit_order(Order("005930","buy", 소액))` → rt_cd 확인.
4. 주의문: 실전(`paper=False`)은 실제 체결됨 — 모의투자로만 검증 권장.

## 9. 비범위

- 현재가 도메인 이슈(모의투자 도메인 시세 미지원 시): 기본은 주입 client/모드 base_url 사용. 필요 시 시세를 실전 도메인으로 분리하는 건 스모크 후 후속.
- broker_select에 KIS 연결, 전체 라이브 루프, 정정/취소, 체결조회 웹소켓, 해외주식.
