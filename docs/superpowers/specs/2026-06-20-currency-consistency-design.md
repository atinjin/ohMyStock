# 통화 일관성 설계 (USD 기준 + ≈원 참고)

**작성일:** 2026-06-20
**상태:** 설계 확정
**로드맵:** §5 단위 일관성(통화)
**선행:** 백테스트/페이퍼/라이브 대시보드, 시장 개요(`USDKRW=X`), 실 계좌 패널(원화 환산 패턴).

---

## 1. 목표

백테스트·페이퍼·라이브가 **US 주식(USD 가격)**으로 계산되는데 화면엔 "원"으로 라벨된 **통화 혼용**을 바로잡는다. 시스템 기준 통화를 **USD로 통일**(데이터·LivePreview·TOSS와 일치)하고, 원 감각은 **≈원 참고**(환율)로 유지한다.

확정된 결정(Q1=A):
- 기준 통화 **USD**. 백테스트 최종자산·페이퍼 equity/cash/체결·자본 입력 모두 USD($).
- 원은 **참고**로만 — `≈₩…` + 기존 한글 읽기("…만원")를 **환산된 원 금액에 적용**.
- 환율은 yfinance `USDKRW=X`(키 불필요), 백엔드 `/api/fx`로 노출(캐시).
- 자본 입력 기본값을 USD 친화적으로(프론트 `$10,000`). 백엔드 `Config.initial_capital` 기본값(5,000,000)은 테스트 호환 위해 유지하되 의미를 USD로 재해석(주석 갱신).

재사용/수정: `ohmystock/config.py`(currency 필드), `ohmystock/report.py`(currency 포함), `ohmystock/paper/service.py`(state에 currency), `server/app.py`(`/api/fx`), 프론트 `App.tsx`·`components/PaperPanel.tsx`·`components/BacktestForm.tsx`·`api.ts`·신규 통화 헬퍼.

---

## 2. 백엔드

### 2.1 통화 명시
- `Config`에 `currency: str = "USD"` 추가. `initial_capital` 주석 "원" → "USD 기준(시스템 통화)".
- `report.full_report(...)` 반환에 `"currency": config.currency` 추가.
- `PaperService.get_state()` 반환에 `"currency": config.currency` 추가(없으면 추가).

### 2.2 환율 엔드포인트 `GET /api/fx?base=USD&quote=KRW`
응답: `{"base":"USD","quote":"KRW","rate": 1531.0}` (1 USD = ? KRW).
- 동작: `rate = float(app.state.market_provider("USDKRW=X")["last"])` 재사용(시장 개요 provider). `app.state.fx_cache`에 300초 캐시.
- `(base,quote) != ("USD","KRW")` → 400. provider 실패 → 502.
- `create_app`에 `app.state.fx_cache = {}` 추가(주입은 기존 `market_provider`로 충분).

---

## 3. 프론트엔드 (표기 통일)

### 3.1 공용 통화 헬퍼 (`web/src/format.ts` 또는 신규)
- `usd(n)` = `Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0})`.
- 기존 `korean(v)`("…억/만원")는 그대로 두되 **원 환산값에 적용**.
- `approxKrw(usd, rate)` → `rate` 있으면 `" ≈ " + korean(usd*rate)`(예: " ≈ 1,531만원"), 없으면 `""`.

### 3.2 FX 클라이언트 (`api.ts`)
- `getFx()` → `{base,quote,rate}`. `fetch('/api/fx')`, 실패 시 기존 `parseError`.

### 3.3 화면별 적용
- **App.tsx**: `final_equity`를 KRW → `usd(...)` + `approxKrw(...)`(FX). 상단에서 `getFx()` 1회 받아 보관(실패 시 원 참고 생략).
- **PaperPanel.tsx**: equity/cash/peak/체결 notional의 `…원` → `usd(...)` + (요약 카드엔) `approxKrw`. FX는 App에서 prop 또는 자체 `getFx()`.
- **BacktestForm.tsx**: 자본 입력 suffix `원` → `$`. 입력값 아래 보조표기를 `$X` + `≈ …만원`(환산)으로. 기본 자본값 `10000`(USD).
- **EquityChart.tsx**: 숫자 포맷 유지(통화기호 없음) — 변경 없음 또는 축 라벨 "$" 추가(선택).

### 3.4 일관성
- LivePreview(이미 USD)·실 계좌 TOSS(USD)·시장 개요와 표기 통일. KIS 실 계좌(원)는 그대로(실제 KRW 계좌라 정확).

---

## 4. 에러 처리

- `/api/fx`: provider 실패 → 502. 프론트는 FX 실패 시 **≈원 참고만 생략**(USD 표시는 정상).
- 통화 필드 누락(구버전 응답) → 프론트는 기본 "USD"로 간주.

## 5. 테스트

- 백엔드: `full_report`에 `currency=="USD"` 포함; `PaperService.get_state()`에 `currency` 포함; `/api/fx`가 주입 `market_provider`로 `rate` 반환 + 캐시(2회 호출 시 provider 1회) + 잘못된 통화쌍 400.
- 프론트: `npm run build` 타입체크. (레포 관행상 FE 자동테스트 없음.)

## 6. 비범위

- KRW 기준 모드/통화 선택 옵션(이번은 USD 고정), 다중 환율쌍, 실시간 FX 스트리밍.
- 백테스트 엔진의 통화 환산(엔진은 가격 통화 그대로 — USD 데이터면 USD 결과). KR 종목 백테스트(현재 데이터는 US).
