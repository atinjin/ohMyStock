# 통화 일관성 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 백테스트·페이퍼 대시보드의 "원/달러" 혼용을 USD 기준으로 통일하고 ≈원 참고를 곁들인다.

**Architecture:** 백엔드에 `Config.currency="USD"`를 추가해 `full_report`·페이퍼 state가 통화를 명시하고, `GET /api/fx`가 USD/KRW 환율(yfinance, 기존 market_provider 재사용)을 노출한다. 프론트는 공용 통화 헬퍼(`usd`/`approxKrw`)로 최종자산·페이퍼 금액·자본 입력을 USD($) + ≈원으로 통일한다.

**Tech Stack:** Python 3.11, FastAPI, yfinance, pytest, React/Vite/TypeScript, uv.

## Global Constraints

- 백엔드 테스트 `uv run pytest <path> -q`(VIRTUAL_ENV 3.9.11 경고 무해). 프론트 빌드 `cd web && npm run build`.
- 기준 통화 **USD**. `Config.currency: str = "USD"`. `full_report`·`PaperService.get_state()` 응답에 `"currency"` 포함.
- `GET /api/fx?base=USD&quote=KRW` → `{"base","quote","rate"}`(1 USD=? KRW). `app.state.market_provider("USDKRW=X")["last"]` 재사용, 300초 캐시. 다른 통화쌍 400, provider 실패 502.
- 프론트: `usd(n)`(=`$X`), `approxKrw(usd, rate)`(=`" ≈ "+koreanAmount(usd*rate)`, rate 없으면 `""`). 자본 입력 기본값 `10000`(USD).
- KIS 실 계좌 패널(원)은 그대로(실제 KRW 계좌). 각 태스크 끝 커밋(atinjin).

---

### Task 1: 백엔드 — currency 필드 + `/api/fx`

**Files:**
- Modify: `ohmystock/config.py` (`currency` 필드)
- Modify: `ohmystock/report.py` (`full_report` 반환에 `currency`)
- Modify: `ohmystock/paper/service.py` (`get_state` 반환에 `currency`)
- Modify: `server/app.py` (`app.state.fx_cache`, `GET /api/fx`)
- Test: `tests/test_paper_service.py`, `tests/test_server.py`

**Interfaces:**
- Produces: `Config.currency`(기본 "USD"); `full_report(...)`·`get_state()` 응답에 `"currency"`; `GET /api/fx`.
- Consumes: `app.state.market_provider`(quote dict 반환, 기존).

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_paper_service.py` 끝에 추가:
```python
def test_get_state_includes_currency(tmp_path):
    svc = _service(tmp_path)
    svc.init_account("MACrossover", {"short": 3, "long": 10}, ["AAPL"],
                     1_000_000, "2024-01-01", "2024-03-31")
    assert svc.get_state()["currency"] == "USD"
```

`tests/test_server.py` 의 `test_backtest_ok` 끝에 단언 한 줄 추가:
```python
    assert data["currency"] == "USD"
```

`tests/test_server.py` 끝에 추가:
```python
def test_fx_endpoint(tmp_path):
    calls = {"n": 0}

    def provider(symbol):
        calls["n"] += 1
        assert symbol == "USDKRW=X"
        return {"last": 1531.0, "prev_close": 1530.0, "year_high": 1600.0,
                "year_low": 1300.0, "sparkline": [1530.0, 1531.0]}

    adapter = YFinanceAdapter(cache=ParquetCache(tmp_path), downloader=_fake_dl)
    client = TestClient(create_app(adapter=adapter, market_provider=provider))
    r = client.get("/api/fx?base=USD&quote=KRW")
    assert r.status_code == 200
    assert r.json() == {"base": "USD", "quote": "KRW", "rate": 1531.0}
    client.get("/api/fx")            # 기본 USD/KRW → 캐시
    assert calls["n"] == 1           # provider 1회만
    assert client.get("/api/fx?base=EUR&quote=KRW").status_code == 400
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_paper_service.py::test_get_state_includes_currency tests/test_server.py::test_fx_endpoint -q`
Expected: FAIL (`currency` 키 없음 / `/api/fx` 404).

- [ ] **Step 3: 백엔드 구현**

`ohmystock/config.py` 의 `initial_capital` 줄을 아래로 교체하고 `currency` 추가:
```python
    initial_capital: float = 5_000_000      # USD 기준(시스템 통화). 검증 비율엔 영향 없음
    currency: str = "USD"                    # 시스템 기준 통화
```

`ohmystock/report.py` 의 `full_report` 반환 dict에 `currency` 추가(`"strategy"` 옆 등):
```python
    return {
        "strategy": type(strategy).__name__,
        "currency": config.currency,
        "symbols": list(symbols),
```

`ohmystock/paper/service.py` 의 `get_state` 반환 dict에 `currency` 추가(`"exists": True` 아래):
```python
        return {
            "exists": True,
            "currency": self.config.currency,
            "config": {
```

`server/app.py` 의 `create_app` 내 `app.state.market_cal_us = None` 아래에 추가:
```python
        app.state.fx_cache = {}
```
`return app` 직전에 엔드포인트 추가:
```python
    @app.get("/api/fx")
    def fx(base: str = "USD", quote: str = "KRW"):
        """USD→KRW 환율(준실시간, 300초 캐시). 다른 통화쌍은 400."""
        if (base, quote) != ("USD", "KRW"):
            raise HTTPException(status_code=400, detail="현재 USD→KRW만 지원합니다")
        cache = app.state.fx_cache
        now_ts = time.time()
        if cache.get("rate") is not None and now_ts - cache.get("ts", 0) < 300:
            return {"base": base, "quote": quote, "rate": cache["rate"]}
        try:
            rate = float(app.state.market_provider("USDKRW=X")["last"])
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        cache["rate"] = rate
        cache["ts"] = now_ts
        return {"base": base, "quote": quote, "rate": rate}
```
(`time`·`HTTPException` 는 이미 import됨.)

- [ ] **Step 4: 통과 확인 + 전체 스위트**

Run: `uv run pytest tests/test_paper_service.py tests/test_server.py -q` → PASS.
Run: `uv run pytest -q` → 전 프로젝트 그린.

- [ ] **Step 5: 커밋**

```bash
git add ohmystock/config.py ohmystock/report.py ohmystock/paper/service.py server/app.py tests/test_paper_service.py tests/test_server.py
git commit -m "feat: declare USD as system currency + GET /api/fx (USD/KRW)"
```

---

### Task 2: 프론트 — USD 표기 통일 + ≈원 참고

**Files:**
- Modify: `web/src/format.ts` (`usd`, `approxKrw`)
- Modify: `web/src/api.ts` (`Fx`, `getFx`)
- Modify: `web/src/App.tsx` (최종자산 USD+≈₩, fxRate)
- Modify: `web/src/components/BacktestForm.tsx` (자본 USD+≈만원, 기본 10000)
- Modify: `web/src/components/PaperPanel.tsx` (원→USD+≈₩)

**Interfaces:**
- Consumes: Task 1의 `/api/fx`, 응답의 `currency`.
- Produces: `usd(n)`, `approxKrw(usd, rate)`, `getFx()`.

- [ ] **Step 1: format 헬퍼 추가**

`web/src/format.ts` 끝에 추가:
```typescript
/** USD 통화 포맷 (예: 10000 -> "$10,000"). */
export function usd(n: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency', currency: 'USD', maximumFractionDigits: 0,
  }).format(n)
}

/** USD 금액의 원화 환산 참고 (예: " ≈ 1,531만원"). rate 없으면 빈 문자열. */
export function approxKrw(usdAmount: number, rate: number | null): string {
  if (!rate || !Number.isFinite(usdAmount)) return ''
  return ' ≈ ' + koreanAmount(usdAmount * rate)
}
```

- [ ] **Step 2: api.ts FX 클라이언트**

`web/src/api.ts` 끝에 추가:
```typescript
// 환율(USD→KRW)

export interface Fx {
  base: string
  quote: string
  rate: number
}

export async function getFx(): Promise<Fx> {
  const res = await fetch('/api/fx')
  if (!res.ok) {
    return parseError(res)
  }
  return (await res.json()) as Fx
}
```

- [ ] **Step 3: App.tsx — 최종자산 USD + ≈₩**

`web/src/App.tsx` 상단의 KRW 포맷터 블록을 **삭제**:
```tsx
const currency = new Intl.NumberFormat('ko-KR', {
  style: 'currency',
  currency: 'KRW',
  maximumFractionDigits: 0,
})
```
import에 추가(기존 `./api` import 목록에 `getFx`, 그리고 `./format`에서 헬퍼):
```tsx
import { getFx, /* 기존 항목들 */ } from './api'
import { usd, approxKrw } from './format'
```
`function App()` 안 상태들 옆에 fxRate 추가 + 로드:
```tsx
  const [fxRate, setFxRate] = useState<number | null>(null)

  useEffect(() => {
    getFx().then((f) => setFxRate(f.rate)).catch(() => setFxRate(null))
  }, [])
```
최종자산 표시를 교체:
```tsx
                  <span className="summary-equity-value">
                    {usd(report.final_equity)}
                    <span style={{ fontSize: 13, color: 'var(--text-dim)', fontWeight: 400 }}>
                      {approxKrw(report.final_equity, fxRate)}
                    </span>
                  </span>
```
`<BacktestForm ... />` 호출에 `fxRate={fxRate}` prop 추가.

- [ ] **Step 4: BacktestForm.tsx — 자본 USD + ≈만원**

`web/src/components/BacktestForm.tsx`:
import 교체(기존 `withCommas, koreanAmount` → `usd`·`approxKrw` 추가):
```tsx
import { withCommas, usd, approxKrw } from '../format'
```
props 타입에 `fxRate?: number | null` 추가하고 시그니처에서 구조분해(예: `export default function BacktestForm({ strategies, loading, onRun, onPreview, fxRate }: Props)`). `DEFAULT_CAPITAL` 상수를 `10000` 으로 변경.
자본 suffix·읽기 줄을 교체:
```tsx
          <span className="capital-suffix">USD</span>
        </div>
        <span className="capital-reading">
          = <strong>{usd(capital)}</strong>
          <span style={{ color: 'var(--text-dim)' }}>{approxKrw(capital, fxRate ?? null)}</span>
        </span>
```

- [ ] **Step 5: PaperPanel.tsx — 원 → USD + ≈₩**

`web/src/components/PaperPanel.tsx`:
import에 `usd`, `approxKrw`, `getFx` 추가하고, 컴포넌트 안에 fxRate 상태 + 로드 추가:
```tsx
import { withCommas, usd, approxKrw } from '../format'
import { getFx /* 기존 api import와 합치기 */ } from '../api'
```
```tsx
  const [fxRate, setFxRate] = useState<number | null>(null)
  useEffect(() => {
    getFx().then((f) => setFxRate(f.rate)).catch(() => setFxRate(null))
  }, [])
```
3개 지표 카드와 체결 금액의 `{withCommas(x)}원` 을 USD로 교체:
```tsx
              <div className="metric-value">
                {usd(state.equity ?? 0)}
                <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>{approxKrw(state.equity ?? 0, fxRate)}</span>
              </div>
```
```tsx
              <div className="metric-value">{usd(state.cash ?? 0)}</div>
```
```tsx
              <div className="metric-value">{usd(state.peak_equity ?? 0)}</div>
```
```tsx
                        <td className="orders-amount">
                          {usd(trade.notional)}
                        </td>
```

- [ ] **Step 6: 빌드 확인**

Run: `cd web && npm run build`
Expected: 빌드 성공(타입 에러 없음; 미사용 import 없도록 정리).

- [ ] **Step 7: 커밋**

```bash
git add web/src/format.ts web/src/api.ts web/src/App.tsx web/src/components/BacktestForm.tsx web/src/components/PaperPanel.tsx
git commit -m "feat(web): unify dashboard to USD with ≈KRW reference"
```

---

## 완료 후

- 실 서버로 확인: 백테스트 최종자산·페이퍼 금액·자본 입력이 `$` + `≈ …만원` 으로 통일, LivePreview·시장개요·실계좌와 일치.
- ROADMAP §5 "단위 일관성(통화)" 항목 완료 표기, §3 진행 중에서 제거.
