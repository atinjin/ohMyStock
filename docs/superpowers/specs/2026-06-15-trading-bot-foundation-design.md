# OhMyStock — 자동매매 전략 검증·실거래 시스템 설계

**작성일:** 2026-06-15
**상태:** 1단계(토대) 설계 확정
**문서 범위:** 전체 비전 요약 + 1단계(토대) 상세 설계

---

## 1. 전체 비전

"진짜 자동매매 트레이더가 통과해야 하는 20가지 검증"을 자동으로 수행하고, 통과한 전략을 실거래(페이퍼 → 실계좌)로 운용하는 시스템.

핵심 통찰: 20개 항목은 트레이딩 봇 자체가 아니라 **전략의 견고함을 채점하는 검증 프레임워크**다. 이를 돌리려면 그 아래에 데이터·전략·백테스트 엔진이 먼저 깔려야 한다.

### 확정된 제품 결정

| 항목 | 결정 |
|------|------|
| 성격 | 검증 프레임워크 + 실거래 봇 (둘 다) |
| 시장 | 어댑터 구조. 1차 미국(데이터 yfinance / 실거래 Alpaca 페이퍼), 이후 한국(KIS) 확장 |
| 매매 주기 | 일봉 기반 스윙 (하루 1회 판단, 며칠~몇 주 보유) |
| 전략 | 전략 독립적 프레임워크 + 기본 전략(MA교차·모멘텀) 탑재 |
| 유니버스 | 5~20 종목 바스켓 |
| 자금 | ~500만원(약 $3,500). 소수점 주식(Alpaca fractional) 사용 |
| 리스크 | MDD 한도 -20% (설정값, 조정 가능) |
| 결과 출력 | 웹 대시보드 (전략 비교 + 실거래 모니터링) |
| 기술 스택 | Python(FastAPI) 백엔드 + React/Next.js 프론트엔드. 코어는 순수 Python |

### 20개 테스트 그룹핑

| 그룹 | 테스트 | 비고 |
|------|--------|------|
| G0. 데이터 품질 | ①데이터검증 | 토대 |
| G1. 성과지표 | ⑩MDD ⑪샤프 ⑫소르티노 ⑬칼마 ⑭수익팩터 ⑮Recovery | 결과만 있으면 즉시 계산 |
| G2. 자금·리스크 | ⑨켈리 ⑯파산확률 ⑧용량분석 | 포지션 사이징·생존 |
| G3. 견고성 검증 | ②과최적화 ③walk-forward ④out-of-sample ⑤몬테카를로 ⑥스트레스 | 백테스트 재실행 필요, 핵심 |
| G4. 시장구조 | ⑰레짐 ⑱상관관계 ⑲팩터익스포저 ⑳Economic Edge | 다종목·국면 분석 |

⑦거래비용은 테스트가 아니라 백테스트 엔진에 내장되는 모델이다.

### 빌드 단계 (각 단계 = 독립 spec → plan → 구현)

| 단계 | 내용 | 완료 시 가치 |
|------|------|------------|
| **1. 토대** | 데이터 어댑터+①데이터검증 / 전략 인터페이스+MA교차 / 백테스트 엔진(⑦비용 내장) / G1 지표 6개 / CLI 리포트 | 동작하는 최소 검증 시스템 |
| 2. 자금·리스크 | G2(⑨⑯⑧) + 모멘텀 전략 | 포지션 사이징·생존 판정 |
| 3. 견고성 | G3(②③④⑤⑥) | 과최적화 걸러내는 핵심 검증 |
| 4. 시장구조 | G4(⑰⑱⑲⑳) | 국면·팩터 분석 |
| 5. 웹 | FastAPI API + React 대시보드 | 브라우저 시각화·비교 |
| 6. 실거래 | Alpaca 페이퍼 + 리스크 가드(MDD) + 모니터 | 실제 매매 |
| 이후 | KIS 어댑터 | 한국 주식 확장 |

본 문서는 **1단계만** 상세 설계한다. 이후 단계는 각자 별도 spec으로 다룬다.

---

## 2. 1단계(토대) 상세 설계

### 2.1 목표 / 완료 기준

`cli.py`에 5개 종목과 MA교차 전략을 넣고 실행하면:
1. 일봉 데이터를 받아와 캐시한다
2. 데이터 검증(①)을 통과(또는 경고 출력)한다
3. 백테스트를 실행해 자산곡선·거래내역을 만든다(⑦거래비용 반영)
4. G1 성과지표 6개(⑩~⑮)를 계산한다
5. 텍스트 리포트로 출력한다

### 2.2 모듈 구조

```
ohmystock/
├─ core/
│  ├─ data/
│  │  ├─ adapter.py          # MarketDataAdapter 인터페이스
│  │  ├─ yfinance_adapter.py # 미국 일봉
│  │  ├─ cache.py            # parquet 로컬 캐시
│  │  └─ validation.py       # ①데이터검증
│  ├─ strategy/
│  │  ├─ base.py             # Strategy 인터페이스
│  │  └─ ma_crossover.py     # MA 교차 전략
│  ├─ backtest/
│  │  ├─ engine.py           # 시그널→체결→자산곡선
│  │  ├─ costs.py            # ⑦거래비용
│  │  └─ result.py           # BacktestResult
│  └─ validation/
│     ├─ base.py             # Validator 인터페이스
│     └─ metrics.py          # G1 지표 6개
├─ cli.py
├─ config.py
└─ tests/
```

원칙: 코어는 순수 Python(FastAPI/React 비의존). 4개 인터페이스가 경계가 되어 각 부분을 독립 테스트한다.

### 2.3 인터페이스

**MarketDataAdapter** — 시장 교체 지점
```python
class MarketDataAdapter(Protocol):
    def get_daily_bars(self, symbols: list[str],
                       start: date, end: date) -> dict[str, DataFrame]:
        """심볼별 일봉 OHLCV. 컬럼 open/high/low/close/volume, index=date(거래일)."""
```

**Strategy** — 전략 교체 지점
```python
class Strategy(Protocol):
    def generate_signals(self, bars: dict[str, DataFrame]) -> DataFrame:
        """일자×심볼 목표 비중 행렬. 값 0=미보유, 0.1=자산의 10% 보유.
        행 합계는 1.0 이하(현금 허용). 미래 데이터 참조 금지(lookahead 방지)."""
```

**BacktestResult** — 모든 검증의 공통 입력
```python
@dataclass
class BacktestResult:
    equity_curve: Series   # 일별 총자산
    trades: DataFrame      # 컬럼: symbol, entry_date, exit_date, qty, pnl, cost
    positions: DataFrame   # 일별 심볼별 보유 비중
    returns: Series        # 일별 수익률 (equity_curve.pct_change())
```

**Validator** — 20개 테스트 공통 형태
```python
class Validator(Protocol):
    name: str
    def evaluate(self, result: BacktestResult) -> ValidationReport: ...

@dataclass
class ValidationReport:
    name: str
    value: float
    passed: bool
    threshold: float | None
    message: str
```

### 2.4 백테스트 엔진 (engine.py)

- 입력: `bars`(데이터), `signals`(목표 비중 행렬), `config`(초기자금·비용)
- 매일: 전일 종가 시그널 → 당일 시가/종가로 리밸런싱 체결(설정으로 선택). 기본은 당일 시가 체결로 lookahead 회피
- 목표 비중과 현재 비중의 차이만큼 매수/매도 주문 생성 → 거래비용 차감 후 체결
- 출력: `BacktestResult`

### 2.5 거래비용 모델 (costs.py, ⑦)

| 요소 | 모델 | 기본값 |
|------|------|--------|
| 수수료 | 체결금액 × commission_rate | 미국 0%, KIS는 어댑터 설정 |
| 슬리피지 | 체결가 = 기준가 × (1 ± slippage_bps) | 5 bps |
| 스프레드 | 매수=ask, 매도=bid 근사(일봉 간이 모델) | 설정값 |
| (한국 확장) 거래세 | 매도금액 × tax_rate | KIS 어댑터에서 0.18% |

전부 `config.py`에서 조정 가능.

### 2.6 데이터 검증 (validation.py, ①)

탐지 항목: 결측 거래일·중복 인덱스·이상치(비현실적 급등락)·0/음수 가격·장기 거래정지(volume 0) 구간. 생존편향 가능성(상장폐지 종목 누락)은 경고 플래그로 표시. 치명적 문제는 백테스트 진행 전에 막고, 경미한 문제는 경고만 한다.

### 2.7 G1 성과지표 6개 (metrics.py, ⑩~⑮)

| 지표 | 공식 | 판정 기준(기본값) |
|------|------|------|
| ⑩ MDD | 누적 고점 대비 최대 낙폭 | < 20% 경고선 |
| ⑪ Sharpe | (연환산수익 − 무위험수익) / 연환산변동성 | > 1 양호 |
| ⑫ Sortino | (연환산수익 − 무위험) / 하방변동성 | > 1.5 양호 |
| ⑬ Calmar | 연환산수익 / MDD | > 1 양호 |
| ⑭ Profit Factor | 총이익 / 총손실(절대값) | > 1.5 양호, > 2 우수 |
| ⑮ Recovery Factor | 순이익 / MDD | 높을수록 좋음 |

무위험수익률·연환산 거래일수(252)는 `config.py` 설정값.

### 2.8 설정 (config.py)

초기자금, MDD 한도(-20%), 무위험수익률, 거래비용 파라미터(수수료·슬리피지·스프레드), 연환산 거래일수, 캐시 경로.

### 2.9 에러 처리

- 데이터 없음/네트워크 실패: 캐시 우선 사용, 실패 시 어떤 심볼·기간인지 명시한 예외
- 시그널 형식 오류(비중 합 > 1, NaN): 검증 후 명확한 예외
- 빈 거래내역(거래 0건): 지표는 0/NaN 대신 "거래 없음" 메시지

### 2.10 테스트 전략 (TDD)

- 각 지표는 손으로 계산한 기대값을 둔 단위 테스트를 먼저 작성 (예: 알려진 수익률 시퀀스 → Sharpe = 기댓값)
- 백테스트 엔진은 단순 시나리오(1종목, 비중 0↔1)로 자산곡선·비용을 검증
- 데이터 어댑터는 캐시된 픽스처로 네트워크 없이 테스트
- 데이터 검증은 결측·이상치를 심은 샘플로 탐지 확인

---

## 3. 비범위 (1단계에서 하지 않는 것)

- G2/G3/G4 검증(자금·견고성·시장구조) — 2~4단계
- FastAPI·React·실거래 — 5~6단계
- KIS 어댑터 — 이후
- 모멘텀·RSI 전략 — 2단계에서 추가(1단계는 MA교차만)
