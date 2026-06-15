# OhMyStock 2단계 — 자금·리스크(G2) 설계

**작성일:** 2026-06-15
**상태:** 설계 확정
**선행:** 1단계 토대(데이터·전략·엔진·G1 지표) 완료, main 머지·푸시됨

---

## 목표

1단계의 `BacktestResult` 위에 자금관리·생존 검증 3종을 추가하고, 두 번째 전략(모멘텀)을 더한다.

| 항목 | 모듈 | 설명 |
|------|------|------|
| ⑨ 켈리공식 | `core/validation/kelly.py` | 거래 승률·손익비로 최적 베팅 비율 산출 |
| ⑯ 파산확률 | `core/validation/ruin.py` | 수익률 부트스트랩으로 파산(임계 손실) 확률 추정 |
| ⑧ 용량분석 | `core/validation/capacity.py` | ADV(평균거래대금) 대비 최대 투입 가능 시드 |
| 모멘텀 전략 | `core/strategy/momentum.py` | 최근 수익률 상위 K개 동일가중 보유 |

## 공통 계약

기존 `Validator`-형 함수 시그니처를 따른다: `(result[, ...]) -> ValidationReport`(`base.py`의 `ValidationReport(name, value, passed, threshold, message)` 재사용). 이로써 1단계 리뷰가 지적한 "지표가 Validator 계약과 분리됨"을 G2부터 좁힌다.

## 각 항목 정의

### ⑨ 켈리공식 (kelly.py)
거래 손익(`result.trades["pnl"]`)에서:
- 승률 `p = #(pnl>0) / #trades`
- 평균이익 `avg_win = mean(pnl>0)`, 평균손실 `avg_loss = |mean(pnl<0)|`
- 손익비 `b = avg_win / avg_loss`
- 켈리 비율 `f* = p - (1-p)/b`
- 권장: **하프 켈리** `f*/2` (실무 표준, 변동성 절반)
- 가드: 거래 0 / 손실 0(b=∞) / 이익 0 → 안전 처리
- `passed = f* > 0` (양의 기대우위), `value = f*`, message에 하프켈리 병기

### ⑯ 파산확률 (ruin.py)
`result.returns`(일별 수익률)를 복원추출 부트스트랩으로 같은 길이 경로 `n_sims`개 생성 →
각 경로의 시작 대비 누적수익이 한 번이라도 `-ruin_threshold`(기본 0.5, 즉 -50%) 밑으로 내려가면 파산 →
`파산확률 = 파산 경로 수 / n_sims`. `np.random.default_rng(seed)`로 결정적.
- `passed = 파산확률 <= 허용치(기본 0.05)`, `value = 파산확률`

### ⑧ 용량분석 (capacity.py)
`bars`(거래량·종가)와 `result.positions`(비중)에서:
- 종목별 ADV 달러 = `mean(volume * close)` (전체 구간)
- 최대 주문 달러 = `max_participation`(기본 0.1) × ADV달러
- 보유 비중 `w`일 때 시사 최대시드 = `최대주문달러 / w`
- **용량 = 보유 포지션들에 대한 최소 시사 최대시드**
- `passed = initial_capital <= 용량`, `value = 용량`(통화). 500만원 규모에선 항상 여유 → 통과 + "현재 규모 영향 없음" 메시지

### 모멘텀 전략 (momentum.py)
`Momentum(lookback=90, top_k=3)`:
- 추세지표 `mom = close / close.shift(lookback) - 1`
- 매일 `mom` 상위 `top_k` 종목 선택, 동일가중(`1/top_k`)
- lookahead 방지: 최종 비중 `shift(1)`
- 가드: lookback 미만 구간 0, 유효 종목 < top_k면 가능한 종목만

## 통합

- 각 검증은 독립 모듈+테스트. CLI 리포트(`cli.py`)에 G2 섹션 추가하여 켈리·파산확률·용량 출력.
- 모멘텀은 전략 선택지로 노출(리포트 헤더에 전략명 표기).

## 비범위

견고성(G3)·시장구조(G4)·웹·실거래는 이후 단계.
