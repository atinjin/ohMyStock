# OhMyStock 3단계 — 견고성 검증(G3) 설계

**작성일:** 2026-06-16
**상태:** 설계 확정
**선행:** 1·2단계 완료(main 머지·푸시)

---

## 목표

전략이 "과거에 우연히 맞은 것"이 아니라 **시간·표본·파라미터를 바꿔도 견디는지**를 검증한다. 이것이 진짜 자동매매가 통과해야 하는 핵심 관문이다.

| 항목 | 모듈 | 핵심 |
|------|------|------|
| ④ out-of-sample | `core/validation/out_of_sample.py` | 앞부분 학습/뒷부분 검증 성과 비교 |
| ③ walk-forward | `core/validation/walk_forward.py` | 시계열 K분할 폴드별 일관성 |
| ⑤ 몬테카를로 | `core/validation/monte_carlo.py` | 수익률 부트스트랩 분포·신뢰구간 |
| ⑥ 스트레스 | `core/validation/stress.py` | 과거 위기 구간 성과·생존 |
| ② 과최적화 | `core/validation/overfitting.py` | IS 최적 파라미터의 OOS 성능 격차 |

## 공유 헬퍼 (선행 구현)

대부분의 G3 검증은 단일 전체 `BacktestResult`의 `returns`를 구간 슬라이스해 평가한다. 중복을 막기 위해 공통 통계 헬퍼를 둔다.

- `core/validation/_stats.py`
  - `annualized_sharpe(returns, trading_days=252, risk_free_rate=0.0) -> float` (기존 metrics.sharpe와 동일 ddof=1 규약)
  - `total_return(returns) -> float`
  - `max_drawdown_from_returns(returns) -> float`
- `core/backtest/runner.py`
  - `backtest(strategy, bars, config) -> BacktestResult` (generate_signals + run_backtest 묶음). 과최적화의 파라미터 재실행에 사용.

## 각 항목 정의

공통 반환: `ValidationReport(name, value, passed, threshold, message)`.

### ④ out-of-sample (split=0.7)
`returns`를 앞 70%(IS)/뒤 30%(OOS)로 분할. 각 구간 연환산 Sharpe 계산.
- `value = OOS Sharpe`, `passed = OOS Sharpe > 0 그리고 OOS >= degrade(0.5)*IS`
- 과적합이면 OOS가 급락 → 탈락.

### ③ walk-forward (n_folds=5)
`returns`를 연속 K개 폴드로 분할. 폴드별 총수익·Sharpe.
- `value = 양(+)수익 폴드 비율`, `passed = 비율 >= 0.6` (시간대 전반 일관성)

### ⑤ 몬테카를로 (n_sims=10000, seed=0)
`returns`를 복원추출 재표본해 분포 생성. 최종 총수익 분포의 5/50/95 백분위.
- `value = 5퍼센타일 총수익`, `passed = 5퍼센타일 > -ruin(기본 0.0 이상이면 양호; 기본 통과조건: 5퍼센타일 총수익 > 0)`
- np.random.default_rng(seed)로 결정적.

### ⑥ 스트레스 (기본 위기창)
기본 위기 구간(이름, 시작, 끝): COVID 2020(02-19~03-23), 2022 약세장(01-01~10-12), 2018 Q4(10-01~12-24). `equity_curve`(또는 returns)를 각 창으로 슬라이스, 데이터와 겹치는 창만 평가. 창별 수익·MDD.
- `value = 최악 창의 MDD`, `passed = 모든 겹치는 창의 MDD < severe(0.5)`
- 겹치는 창이 없으면 통과 + "해당 위기 구간 데이터 없음".

### ② 과최적화 (strategy_factory, param_grid, split=0.7)
파라미터 그리드 각각으로 전체 백테스트 → returns를 IS/OOS로 슬라이스 → IS Sharpe로 최적 파라미터 선택 → 그 파라미터의 OOS Sharpe 측정.
- `value = 최적화 격차 = IS_best_Sharpe - OOS_Sharpe`
- `passed = OOS_Sharpe > 0 그리고 격차 <= gap_limit(기본 1.0)`
- 기본 그리드: MACrossover (short,long) ∈ {(10,50),(20,60),(20,100),(50,150)} 등.

## 통합

CLI에 "견고성 (G3)" 섹션 추가: out-of-sample·walk-forward·monte-carlo·stress 출력(과최적화는 파라미터 그리드가 필요하므로 별도 데모/옵션). 각 검증은 독립 모듈+테스트.

## 비범위

시장구조(G4)·웹·실거래는 이후 단계.
