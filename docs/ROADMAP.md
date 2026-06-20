# OhMyStock 로드맵

**기준일:** 2026-06-17 · **브랜치:** `main`
**범례:** 우선순위 🔴 높음 · 🟡 중간 · 🟢 낮음 / 진행 `[x]` 완료 · `[ ]` 예정

각 로드맵 피처는 실행 가능한 체크리스트로 분해되어 있다. 새 작업을 시작할 때 해당 피처의 체크리스트를 그대로 작업 단위로 쓴다.

---

## 1. 현재 상태

자동매매 전략을 **20가지 검증**으로 채점하고, 통과한 전략을 **페이퍼/실거래**로 운용하는 시스템. 1~6단계 완료. 테스트는 전부 오프라인(주입식 어댑터·MockTransport·임시 DB).

---

## 2. 완료 ✅

### 핵심 (Phase 1~6)
- [x] **1단계 토대** — 데이터 어댑터·검증, 전략 인터페이스, 백테스트 엔진(거래비용 내장), 성과지표 6종, CLI
- [x] **2단계 G2** — 켈리·파산확률·용량분석 + 모멘텀 전략
- [x] **3단계 G3** — 과최적화·walk-forward·OOS·몬테카를로·스트레스
- [x] **4단계 G4** — 레짐·상관관계·팩터익스포저·Economic Edge (20개 검증 완성)
- [x] **5단계 웹** — FastAPI 백엔드 + React/Vite 대시보드
- [x] **6단계 실거래** — Broker 인터페이스·PaperBroker·RiskGuard·Rebalancer·Alpaca/KIS 어댑터·실거래 드라이런

### 대시보드 UX
- [x] 20검증 스코어카드(상태색 카드 그리드)
- [x] 개념 설명 `?` 버튼 + 모달(지표·검증·전략·파라미터·기간 25+개)
- [x] 종목 검색·자동완성·최근 히스토리 피커(코드+이름)
- [x] 초기 자본 통화 표시·콤마·한글 읽기(예: 5억원)

### 운영
- [x] `Makefile` (서버 start/stop/status/logs)
- [x] CLI 리포트 / 실거래 드라이런(`live.py`)

### 페이퍼 트레이딩 상태 영속화 ✅ ([spec](superpowers/specs/2026-06-16-paper-persistence-design.md) · [plan](superpowers/plans/2026-06-17-paper-persistence.md))
캘린더 재생 + SQLite 영속 + CLI·대시보드. 모의 계좌를 하루씩 전진시키며 보유·현금·자산곡선을 저장(껐다 켜도 이어짐).
- [x] `PaperAccount` DTO + `PaperStore` 인터페이스 + `SqlitePaperStore`
- [x] 스텝 엔진 (캘린더 커서·rebalance·트랜잭션 기록) + `PaperService`(init/step/run/state/history)
- [x] CLI (`python -m ohmystock.paper` init/step/run/status)
- [x] `/api/paper/*` 엔드포인트 + 대시보드 "페이퍼 계좌" 패널
- [x] 실데이터 스모크(1006스텝 무크래시) + main 머지

---

## 3. 진행 중 🔄

(없음)

---

## 4. 단기 로드맵 (실거래로 가기 위한 필수)

### 🔴 실계좌 스케줄링
매 거래일 장 마감 후 리밸런싱을 자동 실행.
- [x] 거래일·장시간 캘린더 판정(개장일/휴장 처리) — `MarketCalendar`(XNYS, 반장일·tz) + `/api/calendar` + 대시보드 달력 패널 ([spec](superpowers/specs/2026-06-17-market-calendar-design.md) · [plan](superpowers/plans/2026-06-17-market-calendar.md))
- [x] 스케줄러 진입점(cron 래퍼) — `python -m ohmystock.scheduler run-once`, 멱등 `compute_target_date`/`run_once` ([spec](superpowers/specs/2026-06-17-scheduler-entrypoint-design.md) · [plan](superpowers/plans/2026-06-17-scheduler-entrypoint.md))
- [x] 매 거래일 1회 `rebalance` 자동 실행 잡 — `run_once`가 due일 때 페이퍼 계좌를 최신까지 전진(리밸런싱)
- [x] 실패 재시도·백오프 + 실행 로그/상태 기록 — `run_scheduled`(지수 백오프) + `SqliteSchedulerStore` + CLI `history`/`last-run` + `/api/scheduler/runs` + 대시보드 패널 ([spec](superpowers/specs/2026-06-19-scheduler-retry-log-design.md) · [plan](superpowers/plans/2026-06-19-scheduler-retry-log.md))
- [x] 드라이런 ↔ 실계좌 모드 토글(API 키 가드) — `broker_select`(resolve_mode + build_broker 가드) + `live_execute`(dry-run 시뮬 / live 실주문) + CLI `--mode`/`OHMYSTOCK_MODE` ([spec](superpowers/specs/2026-06-19-dryrun-live-toggle-design.md) · [plan](superpowers/plans/2026-06-19-dryrun-live-toggle.md))
- [x] 브로커 선택 배선(alpaca/toss/kis) + **실제-돈 동의 게이트** — `resolve_broker`(CLI `--broker`>env>alpaca) + `build_broker` 분기(브로커별 키 가드) + `OHMYSTOCK_ALLOW_REAL_MONEY` 3단계 안전(TOSS·Alpaca 라이브·KIS 실전은 명시 동의 필수) ([spec](superpowers/specs/2026-06-20-broker-select-wiring-design.md) · [plan](superpowers/plans/2026-06-20-broker-select-wiring.md))
- [ ] (선택) APScheduler 상주 데몬
- [ ] `/schedule`(cloud agent) 또는 시스템 cron 연동 문서화

### 🟢 토스증권(TOSS Invest) 어댑터
토스증권 Open API(`https://openapi.tossinvest.com`)를 Broker 프로토콜로 구현. **샌드박스 없음 = 모든 주문 실거래** → 실(live) 브로커 취급, 에이전트는 오프라인 검증만.
- [x] OAuth2 client_credentials 토큰 자동 갱신(`_ensure_token`, 만료 추적)
- [x] 실 응답 스키마 + envelope(`{result}`) 파싱 — 계좌/보유/매수여력/시세
- [x] notional → 정수 수량 변환(현재가 `floor`, 1주 미만·0가·미상장 안전 처리) + `clientOrderId`
- [x] `get_account`/`get_positions`/`submit_order`(시장가) — `TossBroker`, 오프라인 MockTransport 19 테스트
- [x] 사용자용 실 스모크 스크립트(`scripts/toss_smoke.py`, 실주문 이중 게이트) ([spec](superpowers/specs/2026-06-20-toss-broker-integration-design.md) · [plan](superpowers/plans/2026-06-20-toss-broker-integration.md))
- [x] **실 API 읽기 검증** — 토큰·계좌(equity)·보유 조회 실 계좌로 확인. 다통화(KR+US) 계좌 대응: `get_positions` 통화 슬리브 필터(positions 합 ≈ equity 검증). IP 허용목록 필요(Cloudflare 403)
- [x] broker_select/live 배선(`--broker toss`, 실제-돈 동의 게이트)
- [ ] (후속) KR 종목 운용(`currency="krw"`), 정정/취소, 실주문 체결 검증(평일 장중)

### 🟢 KIS 어댑터 실연동
인터페이스만 있던 `KISBroker`를 프로덕션급으로 재작성. **모의투자(paper) 기본**, `paper=False`만 실전. ([spec](superpowers/specs/2026-06-20-kis-real-integration-design.md) · [plan](superpowers/plans/2026-06-20-kis-real-integration.md))
- [x] OAuth 토큰 발급·만료 자동 갱신(`_ensure_token`, `access_token_token_expired`/`expires_in`)
- [x] 실 응답 스키마 — 잔고(output1/output2 + 쿼리 파라미터)·현재가(`stck_prpr`)·주문(`rt_cd` 판정)
- [x] 주문 보안 필드 hashkey 처리(옵션, 기본 off)
- [x] notional → 정수 수량 변환(현재가 `floor`, 1주 미만·0가 안전 처리) + 모의/실전 tr_id 분기
- [x] 사용자용 모의투자 스모크 스크립트(`scripts/kis_smoke.py`, 실주문 이중 게이트) — 오프라인 MockTransport 18 테스트
- [x] **실 모의투자 검증** — 토큰·잔고(1천만원)·보유·주문 경로 실 API 확인(주말 `모의투자 영업일이 아닙니다` 거부 응답까지 처리). 토큰 캐시(`state/`, 분당 발급제한 회피) + 초당 제한(`EGW00201`) 재시도(`_send`, 실행 전 거부라 주문도 안전)
- [x] broker_select/live 배선(`--broker kis`, 모의 기본·실전은 동의 게이트)
- [ ] (후속) 실주문 체결 검증(평일 장중), 실전(`paper=False`) 운용

### 🟡 거래 알림
- [ ] `Notifier` 인터페이스
- [ ] Slack 웹훅 구현
- [ ] 이메일(SMTP) 구현
- [ ] 트리거 연결(체결·MDD 위반·에러)
- [ ] 설정(채널·임계값)

### 🟡 데이터 캐시 개선
현재 캐시는 심볼 단위(기간 무시).
- [ ] 캐시 키/메타에 기간 포함
- [ ] 증분 다운로드(누락 구간만)
- [ ] 무효화·갱신 정책
- [ ] 기존 캐시 마이그레이션

---

## 5. 중기 로드맵 (정확도·기능 강화)

### 🟡 백테스트 엔진 정밀화
- [ ] 주식 수량 기반 회계 옵션(현재 수익률·비중 기반)
- [ ] 종료 시 미청산 포지션을 거래기반 지표(Profit Factor·Recovery)에 반영
- [ ] 체결 시점 선택(시가/종가)
- [ ] 기존 테스트 동등성 유지

### 🟡 단위 일관성(통화)
- [ ] 계좌 통화 vs 가격 통화 개념 명시
- [ ] 환율(USD↔KRW) 처리 옵션
- [ ] 대시보드 통화 표기 통일(현재 일부 $/원 혼용)
- [ ] 리포트·지표 통화 라벨

### 🟡 포지션 사이징 고도화
- [ ] 켈리(하프켈리) 사이저를 리밸런서에 연결
- [ ] 변동성 타겟팅 사이저
- [ ] 손절/익절 룰
- [ ] 사이징 전략 선택 옵션

### 🟡 추가 전략 (RSI 평균회귀 등)
- [ ] `RSIMeanReversion` 전략(lookahead-safe)
- [ ] 전략 레지스트리 등록(검증·웹 자동 노출)
- [ ] 과최적화 그리드 추가
- [ ] 단위 테스트

### 🟢 추가 데이터 소스
- [ ] Alpaca/Polygon 데이터 어댑터
- [ ] 분봉 지원(데이트레이딩 확장)
- [ ] 어댑터 선택 설정

### 🟢 생존편향 실제 처리
- [ ] 상장폐지 포함 데이터셋 확보
- [ ] 유니버스 구성 시점 기준 적용
- [ ] 검증 경고 → 실제 반영

---

## 6. 장기 로드맵 (운영·확장)

### 🟡 대시보드 개선 (시장 개요·실계좌·캘린더) ([spec](superpowers/specs/2026-06-20-dashboard-improvements-design.md))
**v1** (외부 키 불필요):
- [ ] 시장 개요 패널 — 주요 지수·환율(yfinance: `^IXIC`·`^GSPC`·`^DJI`·`^VIX`·`^KS11`·`USDKRW=X`·`NQ=F`) 카드(값·등락·미니 스파크라인) + 국내/해외 장 상태(XNYS/XKRX) + 계산형 배지(52주 고저 근접·고변동성). 상승=빨강/하락=파랑
- [ ] 실 계좌 보유에 종목명 표시(KIS `prdt_name` / TOSS `name`, `get_holdings`)
- [ ] USD 평가금액 원화 환산 참고(TOSS `exchange-rate`)
- [ ] 캘린더 거래일/휴장 색 구분 강화(CSS)

**v2** (키 필요):
- [ ] 뉴스 레이어 — US(yfinance/Finnhub) · KR(네이버 검색 API) 최근 헤드라인 → (선택) LLM 한글 요약 태그(Anthropic 키). 시장 개요 배지를 실제 뉴스 맥락으로
- [ ] 인트라데이 실시간 지수(현재 v1은 EOD 종가)

### 🟢 대시보드 고도화
- [ ] 전략 비교 뷰(다중 결과 나란히)
- [ ] WebSocket 실시간 모니터
- [ ] 포트폴리오·실거래 내역
- [ ] 결과 저장·불러오기

### 🟢 인증·멀티유저
- [ ] 로그인(세션/JWT)
- [ ] 멀티 계좌(스키마에 account_id 확장)
- [ ] API 키 보안 저장(암호화)

### 🟢 배포
- [ ] Dockerfile(백엔드) + 프론트 멀티스테이지 빌드
- [ ] docker-compose
- [ ] GitHub Actions CI(테스트·빌드)
- [ ] 헬스체크·구조적 로깅

### 🟢 세금·리포팅
- [ ] 거래내역 기반 양도손익 계산
- [ ] 250만원 공제·22% 적용
- [ ] 연말 신고용 내보내기(CSV)

---

## 7. 알려진 한계 ↔ 로드맵 연결

| 한계 | 영향 | 대응 로드맵 |
|------|------|------------|
| PaperBroker 인메모리 | 재시작 시 상태 소실 | §3 상태 영속화(진행 중) |
| 수익률·비중 기반 백테스트 | 종료 시 미청산 포지션 지표 누락 | §5 엔진 정밀화 |
| 캐시 심볼 단위(기간 무시) | 구간 불일치 가능 | §4 캐시 개선 |
| 자금 원 / 가격 USD 혼용 | 절대 수치 해석 주의 | §5 단위 일관성 |
| KIS 어댑터 미실연동 | 주입식 테스트만 | §4 KIS 실연동 |
| 생존편향 경고만 | 상폐 종목 누락 가능 | §5 생존편향 처리 |

---

## 8. 참고 문서

- 단계별 설계(spec): [docs/superpowers/specs/](superpowers/specs/)
- 구현 계획(plan): [docs/superpowers/plans/](superpowers/plans/)
- 실행법·구조: [README.md](../README.md)
