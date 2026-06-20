# 대시보드 개선 설계 (시장 개요 + 소소한 개선)

**작성일:** 2026-06-20
**상태:** 설계 확정
**선행:** FastAPI 대시보드(server/app.py + web/), `MarketCalendar`, `YFinanceAdapter`, `KISBroker`/`TossBroker`(실 API 검증), 실 계좌 패널.

---

## 1. 목표

대시보드에 **시장 개요 패널**(주요 지수·환율 카드, Toss식)을 추가하고, 실 계좌 패널·캘린더의 소소한 개선을 함께 처리한다. 외부 키가 필요한 **뉴스 레이어는 v2(로드맵 후속)**.

확정된 결정:
- 범위 묶음(A): 시장 개요 + 종목명 + USD→원화 + 캘린더 색을 **한 계획(v1)**으로. 뉴스(LLM 한글 태그)는 v2 로드맵.
- 태그 슬롯(A): v1은 **계산형 배지**(52주 고저 근접·고변동성). 진짜 뉴스 태그는 v2.
- 색: 한국식 **상승=빨강(`--fail`계열 아님, 별도 up/down 색) / 하락=파랑**.
- 데이터: yfinance(지수·환율), 장 상태는 exchange_calendars(US=XNYS, KR=XKRX). v1은 **일봉(EOD) 종가 기준**(장 마감 시 정확); 인트라데이 실시간은 후속.

재사용/수정: `server/app.py`(엔드포인트), 신규 `ohmystock/market/overview.py`, 신규 `web/src/components/MarketOverviewPanel.tsx`, `web/src/api.ts`, `web/src/App.tsx`. 기존: `KISBroker`/`TossBroker`(get_holdings 추가), `web/src/components/BrokerAccountPanel.tsx`, `web/src/App.css`(캘린더).

---

## 2. 시장 개요 패널 (v1 메인)

### 2.1 백엔드 `GET /api/market/overview`
응답:
```json
{
  "markets": { "kr": {"open": false}, "us": {"open": false} },
  "items": [
    {"key":"nasdaq","label":"나스닥","value":26517.93,"change":496.28,
     "change_pct":1.90,"sparkline":[...최근 30 종가...],"badge":"52주 고점 근접"}
  ]
}
```
- 지수/환율(yfinance 심볼): 나스닥 `^IXIC`, S&P500 `^GSPC`, 다우 `^DJI`, VIX `^VIX`, 코스피 `^KS11`, 달러환율 `USDKRW=X`, 나스닥100선물 `NQ=F`.
- 항목당: `value`=최근 종가, `change`=최근−직전 종가, `change_pct`=change/직전×100, `sparkline`=최근 30 종가, `badge`(계산형).
- **계산형 배지**: 52주 고가의 98% 이상 → `"52주 고점 근접"`; 52주 저가의 102% 이하 → `"52주 저점 근접"`; VIX는 value≥20이면 `"고변동성"`(우선); 그 외 `null`.
- **장 상태**: US(XNYS)·KR(XKRX) 캘린더로 "지금 개장 중인가" — 오늘이 거래일이고 현재시각(해당 거래소 tz)이 장 시간 내면 `open:true`.

### 2.2 데이터 제공자 + 캐시
- `ohmystock/market/overview.py`:
  - `build_overview(provider, *, kr_cal, us_cal, now) -> dict` — provider로 각 심볼의 최근 1년 일봉을 받아 value/change/sparkline/badge 계산 + 장 상태.
  - `provider(symbol) -> DataFrame`(일봉, close 포함). 기본 구현은 yfinance(주입식 downloader). **테스트는 가짜 provider 주입**.
- 엔드포인트는 `app.state.market_provider`(기본 yfinance 기반) 사용 + 결과를 **app.state에 짧은 TTL(예 300초) 캐시**(yfinance 반복 호출·지연 회피). 캐시·now는 테스트를 위해 주입 가능.

### 2.3 프론트 `MarketOverviewPanel.tsx`
- 상단: **국내/해외 장 상태**(`국내 장 열림/닫힘`, `해외 장 열림/닫힘`) 점+텍스트.
- 카드 그리드: 각 항목 — 라벨 + (있으면)배지 + 값 + 등락(`+496.28 (1.90%)`, **상승 빨강/하락 파랑**) + **미니 스파크라인**(SVG polyline, 색은 등락 방향).
- 30초 폴링 + 수동 새로고침(실 계좌 패널과 동일 패턴). App.tsx 상단(백테스트 결과 위 또는 사이드 아래)에 배치.

---

## 3. 소소한 개선 (v1)

### 3.1 보유 종목명 표시
- `KISBroker.get_holdings() -> list[{symbol,name,value}]`(output1 `pdno`/`prdt_name`/`evlu_amt`, 0 제외), `TossBroker.get_holdings()`(items `symbol`/`name`/`marketValue.amount`, qty>0 + 통화 일치). `get_positions()`는 `get_holdings()`에서 파생(동작 불변).
- `/api/broker/account`의 `positions`를 `[{symbol,value}]` → `[{symbol,name,value}]`로(엔드포인트가 `get_holdings` 사용).
- `BrokerAccountPanel`: 보유 테이블에 **"종목명" 컬럼** 추가.

### 3.2 USD 금액 원화 환산 참고
- `TossBroker.exchange_rate(base="USD", quote="KRW") -> float` — `GET /api/v1/exchange-rate?baseCurrency=USD&quoteCurrency=KRW` → `result.rate`(1 USD=? KRW).
- `/api/broker/account`(broker=toss)에 `krw_rate` 필드 추가(usd 통화일 때). KIS(krw)는 `krw_rate=null`.
- `BrokerAccountPanel`: TOSS(usd)면 equity·cash·평가금액 옆에 **`(≈₩…)`** 참고 표기. 환율 없으면 생략.

### 3.3 캘린더 색 구분 강화 (`App.css`)
- 현재 `cal-cell-open`(투명)·`cal-cell-holiday`(surface-2)가 너무 비슷. 거래일은 **명확한 활성 배경/글자**, 휴장은 **뚜렷이 구분되는 muted 배경 + 흐린 글자**(또는 옅은 적색 틸트)로. 범례 점 색도 일치. CSS-only(컴포넌트 로직 불변).

---

## 4. 에러 처리

- `/api/market/overview`: 일부 심볼 조회 실패 시 그 항목만 제외(또는 value=null)하고 나머지 반환; 전체 실패 시 502. 프론트는 빈/에러 표시.
- `/api/broker/account`: 기존대로(400/502). `krw_rate` 조회 실패는 치명적 아님 → `null`로 두고 환산만 생략.
- 캘린더 색: 로직 변경 없음.

## 5. 테스트

- 백엔드 `build_overview`: 가짜 provider(고정 일봉)로 value/change/change_pct/sparkline/badge(52주 고점·저점·VIX 고변동성) + 장 상태(주입 now·캘린더) 검증.
- 엔드포인트 `/api/market/overview`: 주입 provider로 JSON 구조·캐시(2회 호출 시 provider 1회) 검증.
- `get_holdings`(KIS/TOSS): name 포함·필터 검증; `get_positions`가 파생값으로 동일 결과.
- `/api/broker/account`: positions에 name 포함, TOSS는 krw_rate 포함(가짜 브로커).
- 프론트: `npm run build` 타입체크(레포 관행상 FE 자동테스트 없음).

## 6. 비범위 (v2 로드맵)

- **뉴스 레이어**: US(yfinance/Finnhub) + KR(네이버 검색 API) 최근 헤드라인 → (선택) LLM 한글 요약 태그(Anthropic 키). 시장 개요 배지를 진짜 뉴스로 교체.
- 인트라데이 실시간 지수(현재 v1은 EOD 종가), 종목 클릭 상세, 다계좌, 인증/접근제어(로컬 전용).
