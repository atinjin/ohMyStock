# OhMyStock 4단계 — 시장구조 검증(G4) 설계

**작성일:** 2026-06-16
**선행:** 1~3단계 완료(main)

## 목표

전략이 시장 국면·팩터·벤치마크와 어떤 관계인지 분해해, "그냥 시장을 산 것"과 다른 **진짜 우위(edge)**가 있는지 확인한다.

| 항목 | 모듈 | 핵심 |
|------|------|------|
| ⑰ 레짐 | `core/validation/regime.py` | 상승/하락 국면별 전략 성과 |
| ⑱ 상관관계 | `core/validation/correlation.py` | 전략-시장 상관(독립성) |
| ⑲ 팩터 익스포저 | `core/validation/factor_exposure.py` | 팩터 회귀 → 알파·베타·R² |
| ⑳ Economic Edge | `core/validation/economic_edge.py` | 벤치마크 대비 위험조정 초과 |

## 공유 헬퍼 (구현됨)

`core/validation/_market.py::equal_weight_benchmark(bars) -> pd.Series` — 유니버스 동일가중 매수보유 일별 수익률(시장 프록시). 4개 검증은 `benchmark_returns`를 인자로 받아 BacktestResult.returns와 공통 날짜로 정렬해 계산한다.

## 각 항목 정의 (반환 ValidationReport)

### ⑰ regime_test(result, benchmark_returns, window=20, floor=-0.20)
벤치마크의 `window`일 이동평균 부호로 상승/하락 국면 분류. 각 국면에서 전략 총수익 계산. `value = 하락국면 전략 총수익`, `passed = 하락국면 총수익 >= floor`(추세전략은 하락장에 현금화 → ~0 → 통과). 표본 부족시 실패.

### ⑱ correlation(result, benchmark_returns, max_abs=0.95)
전략-벤치마크 피어슨 상관. `value = corr`, `passed = |corr| < max_abs`(시장과 100% 동조가 아닌 독립적 요소 존재). 분산 0/표본 부족시 실패.

### ⑲ factor_exposure(result, factors: dict[str, Series], trading_days=252)
팩터(예: {"market": benchmark})에 대한 OLS 회귀(절편=알파, 계수=베타, R²). `value = 연환산 알파`, `passed = 알파 > 0`. message에 베타·R². np.linalg.lstsq 사용.

### ⑳ economic_edge(result, benchmark_returns, config)
전략 Sharpe vs 벤치마크 Sharpe, 전략 총수익 vs 벤치마크 총수익. `value = 전략Sharpe - 벤치Sharpe`, `passed = 전략Sharpe > 벤치Sharpe 그리고 전략총수익 > 0`. "그냥 지수 사는 것보다 나은가"의 최종 점검.

## 통합

CLI에 "시장구조 (G4)" 섹션: 벤치마크를 `equal_weight_benchmark(bars)`로 만들어 4개 검증 출력(factor_exposure는 {"market": benchmark}).

## 비범위

웹·실거래는 5·6단계.
