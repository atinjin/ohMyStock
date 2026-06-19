# OhMyStock

자동매매 전략을 **20가지 검증**으로 채점하고, 통과한 전략을 **페이퍼/실거래**로 운용하는 시스템.

- 시장: 어댑터 구조. 1차 미국(데이터 yfinance / 실거래 Alpaca 페이퍼), 한국(KIS) 확장 준비됨.
- 매매 주기: 일봉 기반 스윙. 유니버스: 5~20 종목 바스켓.
- 코어는 순수 Python. 웹은 FastAPI + React.

## 20가지 검증

| # | 항목 | 위치 |
|---|------|------|
| ① | 데이터 검증 | `core/data/validation.py` |
| ⑦ | 거래비용(수수료·슬리피지·스프레드) | `core/backtest/costs.py` (엔진 내장) |
| ⑩⑪⑫⑬⑭⑮ | MDD·Sharpe·Sortino·Calmar·ProfitFactor·Recovery | `core/validation/metrics.py` |
| ⑨ | 켈리공식 | `core/validation/kelly.py` |
| ⑯ | 파산확률 | `core/validation/ruin.py` |
| ⑧ | 용량분석 | `core/validation/capacity.py` |
| ④ | out-of-sample | `core/validation/out_of_sample.py` |
| ③ | walk-forward | `core/validation/walk_forward.py` |
| ⑤ | 몬테카를로 | `core/validation/monte_carlo.py` |
| ⑥ | 스트레스 테스트 | `core/validation/stress.py` |
| ② | 과최적화 | `core/validation/overfitting.py` |
| ⑰ | 레짐 테스트 | `core/validation/regime.py` |
| ⑱ | 상관관계 | `core/validation/correlation.py` |
| ⑲ | 팩터 익스포저 | `core/validation/factor_exposure.py` |
| ⑳ | Economic Edge | `core/validation/economic_edge.py` |

## 설치

```bash
uv sync                 # Python 의존성 (Python 3.11)
cd web && npm install   # 프론트엔드 의존성
```

## 실행

### 1) CLI 백테스트 리포트 (가장 빠름)
```bash
uv run python -m ohmystock.cli
```
5개 종목에 MA교차/모멘텀을 돌려 자산곡선 + 18개 검증 항목을 텍스트로 출력.

### 2) 실거래 드라이런 (페이퍼 — 실주문 없음)
```bash
uv run python -m ohmystock.live
```
오늘자 목표 리밸런싱 주문을 PaperBroker로 미리보기.

### 3) 웹 대시보드
```bash
# 터미널 1: 백엔드
uv run uvicorn server.app:app --port 8000
# 터미널 2: 프론트엔드
cd web && npm run dev    # http://localhost:5173 (개발 프록시 /api -> :8000)
```
전략·종목·기간을 골라 백테스트 → 자산곡선·지표·20검증 스코어카드 + "오늘 주문 미리보기" 패널.

## 테스트

```bash
uv run pytest -q          # 124개 (네트워크 불필요 — 모두 주입식/오프라인)
cd web && npm run build   # 프론트 타입체크 + 빌드
```

## 실거래 연동 (실주문)

실주문은 **API 키를 넣어야만** 동작한다(기본은 페이퍼/드라이런).
- 미국: 환경변수 `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` → `AlpacaBroker` (기본 base_url은 페이퍼).
- 한국: `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT_NO` → `KISBroker`.

### 토스증권(TOSS Invest) 어댑터

`ohmystock/core/broker/toss.py::TossBroker` 는 토스증권 Open API(`https://openapi.tossinvest.com`)를
Broker 프로토콜로 구현한다. OAuth client_credentials 토큰을 자동 갱신하고,
주문은 현재가로 `floor(notional/lastPrice)` 정수 수량을 계산해 시장가로 제출한다.

**주의: TOSS는 모의투자(샌드박스)가 없어 모든 주문이 실제 체결된다.** 에이전트/자동화는
실주문을 내지 않으며, 실계좌 검증은 사용자가 직접 실행한다:

```bash
export TOSS_CLIENT_ID=...  TOSS_CLIENT_SECRET=...
uv run python scripts/toss_smoke.py            # 토큰+계좌+보유 확인(안전)
uv run python scripts/toss_smoke.py --order AAPL 50 --i-understand-real-money  # 소량 실주문
```

리스크 가드(`RiskGuard`)가 MDD 한도(-20%, 설정값)를 넘으면 신규 진입을 차단한다.

## 구조

```
ohmystock/
  config.py                 설정(자금·비용·MDD·연환산)
  cli.py / live.py          텍스트 리포트 / 실거래 드라이런
  report.py                 구조화 리포트(API·CLI 공용)
  core/
    data/                   어댑터(yfinance) + 캐시 + 데이터검증
    strategy/               MACrossover, Momentum
    backtest/               엔진 + 거래비용 + 러너
    validation/             20개 검증 + 통계 헬퍼
    broker/                 Broker 인터페이스 + PaperBroker + RiskGuard + Rebalancer + Alpaca/KIS
server/app.py               FastAPI (/api/health, strategies, backtest, live/preview)
web/                        React + Vite 대시보드
docs/superpowers/           단계별 설계(spec)·구현계획(plan)
```

## 알려진 단순화 (향후 개선 여지)

- 백테스트는 수익률 기반(비중 구동) — 소수점 주식 일봉 스윙에 적합. 종료 시 미청산 포지션은 거래기반 지표에서 제외.
- 데이터 캐시는 심볼 단위(기간 무시) — 재다운로드 방지용. 자금 단위는 원, 미국 가격은 USD로 혼용(표기상 단순화).
- 과최적화(②)는 파라미터 그리드가 필요해 표준 리포트와 별도 도구로 제공.
