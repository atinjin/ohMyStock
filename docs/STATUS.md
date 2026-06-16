# OhMyStock — 구현 현황 및 향후 계획

**기준일:** 2026-06-16
**브랜치:** `main` (6단계 전부 머지)
**테스트:** Python 124개 통과(전부 오프라인), 프론트 빌드 통과
**커밋:** 38개, 작성자 atinjin

---

## 1. 한눈에 보기

자동매매 전략을 **20가지 검증**으로 채점하고, 통과한 전략을 **페이퍼/실거래**로 운용하는 시스템. 6단계로 나눠 단계마다 spec → plan → 멀티에이전트 구현 → 적대적 검증 → 통합 순으로 빌드했고, 모두 완료됐다.

| 단계 | 내용 | 상태 |
|------|------|------|
| 1. 토대 | 데이터·전략·백테스트 엔진·성과지표 6종·CLI | ✅ 완료 |
| 2. 자금·리스크 (G2) | 켈리·파산확률·용량분석 + 모멘텀 전략 | ✅ 완료 |
| 3. 견고성 (G3) | 과최적화·walk-forward·OOS·몬테카를로·스트레스 | ✅ 완료 |
| 4. 시장구조 (G4) | 레짐·상관관계·팩터익스포저·Economic Edge | ✅ 완료 |
| 5. 웹 | FastAPI 백엔드 + React 대시보드 | ✅ 완료 |
| 6. 실거래 | 브로커 계층·리스크가드·Alpaca/KIS 어댑터·드라이런 | ✅ 완료 |

---

## 2. 구현 완료 항목

### 2.1 20가지 검증 (전부 구현·개별 테스트·통합 리포트 노출)

| # | 항목 | 모듈 | 통합 노출 |
|---|------|------|----------|
| ① | 데이터 검증 | `core/data/validation.py` | 리포트 `data_validation` |
| ② | 과최적화 | `core/validation/overfitting.py` | G3 (그리드 서치) |
| ③ | walk-forward | `core/validation/walk_forward.py` | G3 |
| ④ | out-of-sample | `core/validation/out_of_sample.py` | G3 |
| ⑤ | 몬테카를로 | `core/validation/monte_carlo.py` | G3 |
| ⑥ | 스트레스 테스트 | `core/validation/stress.py` | G3 |
| ⑦ | 거래비용 | `core/backtest/costs.py` | 엔진 내장(항상 적용) |
| ⑧ | 용량분석 | `core/validation/capacity.py` | G2 |
| ⑨ | 켈리공식 | `core/validation/kelly.py` | G2 |
| ⑩ | MDD 제한 | `core/validation/metrics.py` | 성과지표 |
| ⑪ | 샤프 비율 | `core/validation/metrics.py` | 성과지표 |
| ⑫ | 소르티노 비율 | `core/validation/metrics.py` | 성과지표 |
| ⑬ | Calmar Ratio | `core/validation/metrics.py` | 성과지표 |
| ⑭ | 수익팩터 | `core/validation/metrics.py` | 성과지표 |
| ⑮ | Recovery Factor | `core/validation/metrics.py` | 성과지표 |
| ⑯ | 파산확률 | `core/validation/ruin.py` | G2 |
| ⑰ | 레짐 테스트 | `core/validation/regime.py` | G4 |
| ⑱ | 상관관계 | `core/validation/correlation.py` | G4 |
| ⑲ | 팩터 익스포저 | `core/validation/factor_exposure.py` | G4 |
| ⑳ | Economic Edge | `core/validation/economic_edge.py` | G4 |

### 2.2 핵심 기능

- **데이터 계층**: yfinance 어댑터(`MarketDataAdapter` 인터페이스) + parquet 캐시. 시장 교체는 어댑터만 추가.
- **전략 계층**: `MACrossover`, `Momentum` (둘 다 lookahead-safe). 전략 독립적 인터페이스.
- **백테스트 엔진**: 수익률 기반, 거래비용(수수료·슬리피지·스프레드) 내장, `BacktestResult` 산출.
- **검증 계층**: 20개 검증 + 공유 통계 헬퍼(`_stats`, `_market`).
- **리포트**: `report.full_report()` 단일 진실원천(SSOT) → CLI 텍스트·웹 JSON 공용.
- **브로커 계층**: `Broker` 인터페이스, `PaperBroker`(인메모리 시뮬), `RiskGuard`(MDD 한도 진입차단), `rebalance()`(일일 리밸런서), `AlpacaBroker`·`KISBroker`(주입식 HTTP, env 키, 오프라인 테스트).
- **웹**: FastAPI(`/api/health,strategies,backtest,live/preview`) + React/Vite 대시보드(폼·자산곡선·20검증 스코어카드·오늘 주문 미리보기).
- **운영**: `Makefile`(서버 start/stop/status/logs), `live.py` 실거래 드라이런.

### 2.3 진입점

| 명령 | 용도 |
|------|------|
| `uv run python -m ohmystock.cli` | 텍스트 백테스트 리포트(20검증) |
| `uv run python -m ohmystock.live` | 실거래 드라이런(실주문 없음) |
| `make start` / `make stop` | 웹 백엔드+프론트 실행/정지 |

---

## 3. 아키텍처

```
ohmystock/
  config.py / cli.py / live.py / report.py
  core/
    data/        어댑터(yfinance) + 캐시 + 데이터검증
    strategy/    MACrossover, Momentum
    backtest/    engine + costs + runner + result
    validation/  20개 검증 + _stats/_market 헬퍼
    broker/      Broker·PaperBroker·RiskGuard·rebalance·Alpaca·KIS
server/app.py    FastAPI
web/             React + Vite 대시보드
docs/            STATUS(본 문서) + superpowers/{specs,plans}
```

설계 원칙: 코어는 순수 Python(웹 프레임워크 비의존), 4개 인터페이스(데이터·전략·검증·브로커)가 경계, 어댑터 패턴으로 시장·증권사 확장.

---

## 4. 품질 현황

- **테스트 124개 전부 통과, 전부 오프라인**: 데이터는 주입식 다운로더, 브로커는 httpx MockTransport, 서버는 가짜 어댑터 주입 → 네트워크 없이 실행.
- **멀티에이전트 적대적 검증**: 각 검증·어댑터를 워크플로로 병렬 구현하고 독립 에이전트가 공식·테스트를 재검증. 이 과정에서 잡은 실제 결함 — 계획의 테스트/구현 불일치, yfinance MultiIndex 버그, 부동소수점에 의존한 취약 테스트, 미통합 과최적화 — 모두 수정.
- **실서버 스모크**: CLI 실데이터 리포트, uvicorn 실엔드포인트, 실거래 드라이런 모두 실제 동작 확인.

---

## 5. 향후 구현 계획

우선순위: 🔴 높음 · 🟡 중간 · 🟢 낮음

### 5.1 단기 (실거래로 가기 위한 필수)

| 우선 | 항목 | 내용 |
|------|------|------|
| 🔴 | **실계좌 스케줄링** | 매 거래일 장 마감 후 `rebalance`를 자동 실행하는 스케줄러(cron/APScheduler). 실패·재시도·알림 포함. |
| 🔴 | **페이퍼 트레이딩 상태 영속화** | 현재 PaperBroker는 인메모리. 보유·현금·peak equity를 DB/파일에 저장해 재시작에도 유지. |
| 🔴 | **KIS 어댑터 실연동 검증** | OAuth 토큰 자동 갱신, 실제 응답 스키마 검증, 모의투자 계좌로 end-to-end 확인. |
| 🟡 | **거래 알림** | 체결·리스크 위반 시 Slack/이메일 알림. |
| 🟡 | **데이터 캐시 개선** | 현재 심볼 단위(기간 무시). 기간 인식 + 증분 업데이트로 정확한 구간 백테스트. |

### 5.2 중기 (정확도·기능 강화)

| 우선 | 항목 | 내용 |
|------|------|------|
| 🟡 | **백테스트 엔진 정밀화** | 수익률 기반 → 주식 수량 기반 옵션, 종료 시 미청산 포지션을 거래기반 지표에 반영, 일중 체결가 선택. |
| 🟡 | **단위 일관성(통화)** | 자금(원) vs 미국 가격(USD) 혼용 정리, 환율 처리, 대시보드 통화 표기 통일. |
| 🟡 | **포지션 사이징 고도화** | 켈리(하프켈리)·변동성 타겟팅을 리밸런서에 연결, 손절/익절 룰. |
| 🟡 | **추가 전략** | RSI 평균회귀 등. 전략 레지스트리에 등록만 하면 검증·웹에 자동 노출. |
| 🟢 | **추가 데이터 소스** | Alpaca/Polygon 데이터, 분봉(데이트레이딩 확장 시). |
| 🟢 | **생존편향 실제 처리** | 상장폐지 종목 포함 데이터셋으로 검증 강화(현재는 경고만). |

### 5.3 장기 (운영·확장)

| 우선 | 항목 | 내용 |
|------|------|------|
| 🟢 | **대시보드 고도화** | 전략 비교 뷰, WebSocket 실시간 모니터링, 포트폴리오 추적, 실거래 내역. |
| 🟢 | **인증·멀티유저** | 대시보드 로그인, API 키 보안 저장. |
| 🟢 | **배포** | Docker 컨테이너화, CI/CD(GitHub Actions), 헬스체크. |
| 🟢 | **세금·리포팅** | 양도소득세 계산·연말 신고 자료(한국 거주자 미국주식). |

---

## 6. 알려진 한계 / 단순화

각 항목은 위 향후 계획과 연결된다.

| 한계 | 영향 | 개선 계획 |
|------|------|----------|
| 수익률 기반 백테스트(비중 구동) | 종료 시 미청산 포지션이 거래기반 지표에서 제외 | 5.2 엔진 정밀화 |
| 캐시가 심볼 단위(기간 무시) | 다른 기간 요청 시 캐시 재사용으로 구간 불일치 가능 | 5.1 캐시 개선 |
| 자금 원/가격 USD 혼용 | 표기상 단순화(절대 수치 해석 주의) | 5.2 단위 일관성 |
| PaperBroker 인메모리 | 재시작 시 상태 소실 | 5.1 상태 영속화 |
| KIS 어댑터 미실연동 | 인터페이스만 준비(주입식 테스트만) | 5.1 KIS 실연동 |
| 생존편향 경고만 | 상폐 종목 누락 가능 | 5.2 생존편향 처리 |

---

## 7. 참고 문서

- 단계별 설계(spec): [docs/superpowers/specs/](superpowers/specs/)
- 1단계 구현계획(plan): [docs/superpowers/plans/](superpowers/plans/)
- 실행법·구조: [README.md](../README.md)
