# 페이퍼 트레이딩 상태 영속화 설계

**작성일:** 2026-06-16
**상태:** 설계 확정
**선행:** 1~6단계 완료(브로커 계층·실거래 드라이런·대시보드 존재)

---

## 1. 목표

모의(페이퍼) 계좌를 **정해진 캘린더를 따라 하루씩 전진**시키며 보유·현금·자산곡선·거래내역을 **SQLite에 영속**하고, **CLI와 대시보드**로 운용·조회한다. 프로그램을 껐다 켜도 계좌가 이어진다.

핵심 모델: **캘린더 재생(시뮬 캘린더 스텝)**. 한 스텝 = 커서 날짜를 다음 거래일로 전진해 그 시점 기준 리밸런싱·기록. 완전 결정적이라 오프라인 테스트가 가능하다.

확정된 결정:
- 용도: 연속 모의운용 + 대시보드 연동
- 저장소: SQLite 파일 DB(파이썬 stdlib `sqlite3`), `PaperStore` 인터페이스 뒤에 두어 교체 가능
- 스텝 모델: 캘린더 재생(1급 기능). `run`으로 끝까지 빠르게 전진
- 트리거: CLI(`init/step/run/status`) + 대시보드(조회 + 스텝 버튼)
- 단일 계좌(id=1). 멀티계좌는 향후

---

## 2. 모듈 구조

```
ohmystock/paper/
  account.py        # PaperAccount: 설정+상태 DTO
  store.py          # PaperStore (Protocol) + row DTO
  sqlite_store.py   # SqlitePaperStore (sqlite3 구현)
  engine.py         # step(): 커서 전진 → rebalance → 기록
  service.py        # init/step/run/get_state/get_history (store+engine+adapter 묶음)
  __main__.py       # CLI 진입점
server/app.py        # /api/paper/* 엔드포인트
web/                 # "페이퍼 계좌" 패널
```

원칙: `service`는 `PaperStore` 인터페이스에만 의존. `engine`은 기존 `core/broker/{rebalance,paper,risk}`와 데이터 어댑터를 재사용(신규 로직 최소).

재사용 대상(기존):
- `core/broker/paper.py::PaperBroker(cash)` — `set_prices`, `get_account`, `get_positions`, `submit_order`
- `core/broker/risk.py::RiskGuard(config, peak_equity)` — `update`, `drawdown`, `in_breach`, `filter_orders`
- `core/broker/rebalance.py::rebalance(strategy, bars, broker, risk_guard, config, max_position_weight=None)`
- `report.py::build_strategy(name, params)`
- 데이터 어댑터(`YFinanceAdapter`, 주입식 downloader)

---

## 3. 데이터 모델 (SQLite, 단일 계좌)

```sql
account(
  id INTEGER PRIMARY KEY CHECK (id = 1),
  strategy TEXT, params TEXT,           -- params는 JSON 문자열
  symbols TEXT,                         -- JSON 배열 문자열
  initial_capital REAL,
  start_date TEXT, end_date TEXT,
  cursor_date TEXT,                     -- 마지막으로 처리한 거래일(없으면 NULL)
  cash REAL, peak_equity REAL,
  created_at TEXT, updated_at TEXT
)
positions(symbol TEXT PRIMARY KEY, shares REAL)
snapshots(date TEXT PRIMARY KEY, equity REAL, cash REAL)
trades(id INTEGER PRIMARY KEY AUTOINCREMENT,
       date TEXT, symbol TEXT, side TEXT, notional REAL, price REAL, shares REAL)
```

DB 경로는 설정값(기본 `state/paper.db`), 부모 디렉토리 자동 생성, `.gitignore` 처리.

`init --reset`(또는 `POST /init`): 기존 테이블을 비우고 새 설정으로 재생성(cursor=NULL, cash=initial_capital, peak=initial_capital, positions/snapshots/trades 비움).

---

## 4. PaperStore 인터페이스

```python
class PaperStore(Protocol):
    def initialize(self, account: PaperAccount) -> None: ...      # 스키마 생성 + 계좌 reset
    def load_account(self) -> PaperAccount | None: ...            # 미생성이면 None
    def save_account(self, account: PaperAccount) -> None: ...    # cursor/cash/peak/updated_at
    def load_positions(self) -> dict[str, float]: ...             # symbol -> shares
    def save_positions(self, shares: dict[str, float]) -> None: ...
    def append_snapshot(self, date: str, equity: float, cash: float) -> None: ...
    def append_trades(self, date: str, orders: list[dict]) -> None: ...
    def snapshots(self) -> list[dict]: ...                        # 자산곡선용
    def trades(self) -> list[dict]: ...
```

`PaperAccount`(dataclass): strategy, params(dict), symbols(list[str]), initial_capital, start_date, end_date, cursor_date(str|None), cash, peak_equity.

`SqlitePaperStore(db_path)`가 구현. 각 메서드는 자체 커넥션/트랜잭션. `step` 저장은 service에서 한 번에 묶어 일관성 보장(save_positions+append_snapshot+append_trades+save_account).

---

## 5. 스텝 엔진 (`engine.step`)

입력: account, store, adapter, config. 동작:

1. 종목 일봉을 `start_date..end_date`로 확보(어댑터, 캐시). 종가 패널 = 종목별 종가를 **거래일 합집합(union)** 인덱스로 정렬하고 결측은 직전값으로 채움(ffill). 전체 거래일 캘린더 = 이 패널의 인덱스(`start_date..end_date` 범위로 한정).
2. 다음 거래일 `d` = 캘린더에서 `cursor_date` 다음 날짜(없으면 첫 날짜). `d`가 없거나 `end_date` 초과면 `None` 반환(=완료).
3. `d`까지로 bars 슬라이스. 저장된 `cash`·`positions`로 `PaperBroker` 복원. 가격 = 패널의 `d` 행(모든 종목에 값 보장). 종가 미존재(ffill 전 첫 구간)면 그 종목은 가격 없음으로 두고 매매 대상에서 제외.
4. `strategy = build_strategy(account.strategy, account.params)`. `RiskGuard(config, account.peak_equity)`.
5. `orders = rebalance(strategy, sliced_bars, broker, risk, config)` — 마지막 행(=`d` 목표비중)으로 리밸런싱, 모의체결.
6. `equity = broker.get_account().equity`. peak = max(peak, equity).
7. store에 트랜잭션으로 저장: positions(broker.shares), snapshot(`d`, equity, cash), trades(orders, price=`d` 종가), account(cursor=`d`, cash, peak).
8. 반환: `{date, equity, cash, orders, in_breach, drawdown}`.

`service.run(steps=None, to=None)`: step을 반복(끝/`to`/N회까지). 각 결과 누적 반환.

- **lookahead 안전**: 전략 `shift(1)` → `d` 비중은 `d`까지 데이터로 결정.
- **멱등성**: 항상 다음 날로 전진하므로 중복 체결 없음.
- **단순화(명시)**: 체결은 `d` 종가 기준. 슬리피지·수수료는 추후 백테스트 비용 모델과 통일 가능.

---

## 6. CLI · API · 대시보드

**CLI** `python -m ohmystock.paper`:
- `init --strategy <name> --symbols A,B,C --capital N --start YYYY-MM-DD --end YYYY-MM-DD [--reset]`
- `step` · `run [--steps N | --to YYYY-MM-DD]` · `status`

**API** `/api/paper`:
- `POST /api/paper/init` (body: strategy, params, symbols, capital, start, end) → 생성/리셋 후 state
- `POST /api/paper/step` → 한 스텝, 결과(또는 완료) 반환
- `POST /api/paper/run` (body: {steps?|to?}) → 여러 스텝 결과
- `GET /api/paper/state` → {exists, config, cursor_date, cash, equity, positions:[{symbol,shares,value}], in_breach, drawdown}
- `GET /api/paper/history` → {snapshots:[{date,equity,cash}], trades:[...]}

**대시보드 "페이퍼 계좌" 패널:**
- 설정·현재 자본/현금·보유 표 + 자산곡선(기존 `EquityChart` 재사용) + 거래 로그
- 버튼: 초기화(폼 설정으로 init) · 한 스텝 · 끝까지 빠르게
- 리스크 배지(MDD 위반) 재사용. 금액은 원화 콤마(`format.ts` 재사용)

---

## 7. 에러 처리

- 계좌 미생성: `state`→`{exists:false}`, `step/run`→명확한 에러("먼저 init 필요")
- 커서가 끝/없음: step→완료 신호(무동작)
- 데이터 실패: 어떤 종목·기간인지 명시한 예외
- DB 경로 부모 디렉토리 자동 생성

---

## 8. 테스트 (전부 오프라인)

- `SqlitePaperStore` 왕복(tmp_path DB): initialize→load_account, positions/snapshots/trades 저장·조회, reset 동작
- `engine`/`service`: 주입식 가짜 어댑터(합성 일봉)+임시 DB → init / step(커서 전진·snapshot·trades 기록) / run(끝까지, cursor=end) / equity 변화 / MDD 위반 시 매수 차단 / 미생성 시 에러
- API: TestClient + 임시 DB + 가짜 어댑터 → init/step/run/state/history, 미생성 state
- 프론트: `npm run build` 타입체크 통과

---

## 9. 비범위

- 멀티계좌, 실계좌(Alpaca/KIS) 자동 스케줄링(cron), 슬리피지/수수료 정밀화, 실시간 스트리밍, 인증.
- 과거 재생 외 "오늘 실데이터 기준 전진"은 캘린더 `end_date`를 최근일로 두면 자연히 포함됨.
