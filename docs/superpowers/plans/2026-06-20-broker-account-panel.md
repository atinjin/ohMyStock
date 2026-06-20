# 실 계좌 현황 패널 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 대시보드에 KIS/TOSS 실 계좌(equity·cash·보유)를 읽기 전용으로 표시하는 패널을 추가한다.

**Architecture:** `server/app.py`에 읽기 전용 `GET /api/broker/account` 엔드포인트 + 브로커 인스턴스 캐시(`app.state.brokers`)를 추가하고, `web/`에 `BrokerAccountPanel`을 추가한다. 서버는 `get_account`/`get_positions`만 호출(주문 없음)하고, 브로커 인스턴스를 캐시해 토큰을 재사용한다.

**Tech Stack:** Python 3.11, FastAPI, pytest, React/Vite/TypeScript, uv.

## Global Constraints

- 백엔드 테스트: `uv run pytest <path> -q`. 프론트 빌드: `cd web && npm run build`.
- 엔드포인트 `GET /api/broker/account?broker={kis|toss}` → `{broker, mode, equity, cash, positions: [{symbol, value}]}`. 잘못된 broker → 400, 브로커 예외 → 502(detail에 메시지).
- `mode`: KIS는 `broker.paper` 기준 `"paper"`/`"live"`, TOSS는 `"live"`(paper 속성 없음 → False).
- **읽기 전용**: get_account/get_positions만 호출. 주문 엔드포인트 없음.
- 브로커 캐시: `app.state.brokers[name]` 재사용(폴링마다 토큰 재발급 안 함). 생성은 `app.state.broker_factory(name)`(테스트는 가짜 주입).
- 읽기 전용 팩토리는 `build_broker`(주문·실제-돈 게이트)와 **분리**. KIS는 `paper=env OHMYSTOCK_KIS_PAPER != 0` 기본 모의, TOSS는 `TossBroker()`.
- 통화: KIS=KRW(원), TOSS=USD. 프론트가 브로커별로 포맷.
- 폴링 30초 + 수동 새로고침, 선택된 브로커만. 각 태스크 끝 커밋(atinjin).

---

### Task 1: 백엔드 — 읽기 전용 계좌 엔드포인트 + 브로커 캐시

**Files:**
- Modify: `server/app.py` (import 추가, `_read_only_broker`/`_load_dotenv` 추가, `create_app`에 `broker_factory` 파라미터 + `app.state`, 엔드포인트 추가)
- Test: `tests/test_server.py` (테스트 추가)

**Interfaces:**
- Produces: `GET /api/broker/account?broker={kis|toss}` → JSON; `create_app(adapter=None, paper_db=..., broker_factory=None)`; `_read_only_broker(name, env=None) -> Broker`.
- Consumes: `KISBroker(paper=...)`, `TossBroker()`, `ohmystock.core.broker.base.Account`.

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_server.py` 끝에 추가:
```python
def _client_with_broker(tmp_path, broker_factory):
    adapter = YFinanceAdapter(cache=ParquetCache(tmp_path), downloader=_fake_dl)
    return TestClient(create_app(adapter=adapter, broker_factory=broker_factory))


class _FakeBroker:
    paper = True

    def get_account(self):
        from ohmystock.core.broker.base import Account
        return Account(equity=10000000.0, cash=9000000.0)

    def get_positions(self):
        return {"005930": 354000.0}


def test_broker_account_ok(tmp_path):
    made = {"n": 0}

    def factory(name):
        made["n"] += 1
        return _FakeBroker()

    client = _client_with_broker(tmp_path, factory)
    resp = client.get("/api/broker/account?broker=kis")
    assert resp.status_code == 200
    body = resp.json()
    assert body["broker"] == "kis"
    assert body["mode"] == "paper"
    assert body["equity"] == 10000000.0
    assert body["cash"] == 9000000.0
    assert body["positions"] == [{"symbol": "005930", "value": 354000.0}]
    # 캐시: 같은 브로커 재조회 시 factory 는 1회만
    client.get("/api/broker/account?broker=kis")
    assert made["n"] == 1


def test_broker_account_invalid_broker(tmp_path):
    client = _client_with_broker(tmp_path, lambda name: _FakeBroker())
    resp = client.get("/api/broker/account?broker=ibkr")
    assert resp.status_code == 400


def test_broker_account_error_returns_502(tmp_path):
    class _BoomBroker:
        paper = False

        def get_account(self):
            raise RuntimeError("키 없음")

        def get_positions(self):
            return {}

    client = _client_with_broker(tmp_path, lambda name: _BoomBroker())
    resp = client.get("/api/broker/account?broker=toss")
    assert resp.status_code == 502
    assert "키 없음" in resp.json()["detail"]
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_server.py -q`
Expected: FAIL (`create_app() got an unexpected keyword argument 'broker_factory'` / 404).

- [ ] **Step 3: server/app.py 구현**

`server/app.py` 상단 import에 추가:
```python
import os

from ohmystock.core.broker.kis import KISBroker
from ohmystock.core.broker.toss import TossBroker
```
파일 상단(모듈 수준, `create_app` 위)에 헬퍼 추가:
```python
def _load_dotenv():
    """현재 디렉터리 .env 를 환경변수로 로드(있으면). python-dotenv 없으면 무시."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def _read_only_broker(name: str, env=None):
    """읽기 전용 브로커 생성(주문·실제-돈 게이트 없음). 키는 env 폴백."""
    _load_dotenv()
    env = os.environ if env is None else env
    if name == "kis":
        paper = env.get("OHMYSTOCK_KIS_PAPER", "1").strip().lower() not in ("0", "false", "no")
        return KISBroker(paper=paper)
    if name == "toss":
        return TossBroker()
    raise ValueError(f"알 수 없는 브로커: {name}")
```
`create_app` 시그니처와 `app.state` 초기화를 수정:
```python
def create_app(adapter=None, paper_db="state/paper.db", broker_factory=None) -> FastAPI:
    if adapter is None:
        adapter = YFinanceAdapter(cache=ParquetCache(".cache"))

    app = FastAPI(title="OhMyStock API")
    app.state.adapter = adapter
    app.state.paper_db = paper_db
    app.state.calendar = None  # lazy: /api/calendar 첫 요청 때 생성
    app.state.broker_factory = broker_factory or _read_only_broker
    app.state.brokers = {}
```
`return app` 직전(다른 `@app.get` 들과 함께)에 엔드포인트 추가:
```python
    @app.get("/api/broker/account")
    def broker_account(broker: str):
        """선택 브로커의 실 계좌(읽기 전용): equity/cash + 보유."""
        if broker not in ("kis", "toss"):
            raise HTTPException(status_code=400, detail="broker는 kis|toss 이어야 합니다")
        try:
            b = app.state.brokers.get(broker)
            if b is None:
                b = app.state.broker_factory(broker)
                app.state.brokers[broker] = b
            acct = b.get_account()
            positions = b.get_positions()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        mode = "paper" if getattr(b, "paper", False) else "live"
        return {
            "broker": broker,
            "mode": mode,
            "equity": acct.equity,
            "cash": acct.cash,
            "positions": [{"symbol": s, "value": v} for s, v in positions.items()],
        }
```

- [ ] **Step 4: 통과 확인 + 전체 스위트**

Run: `uv run pytest tests/test_server.py -q`
Expected: PASS (신규 3개 포함 그린).
Run: `uv run pytest -q`
Expected: PASS (전 프로젝트 그린).

- [ ] **Step 5: 커밋**

```bash
git add server/app.py tests/test_server.py
git commit -m "feat(server): read-only GET /api/broker/account (KIS/TOSS, cached brokers)"
```

---

### Task 2: 프론트 — api 클라이언트 + BrokerAccountPanel + 배치

**Files:**
- Modify: `web/src/api.ts` (타입 + `getBrokerAccount` 추가)
- Create: `web/src/components/BrokerAccountPanel.tsx`
- Modify: `web/src/App.tsx` (import + 패널 배치)

**Interfaces:**
- Consumes: Task 1의 `GET /api/broker/account?broker=`.
- Produces: `getBrokerAccount(broker) -> Promise<BrokerAccount>`; `<BrokerAccountPanel />`.

- [ ] **Step 1: api.ts 클라이언트 추가**

`web/src/api.ts` 끝에 추가:
```typescript
// 실 계좌 현황 (읽기 전용)

export interface BrokerAccount {
  broker: string
  mode: string
  equity: number
  cash: number
  positions: { symbol: string; value: number }[]
}

export async function getBrokerAccount(
  broker: 'kis' | 'toss',
): Promise<BrokerAccount> {
  const res = await fetch('/api/broker/account?broker=' + broker)
  if (!res.ok) {
    return parseError(res)
  }
  return (await res.json()) as BrokerAccount
}
```

- [ ] **Step 2: 패널 컴포넌트 작성**

`web/src/components/BrokerAccountPanel.tsx`:
```tsx
import { useCallback, useEffect, useState, type CSSProperties } from 'react'
import { getBrokerAccount, type BrokerAccount } from '../api'

const BROKERS: { key: 'kis' | 'toss'; label: string }[] = [
  { key: 'kis', label: 'KIS (모의)' },
  { key: 'toss', label: 'TOSS' },
]
const POLL_MS = 30000

function formatter(broker: string): Intl.NumberFormat {
  const usd = broker === 'toss'
  return new Intl.NumberFormat(usd ? 'en-US' : 'ko-KR', {
    style: 'currency',
    currency: usd ? 'USD' : 'KRW',
    maximumFractionDigits: usd ? 2 : 0,
  })
}

export default function BrokerAccountPanel() {
  const [broker, setBroker] = useState<'kis' | 'toss'>('kis')
  const [data, setData] = useState<BrokerAccount | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async (b: 'kis' | 'toss') => {
    setLoading(true)
    setError(null)
    try {
      setData(await getBrokerAccount(b))
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '계좌 조회 실패')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load(broker)
    const id = setInterval(() => load(broker), POLL_MS)
    return () => clearInterval(id)
  }, [broker, load])

  const fmt = formatter(broker)

  function tabStyle(active: boolean): React.CSSProperties {
    return {
      padding: '4px 10px',
      borderRadius: 4,
      cursor: 'pointer',
      border: '1px solid var(--border, #ccc)',
      background: active ? 'var(--accent, #2a6)' : 'transparent',
      color: active ? '#fff' : 'inherit',
    }
  }

  return (
    <div className="card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <h2 className="card-title" style={{ margin: 0 }}>실 계좌 현황</h2>
        <span
          style={{
            fontSize: 12,
            color: 'var(--text-dim)',
            border: '1px solid var(--text-dim)',
            borderRadius: 4,
            padding: '1px 6px',
          }}
        >
          읽기 전용 · 실 계좌
        </span>
        <div style={{ display: 'flex', gap: 6, marginLeft: 'auto' }}>
          {BROKERS.map((b) => (
            <button key={b.key} onClick={() => setBroker(b.key)} style={tabStyle(broker === b.key)}>
              {b.label}
            </button>
          ))}
          <button onClick={() => load(broker)} disabled={loading}>
            새로고침
          </button>
        </div>
      </div>

      {error ? (
        <p style={{ color: 'var(--fail)' }}>{error}</p>
      ) : data === null ? (
        <p style={{ color: 'var(--text-dim)' }}>불러오는 중…</p>
      ) : (
        <>
          <div style={{ display: 'flex', gap: 24, margin: '12px 0' }}>
            <div>
              <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>
                총 자산 (equity) · {data.mode === 'paper' ? '모의' : '실전'}
              </div>
              <div style={{ fontSize: 22, fontVariantNumeric: 'tabular-nums' }}>
                {fmt.format(data.equity)}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>예수금 (cash)</div>
              <div style={{ fontSize: 22, fontVariantNumeric: 'tabular-nums' }}>
                {fmt.format(data.cash)}
              </div>
            </div>
          </div>
          {data.positions.length === 0 ? (
            <p style={{ color: 'var(--text-dim)' }}>보유 종목 없음</p>
          ) : (
            <table className="orders-table">
              <thead>
                <tr>
                  <th>종목</th>
                  <th>평가금액</th>
                </tr>
              </thead>
              <tbody>
                {data.positions.map((p) => (
                  <tr key={p.symbol}>
                    <td>{p.symbol}</td>
                    <td style={{ fontVariantNumeric: 'tabular-nums' }}>{fmt.format(p.value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 3: App.tsx 에 배치**

`web/src/App.tsx`의 import 블록(다른 패널 import 옆)에 추가:
```tsx
import BrokerAccountPanel from './components/BrokerAccountPanel'
```
`app-main` 안의 `<SchedulerRunsPanel />` 바로 아래에 추가:
```tsx
          <PaperPanel request={lastRequest} />
          <CalendarPanel />
          <SchedulerRunsPanel />
          <BrokerAccountPanel />
```

- [ ] **Step 4: 빌드(타입체크) 확인**

Run: `cd web && npm run build`
Expected: 빌드 성공(타입 에러 없음; 청크 크기 경고는 무해).

- [ ] **Step 5: 커밋**

```bash
git add web/src/api.ts web/src/components/BrokerAccountPanel.tsx web/src/App.tsx
git commit -m "feat(web): add read-only broker account panel (KIS/TOSS, poll+refresh)"
```

---

## 완료 후

- 백엔드+프론트 머지 후, 실 서버로 수동 확인(선택): `uv run uvicorn server.app:app --reload` + `cd web && npm run dev` → 패널에서 KIS(모의)·TOSS 실 잔고/보유 표시 확인.
- ROADMAP에 실 계좌 패널 항목 표기.
