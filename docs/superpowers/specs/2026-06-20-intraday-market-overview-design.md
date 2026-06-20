# 시장 개요 인트라데이(준실시간) 설계 (v2)

**작성일:** 2026-06-20
**상태:** 설계 확정
**선행:** v1 시장 개요(`ohmystock/market/overview.py::build_overview`, `GET /api/market/overview`, `MarketOverviewPanel`).

---

## 1. 목표

v1 시장 개요가 **일봉 종가(EOD)**만 보여줘 장중엔 어제 값에 멈추는 문제를, **장중 현재가(준실시간)**로 갱신되게 바꾼다. 장 마감 시 동작은 v1과 동일(정확). yfinance는 약 15분 지연 → **준실시간(지연 시세)**임을 명시.

확정된 결정:
- 데이터: yfinance `fast_info`의 `last_price`(현재가)·`previous_close`(전일종가)·`year_high`/`year_low`(52주). `value`=현재가, `change`=현재가−전일종가(표준 "오늘 등락", 장중·마감 통일).
- 스파크라인(A): **장중=인트라데이(오늘 5분봉) / 마감(또는 인트라데이 미존재)=일봉**. provider가 판단해 closes 리스트를 제공.
- 신선도: 백엔드 캐시 TTL **300→60초**, 프론트 폴링 30초 유지.
- 정직성: 프론트 패널에 "지연 시세(약 15분)" 라벨.
- **API 응답 형태 불변** — `{markets, items:[{key,label,value,change,change_pct,sparkline,badge}]}`. 프론트는 라벨만 추가.

재사용/수정: `ohmystock/market/overview.py`(provider 계약 변경), `server/app.py`(`_default_market_provider` 재작성 + `_MARKET_TTL`), `web/src/components/MarketOverviewPanel.tsx`(라벨). 비범위: 진짜 틱 실시간(WebSocket), 유료 시세.

---

## 2. provider 계약 변경 (`build_overview`)

기존: `provider(symbol) -> DataFrame`(일봉, close 컬럼).
신규: `provider(symbol) -> dict`:
```python
{
  "last": float,        # 현재가(장중 살아있음, 마감 시 종가)
  "prev_close": float,  # 전일 종가
  "year_high": float,   # 52주 고가
  "year_low": float,    # 52주 저가
  "sparkline": list[float],  # 스파크라인용 종가 시퀀스(인트라데이 또는 일봉)
}
```

`build_overview(provider, *, kr_cal, us_cal, now, items=_ITEMS)` 계산:
- `value = last`, `change = last - prev_close`, `change_pct = change/prev_close*100`(prev 0이면 0).
- `sparkline = q["sparkline"]`(최근 30개로 자름, round 2).
- `badge = _badge(cfg, last, year_high, year_low)`(기존 로직 그대로 — VIX 고변동성 / 52주 고저 근접).
- 항목별 예외는 `continue`(해당 항목만 제외). `markets` 장 상태는 v1 그대로(kr/us 캘린더 `is_open(now)`).

---

## 3. 기본 provider (`server/app.py::_default_market_provider`)

`_default_market_provider(symbol) -> dict`:
1. `t = yf.Ticker(symbol)`; `fi = t.fast_info` → `last_price`, `previous_close`, `year_high`, `year_low`.
   - 누락 필드는 fallback(예: year_high/low 없으면 최근 1년 일봉의 max/min). 핵심 `last_price`/`previous_close` 없으면 예외 → build_overview가 스킵.
2. 스파크라인:
   - `intraday = yf.download(symbol, period="1d", interval="5m")` 시도 → close가 2개 이상이면 그 closes 사용(인트라데이).
   - 비어있으면 `daily = yf.download(symbol, period="1mo", interval="1d")`의 최근 30 closes(일봉).
3. 위 묶음 dict 반환.

캐시: `_MARKET_TTL = 60`. 엔드포인트 로직(캐시·장 상태)은 v1 그대로.

---

## 4. 프론트 (`MarketOverviewPanel.tsx`)

- 제목 옆에 작은 배지: **"지연 시세 · 약 15분"**(또는 유사). 스타일은 기존 배지와 통일.
- 나머지(카드·스파크라인·등락 색·장 상태·폴링)는 v1 그대로. API 형태 불변이라 데이터 처리 변경 없음.

---

## 5. 에러 처리

- provider가 한 심볼에서 실패(네트워크·필드 누락) → build_overview가 그 항목만 제외. 전체 0개면 엔드포인트 502(v1 동일).
- 인트라데이 fetch 실패 → 일봉 스파크라인으로 폴백. 그래도 실패면 빈 스파크라인(카드는 값/등락만).

## 6. 테스트

- `build_overview`: 가짜 provider(quote dict 반환)로 value/change/change_pct/sparkline/badge(52주 고저·VIX) 검증. 기존 일봉-DataFrame 테스트는 quote-dict 형태로 **교체**.
- 엔드포인트 `/api/market/overview`: 주입 provider(quote dict)로 구조·캐시 검증(기존 테스트의 가짜 provider 반환형 교체).
- 실 provider(`_default_market_provider`)는 yfinance·네트워크라 단위 테스트 안 함 → 실 서버 스모크로 확인(장중엔 value가 종가와 달라짐).
- 프론트: `npm run build`.

## 7. 비범위

- 진짜 틱 단위 실시간(WebSocket 스트리밍), 유료 실시간 피드.
- 심볼별 정밀 장 상태 기반 스파크라인 선택(현재는 "인트라데이 데이터 있으면 사용"으로 단순화).
- 뉴스 레이어(별도 v2 항목).
